from typing import List, Any, Tuple, TYPE_CHECKING

from app.models.guideline_evaluation.question_dataset.question_entry import QuestionEntry, QuestionClassification
from app.models.guideline_evaluation.question_dataset.question_parser_result import (
    QuestionParserResult, ExpectedAnswerParserResult,
)
from app.models.knowledge.guidelines import GuidelineReferenceGroup, GuidelineMetadataReference, ReferenceType
from app.models.knowledge.guidelines.guideline_reference_models import BoundingBox
from app.services.knowledge.guidelines import GuidelineService
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.services.knowledge.guidelines.references.reference_finder_service import ReferenceFinderService
from app.utils.logger import setup_logger

if TYPE_CHECKING:
    from app.services.guideline_evaluation.question_dataset import QuestionDatasetService

logger = setup_logger(__name__)


class QuestionDatasetParserService:
    """
    Service layer to manage automatic transformation of question-answer entries to something insertable into mongodb.
    - Parse csv to json
    - With usage of reference service / dataset service, insert the jsons
    """
    
    def __init__(
            self, dataset_service: "QuestionDatasetService", reference_service: GuidelineReferenceService,
            reference_finder_service: ReferenceFinderService, guideline_service: GuidelineService,
    ):
        self.dataset_service = dataset_service
        self.reference_service = reference_service
        self.reference_finder_service = reference_finder_service
        self.guideline_service = guideline_service
    
    @staticmethod
    def find_csv_entries_based_on_parser_result(csv_values, parser_result: QuestionParserResult):
        csv_entries = []
        i = 0
        while i < len(csv_values):
            current_value = csv_values.iloc[i]
            question = current_value.get("Question", "")
            if question == parser_result.question:
                csv_entries.append(current_value)
                i += 1
        return csv_entries
    
    def csv_to_parser_result(self, csv_values) -> Tuple[List[QuestionParserResult], List[Any]]:
        """
        Transforms csv rows into objects that can be inserted into mongodb.
        - Meaning: question entries with values as ready as possible
        - And references ready to be inserted (linked to guideline id)

        Names for file columns:
        - Question supercategory, Question subcategory
        - Question
        - Correct Answer (text)
        - Answer Guideline, Answer Gpage, Retrieval Text
        - Comment
        
        Returns:
            - List of json objects
            - List of failed entries (somehow invalid)
        """
        csv_values.fillna("", inplace=True)
        parsed_entries = []
        failed_entries = []
        
        i = 0
        while i < len(csv_values):
            current_value = csv_values.iloc[i]
            
            logger.debug(f"Parsing entry {i}: {current_value}")
            question = current_value.get("Question", "")
            super_class = current_value.get("Question supercategory", "").strip()
            sub_class = current_value.get("Question subcategory", "").strip()
            expected_text_answer = current_value.get("Correct Answer", "")
            note = current_value.get("Comment", "")
            
            if question == "" or super_class == "" or sub_class == "":
                logger.warning(
                    f"Skipping entry {i} because it missing at least one required value (question, super_class, sub_class).",
                )
                failed_entries.append(current_value)
                i += 1
                continue
            try:
                self.dataset_service.validate_question_classes(super_class, sub_class)
            except ValueError:
                logger.warning(f"Skipping entry {i} because it has invalid super_class or sub_class.")
                failed_entries.append(current_value)
                i += 1
                continue
            
            expected_retrieval = []
            intended_length_of_retrieval = 0
            j = 0
            while j + i < len(csv_values):
                retrieval_value = csv_values.iloc[i + j]
                if retrieval_value.get("Question", "") == question:
                    logger.debug(f"Found new expected retrieval for '{question[:20]}...' at {i + j}")
                    
                    guideline = retrieval_value.get("Answer Guideline", "")
                    page_str = retrieval_value.get("Answer Gpage", "")
                    expected_retrieval_text = retrieval_value.get("Retrieval Text", "")
                    
                    if guideline != "" and page_str != "":
                        intended_length_of_retrieval += 1
                        try:
                            matching_guidelines = self.guideline_service.get_all_guidelines(
                                awmf_register_number_full=guideline,
                            )
                            assert len(matching_guidelines) > 0, f"Guideline '{guideline}' not found."
                        except:
                            logger.warning(f"Skipping entry {i + j} because guideline '{guideline}' not found.")
                            failed_entries.append(retrieval_value)
                            j += 1
                            continue
                        guideline_id = matching_guidelines[0].id
                        logger.debug(
                            f"For '{guideline}', found {len(matching_guidelines)} guideline IDs, will choose {guideline_id}.",
                        )
                        
                        try:
                            page = int(page_str) - 1
                            assert page >= 0, f"Page '{page_str}' is not a number."
                        except:
                            logger.warning(f"Skipping entry {i + j} because page '{page_str}' is not a number.")
                            failed_entries.append(retrieval_value)
                            j += 1
                            continue
                        logger.debug(f"For '{guideline}', found page '{page}'.")
                    
                    else:
                        logger.debug(f"No retrieval found.")
                        break
                    
                    expected_retrieval.append(
                        ExpectedAnswerParserResult(
                            guideline_id=guideline_id, page=page, contained_text=expected_retrieval_text,
                        ),
                    )
                    logger.debug(f"Added expected retrieval: {expected_retrieval[-1]}")
                    j += 1
                else:
                    break
            
            if len(expected_retrieval) == 0 and intended_length_of_retrieval > 0:
                logger.warning(f"Skipping entry {i} because no intended expected retrieval could be attached.")
                failed_entries.append(current_value)
                i += 1
                continue
            
            if len(expected_retrieval) != intended_length_of_retrieval:
                logger.warning(f"Be aware: attaching correct expected retrieval failed for {i}")
            
            parsed_entries.append(
                QuestionParserResult(
                    question=question, correct_answer=expected_text_answer, expected_retrieval=expected_retrieval,
                    note=note, classification=QuestionClassification(super_class=super_class, sub_class=sub_class),
                ),
            )
            logger.debug(f"Added parsed entry: {parsed_entries[-1]}")
            
            i = i + j + 1
        
        logger.info(f"Parsed {len(parsed_entries)} entries, with {len(failed_entries)} failed entries.")
        
        return parsed_entries, failed_entries
    
    def insert_question_entries_from_parser_result(
            self, question_entries: List[QuestionParserResult],
            reference_group_name: str = "guideline_question_dataset",
    ):
        """
        Inserts a list of question entries into a dataset, associates them with a reference group, and creates
        the necessary references. The function handles creating the reference group if it does not already
        exist and manages both successful and failed insert operations.

        Parameters:
            question_entries : List[QuestionParserResult]
                A list of QuestionParserResult objects representing the question entries to be inserted.
            reference_group_name : str, optional
                The name of the reference group to associate with the question entries. Defaults to 'guideline_question_dataset'.

        Returns:
            Tuple[List[str], List[QuestionParserResult]]
                A tuple containing two lists:
                - The first list contains the IDs of successfully inserted question entries.
                - The second list contains QuestionParserResult objects for the entries that failed to insert.

        Raises:
            Exception
                Propagates any exceptions encountered that prevent the operation from proceeding.
        """
        try:
            try:
                reference_group_id = self.reference_service.get_reference_group_by_name(reference_group_name).id
                logger.info(f"Found reference group '{reference_group_name}'.")
            except ValueError:
                reference_group_id = self.reference_service.create_reference_group(
                    GuidelineReferenceGroup(name=reference_group_name),
                ).id
                logger.info(f"Created reference group '{reference_group_name}'.")
        except Exception as e:
            logger.error(f"Error finding / creating reference group: {str(e)}")
            raise e
        
        successful_entries = []
        failed_entries = []
        
        for entry in question_entries:
            logger.debug(f"Inserting question entry: {entry.question}")
            
            try:
                expected_retrieval_ids = []
                for ref_entry in entry.expected_retrieval:
                    logger.debug(f"Inserting reference entry: {ref_entry}")
                    
                    ref = None
                    try:
                        guideline = self.guideline_service.get_guideline_by_id(ref_entry.guideline_id)
                        ref = self.reference_finder_service.find_text_reference(guideline, ref_entry.contained_text)
                        ref.reference_group_id = reference_group_id
                    except Exception as e:
                        logger.warning(f"Failed to find text reference for entry: {ref_entry}. Reason: {str(e)}")
                    
                    if ref is None:
                        ref = GuidelineMetadataReference(
                            reference_group_id=reference_group_id, guideline_id=ref_entry.guideline_id,
                            bboxs=[BoundingBox(page=ref_entry.page, positions=(0, 0, 0, 0))],
                            metadata_type="Unresolved Reference", metadata_content=ref_entry.contained_text, type=ReferenceType.METADATA,
                        )
                    try:
                        ref_id = self.reference_service.create_reference(ref).id
                    except Exception as e:
                        logger.warning(f"Failed to insert reference: {ref}. Reason: {str(e)}")
                        raise e
                    
                    logger.info(f"Created reference with ID: {ref_id}")
                    logger.debug(f"Created reference with ID: {ref_id}, object: {ref}")
                    expected_retrieval_ids.append(ref_id)
                
                mongodb_entry = QuestionEntry(
                    question=entry.question,
                    classification=entry.classification,
                    correct_answer=entry.correct_answer,
                    note=entry.note,
                    expected_retrieval=expected_retrieval_ids,
                )
                
                entry_id = self.dataset_service.create_dataset_entry(mongodb_entry).id
                
                logger.info(f"Successfully inserted question entry with ID: {entry_id}")
                logger.debug(f"Successfully inserted question entry with ID: {entry_id}, object: {mongodb_entry}")
                successful_entries.append(entry_id)
            
            except Exception as e:
                logger.warning(f"Failed to insert question entry: {entry}. Reason: {str(e)}")
                failed_entries.append(entry)
        
        logger.info(
            f"Successfully inserted {len(successful_entries)} question entries, failed to insert {len(failed_entries)} entries.",
        )
        
        return successful_entries, failed_entries
