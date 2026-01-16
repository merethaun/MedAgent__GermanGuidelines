import re
from typing import Union, Optional, List, Dict, Any

from bson import ObjectId
from pydantic import BaseModel
from pymongo.synchronous.collection import Collection

from app.models.chat.chat import Chat
from app.models.guideline_evaluation.evaluation_results.generation_result import (
    GenerationResultRun, GenerationResult, ManualEvaluator, AutomaticEvaluation,
)
from app.services.chat import ChatService
from app.services.guideline_evaluation.question_dataset import QuestionDatasetService
from app.utils.knowledge.mongodb_object_id import as_object_id, PyObjectId
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ResultGenerationService:
    """
    Service to create generation results to be evaluated AND CRUD management of GenerationResult entries
    """
    
    def __init__(
            self, evaluators_collection: Collection, results_collection: Collection, dataset_service: QuestionDatasetService,
            chat_service: ChatService,
    ):
        self.evaluators_collection = evaluators_collection
        self.results_collection = results_collection
        self.dataset_service = dataset_service
        self.chat_service = chat_service
    
    def find_generation_runs(
            self, run_name: Optional[str] = None, workflow_id: Optional[Union[str, ObjectId]] = None,
    ) -> List[GenerationResultRun]:
        logger.info("Fetching generation runs from database with filters.")
        logger.debug("Building generation run query with provided filters.")
        
        query: Dict[str, Any] = {}
        
        if run_name is not None:
            query["generation_run.name"] = run_name
            logger.debug(f"Filter applied: run_name = {run_name}")
        
        if workflow_id is not None:
            query["generation_run.workflow_system_id"] = str(workflow_id)
            logger.debug(f"Filter applied: workflow_id = {workflow_id}")
        
        try:
            logger.info(f"Executing query on results collection: {query}")
            matching_entries = list(self.results_collection.find(query))
            logger.debug(f"Found {len(matching_entries)} matching result entries.")
            
            all_runs = list({GenerationResultRun(**entry["generation_run"]) for entry in matching_entries})
            logger.debug(f"Extracted {len(all_runs)} unique generation runs from matched entries.")
            
            if len(all_runs) == 0:
                logger.error(f"No matching generation runs found for query: {query}")
                raise ValueError("No matching generation run found.")
            elif len(all_runs) > 1:
                logger.warning(f"Multiple ({len(all_runs)}) generation runs matched the filters.")
            else:
                logger.info("Exactly one generation run matched the filters.")
            
            return all_runs
        
        except Exception as e:
            logger.error(f"Error occurred while fetching generation runs: {str(e)}")
            raise
    
    def generate_stored_result(
            self, run: GenerationResultRun, question_entry_id: Union[str, ObjectId],
    ) -> GenerationResult:
        existing_entries = self.list_generation_results(
            run_name=run.name, workflow_id=run.workflow_system_id, question_id=question_entry_id,
        )
        if existing_entries:
            msg = (f"Generation result with the provided configuration already existing, see ids: "
                   f"[{[e.id for e in existing_entries]}]")
            logger.error(msg)
            raise ValueError(msg)
        
        logger.info(
            f"Generating stored result for run '{run.name}' (wf system: {run.workflow_system_id}) "
            f"with question ID: {question_entry_id}",
        )
        question_entry = self.dataset_service.get_question_entry_by_id(question_entry_id)
        logger.debug(f"Retrieved question entry with text: {question_entry.question[:20]}")
        
        chat = Chat(
            workflow_system_id=run.workflow_system_id,
            username=f"Result generation for evaluation: {run.name}",
        )
        chat = self.chat_service.create_chat_entry(chat)
        logger.debug(f"Created new chat entry with ID: {chat.id}")
        
        chat = self.chat_service.pose_question(chat_id=chat.id, user_input=question_entry.question)
        logger.debug("Posed question to chat service")
        if not chat.interactions or not chat.interactions[-1].generator_output:
            logger.error(f"Could not create valid generation result (chat={chat.id}), will remove created chat")
            self.chat_service.delete_chat_entry(chat.id)
            raise ValueError(f"Could not create / find valid interactions for asked question")
        
        gen_result = GenerationResult(
            related_question=question_entry.id,
            generation_run=run,
            related_chat=chat.id,
            created_at=chat.interactions[-1].time_response_output,
        )
        
        data = gen_result.model_dump(by_alias=True, exclude_unset=True)
        result = self.results_collection.insert_one(data)
        logger.info(f"Stored generation result with ID: {result.inserted_id}")
        
        return self.get_generation_result_entry(result.inserted_id)
    
    def regenerate_stored_result(self, generation_result_entry_id) -> GenerationResult:
        existing_entry = self.get_generation_result_entry(generation_result_entry_id)
        
        logger.info(f"Regenerating stored result for run '{existing_entry.generation_run.name}' with question ID: {existing_entry.related_question}")
        
        # (1) generate result
        question_entry = self.dataset_service.get_question_entry_by_id(existing_entry.related_question)
        logger.debug(f"Retrieved question entry with text: {question_entry.question[:20]}")
        
        chat = Chat(
            workflow_system_id=existing_entry.generation_run.workflow_system_id,
            username=f"Result generation for evaluation: {existing_entry.generation_run.name}",
        )
        chat = self.chat_service.create_chat_entry(chat)
        logger.debug(f"Created new chat entry with ID: {chat.id}")
        
        chat = self.chat_service.pose_question(chat_id=chat.id, user_input=question_entry.question)
        logger.debug("Posed question to chat service")
        if not chat.interactions or not chat.interactions[-1].generator_output:
            logger.error(f"Could not create valid generation result (chat={chat}), will remove created chat")
            self.chat_service.delete_chat_entry(chat.id)
            raise ValueError(f"Could not create / find valid interactions for asked question")
        
        # (2) clean up old entry
        self.chat_service.delete_chat_entry(existing_entry.related_chat)
        existing_entry.automatic_evaluation = AutomaticEvaluation()
        existing_entry.factuality_evaluations = []
        existing_entry.correctness_evaluations = []
        
        # (3) update entry
        existing_entry.related_chat = chat.id
        existing_entry.created_at = chat.interactions[-1].time_response_output
        
        data = existing_entry.model_dump(by_alias=True, exclude_unset=True)
        self.update_generation_result_entry(existing_entry.id, data)
        logger.info(f"Updated generation result with ID: {existing_entry.id}")
        
        return self.get_generation_result_entry(existing_entry.id)
    
    def get_generation_result_entry(self, gen_result_entry_id: Union[str, ObjectId]) -> GenerationResult:
        logger.debug(f"Retrieving generation result entry with ID: {gen_result_entry_id}")
        obj_id = ObjectId(gen_result_entry_id) if isinstance(gen_result_entry_id, str) else gen_result_entry_id
        doc = self.results_collection.find_one({"_id": obj_id})
        if not doc:
            logger.warning(f"Generation result entry not found with ID: {gen_result_entry_id}")
            raise ValueError(f"Generation result not found: {gen_result_entry_id}")
        logger.debug("Found and returning generation result entry")
        return GenerationResult(**doc)
    
    def update_generation_result_entry(
            self, gen_result_entry_id: Union[str, ObjectId], update_data: Dict[str, Any],
    ) -> GenerationResult:
        logger.debug(f"Updating generation result entry with ID: {gen_result_entry_id}")
        obj_id = ObjectId(gen_result_entry_id) if isinstance(gen_result_entry_id, str) else gen_result_entry_id
        
        # Validate that the entry exists
        existing_entry = self.results_collection.find_one({"_id": obj_id})
        if not existing_entry:
            msg = f"Generation result entry with ID {gen_result_entry_id} not found"
            logger.warning(msg)
            raise ValueError(msg)
        
        def recursive_model_dump(value: Any) -> Any:
            if isinstance(value, BaseModel):
                return {k: recursive_model_dump(v) for k, v in value.model_dump(by_alias=True).items()}
            elif isinstance(value, list):
                return [recursive_model_dump(item) for item in value]
            elif isinstance(value, dict):
                return {k: recursive_model_dump(v) for k, v in value.items()}
            else:
                return value
        
        update_doc = {key: recursive_model_dump(value) for key, value in update_data.items()}
        
        logger.debug(f"Applying update: {update_doc}")
        result = self.results_collection.find_one_and_update(
            {"_id": obj_id},
            {"$set": update_doc},
        )
        
        if not result:
            msg = f"Failed to update generation result entry with ID: {gen_result_entry_id}"
            logger.error(msg)
            raise ValueError(msg)
        
        logger.info(f"Successfully updated generation result entry with ID: {gen_result_entry_id}")
        return self.get_generation_result_entry(gen_result_entry_id)
    
    def delete_generation_result_entry(self, gen_result_entry_id: Union[str, ObjectId], delete_with_associated_chat):
        logger.debug(f"Removing generation result entry with ID: {gen_result_entry_id}")
        obj_id = ObjectId(gen_result_entry_id) if isinstance(gen_result_entry_id, str) else gen_result_entry_id
        
        if delete_with_associated_chat:
            try:
                generation_result_entry = self.get_generation_result_entry(obj_id)
                self.chat_service.delete_chat_entry(generation_result_entry.related_chat)
            except ValueError as e:
                logger.warning(f"Error deleting associated chat for generation result: {str(e)}", exc_info=True)
                raise ValueError(f"Could not delete associated chat for generation result: {str(e)}")
            except Exception as e:
                logger.error(
                    f"Failure during deletion of associated chat for generation result: {str(e)}", exc_info=True,
                )
                raise Exception(f"Could not delete associated chat for generation result: {str(e)}")
        
        # Check if entry exists
        if not self.results_collection.find_one({"_id": obj_id}):
            msg = f"Generation result entry with ID {gen_result_entry_id} not found -> can assumed to be 'removed'."
            logger.warning(msg)
            return True
        
        result = self.results_collection.delete_one({"_id": obj_id})
        
        if result.deleted_count > 0:
            logger.info(f"Successfully deleted generation result entry with ID: {gen_result_entry_id}")
            return True
        else:
            msg = f"Failed to delete generation result entry with ID: {gen_result_entry_id}"
            logger.warning(msg)
            raise ValueError(msg)
    
    def list_generation_results(
            self, run_name: Optional[str] = None, run_name_regex: Optional[str] = None, workflow_id: Optional[Union[str, ObjectId]] = None,
            question_id: Optional[Union[str, ObjectId]] = None, chat_id: Optional[Union[str, ObjectId]] = None,
            manual_eval_required: Optional[bool] = None,
    ) -> List[GenerationResult]:
        query = {}
        
        def to_object_id(val):
            return ObjectId(val) if isinstance(val, str) else val
        
        if chat_id is not None:
            query["related_chat"] = to_object_id(chat_id)
            logger.debug(f"Filter applied: related_chat = '{chat_id}'")
        
        if question_id is not None:
            query["related_question"] = to_object_id(question_id)
            logger.debug(f"Filter applied: related_question = '{question_id}'")
        
        if run_name is not None and run_name_regex is not None:
            raise ValueError("Cannot specify both run_name and run_name_regex")
        if run_name is not None:
            query["generation_run.name"] = {"$regex": re.escape(run_name), "$options": "i"}
            logger.debug(f"Filter applied: run_name contains '{run_name}' (case-insensitive)")
        if run_name_regex is not None:
            query["generation_run.name"] = {"$regex": run_name_regex, "$options": "i"}
            logger.debug(f"Filter applied: run_name matches regex '{run_name_regex}' (case-insensitive)")
        
        if workflow_id is not None:
            query["generation_run.workflow_system_id"] = to_object_id(workflow_id)
            logger.debug(f"Filter applied: workflow_system_id = '{workflow_id}'")
        
        if manual_eval_required is not None:
            query["requires_manual_evaluation"] = manual_eval_required
            logger.debug(f"Filter applied: requires_manual_evaluation = '{manual_eval_required}'")
        
        try:
            logger.info(f"Executing generation result query: {query}")
            gen_result_entries = list(self.results_collection.find(query))
            if len(gen_result_entries) == 0:
                logger.warning("No generation result entries found matching query.")
            else:
                logger.info(f"Successfully fetched {len(gen_result_entries)} generation results matching query.")
            results = [GenerationResult(**doc) for doc in gen_result_entries]
            return results
        except Exception as e:
            logger.error(f"Error executing  generation result query: {str(e)}")
            raise
    
    def insert_new_evaluator(self, manual_evaluator: ManualEvaluator) -> ManualEvaluator:
        """
        Insert a new manual evaluator into the database.
        """
        logger.debug("Attempting to insert new manual evaluator.")
        data = manual_evaluator.model_dump(by_alias=True)
        data.pop("_id", None)
        
        try:
            result = self.evaluators_collection.insert_one(data)
            logger.info(f"Inserted manual evaluator with ID {result.inserted_id}")
            return self.find_evaluator(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to insert manual evaluator: {str(e)}", exc_info=True)
            raise
    
    def list_all_evaluators(self, name: Optional[str] = None) -> List[ManualEvaluator]:
        """
        List all evaluators, optionally filtering by name.
        """
        logger.debug("Fetching all evaluators.")
        query = {}
        if name:
            query["name"] = {"$regex": re.escape(name), "$options": "i"}
            logger.debug(f"Filter applied: name contains '{name}'")
        
        try:
            docs = list(self.evaluators_collection.find(query))
            logger.info(f"Fetched {len(docs)} evaluator(s).")
            return [ManualEvaluator(**doc) for doc in docs]
        except Exception as e:
            logger.error(f"Error while listing evaluators: {str(e)}")
            raise
    
    def find_evaluator(self, evaluator_entry_id: Union[str, ObjectId]) -> ManualEvaluator:
        """
        Find an evaluator by its ID.
        """
        logger.debug(f"Searching for evaluator with ID {evaluator_entry_id}")
        try:
            evaluator = self.evaluators_collection.find_one({"_id": as_object_id(evaluator_entry_id)})
            if not evaluator:
                logger.warning(f"Evaluator with ID {evaluator_entry_id} not found.")
                raise ValueError(f"Evaluator not found for id: {str(evaluator_entry_id)}")
            logger.info(f"Found evaluator with ID {evaluator_entry_id}")
            return ManualEvaluator(**evaluator)
        except Exception as e:
            logger.error(f"Error fetching evaluator with ID {evaluator_entry_id}: {str(e)}")
            raise
    
    def update_evaluator(self, evaluator_entry_id: Union[str, ObjectId], updated_evaluator: ManualEvaluator) -> ManualEvaluator:
        """
        Update an evaluator entry.
        """
        logger.debug(f"Attempting to update evaluator with ID {evaluator_entry_id}")
        try:
            current = self.evaluators_collection.find_one({"_id": as_object_id(evaluator_entry_id)})
            if not current:
                logger.warning(f"Evaluator with ID {evaluator_entry_id} not found.")
                raise ValueError(f"Evaluator not found for id: {str(evaluator_entry_id)}")
            
            update_data = updated_evaluator.model_dump(by_alias=True, exclude_unset=True, exclude={"id"})
            changes = {k: v for k, v in update_data.items() if current.get(k) != v}
            
            if not changes:
                logger.info(f"No changes to apply for evaluator with ID {evaluator_entry_id}")
                return ManualEvaluator(**current)
            
            result = self.evaluators_collection.update_one(
                {"_id": as_object_id(evaluator_entry_id)},
                {"$set": changes},
            )
            if result.matched_count == 0:
                logger.error(f"Update failed: evaluator with ID {evaluator_entry_id} not found.")
                raise ValueError(f"Evaluator not found for id: {str(evaluator_entry_id)}")
            
            logger.info(f"Evaluator with ID {evaluator_entry_id} updated: {list(changes.keys())}")
            return self.find_evaluator(evaluator_entry_id)
        except Exception as e:
            logger.error(f"Error updating evaluator with ID {evaluator_entry_id}: {str(e)}")
            raise
    
    def delete_evaluator(self, evaluator_entry_id: Union[str, ObjectId]):
        """
        Delete an evaluator by ID.
        """
        logger.debug(f"Attempting to remove evaluation entries from to be deleted evaluator")
        try:
            to_be_updated_entries = self.find_evaluations_for_evaluator(evaluator_entry_id)
            
            for gen_res in to_be_updated_entries:
                gen_res.factuality_evaluations = [
                    f_eval for f_eval in gen_res.factuality_evaluations
                    if str(f_eval.evaluator) != str(evaluator_entry_id)
                ]
                gen_res.correctness_evaluations = [
                    c_eval for c_eval in gen_res.correctness_evaluations
                    if str(c_eval.evaluator) != str(evaluator_entry_id)
                ]
                self.update_generation_result_entry(
                    gen_result_entry_id=gen_res.id,
                    update_data={
                        "factuality_evaluations": gen_res.factuality_evaluations,
                        "correctness_evaluations": gen_res.correctness_evaluations,
                    },
                )
        except Exception as e:
            logger.error(f"Error deleting evaluation entries for evaluator: {evaluator_entry_id} -> {str(e)}", exc_info=True)
            raise
        
        logger.debug(f"Attempting to delete evaluator with ID {evaluator_entry_id}")
        try:
            result = self.evaluators_collection.delete_one({"_id": as_object_id(evaluator_entry_id)})
            if result.deleted_count == 0:
                logger.warning(f"Evaluator with ID {evaluator_entry_id} not found.")
                raise ValueError(f"Evaluator not found for id: {str(evaluator_entry_id)}")
            logger.info(f"Deleted evaluator with ID {evaluator_entry_id}")
        except Exception as e:
            logger.error(f"Error deleting evaluator with ID {evaluator_entry_id}: {str(e)}", exc_info=True)
            raise
    
    def find_evaluations_for_evaluator(self, evaluator_entry_id: Union[str, ObjectId, PyObjectId]) -> List[GenerationResult]:
        """
        Find all GenerationResults that contain evaluations by the specified evaluator.
        Optionally filter by a specific generation_result_id.

        Args:
            evaluator_entry_id: ID of the evaluator (manual evaluator).
            generation_result_id: Optional filter to limit to a specific generation result.

        Returns:
            List of GenerationResult objects containing evaluations by the evaluator.
        """
        logger.debug(f"Looking for evaluations by evaluator ID {evaluator_entry_id}")
        evaluator_oid = as_object_id(str(evaluator_entry_id))
        
        query: Dict[str, Any] = {
            "$or": [
                {"correctness_evaluations": {"$elemMatch": {"evaluator": evaluator_oid}}},
                {"factuality_evaluations": {"$elemMatch": {"evaluator": evaluator_oid}}},
            ],
        }
        
        try:
            logger.info(f"Executing query to find evaluations: {query}")
            results = list(self.results_collection.find(query))
            logger.info(f"Found {len(results)} generation result(s) with evaluations from evaluator {evaluator_entry_id}")
            return [GenerationResult(**r) for r in results]
        except Exception as e:
            logger.error(f"Error finding evaluations for evaluator {evaluator_entry_id}: {str(e)}")
            raise
