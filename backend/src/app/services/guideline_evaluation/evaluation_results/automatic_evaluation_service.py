import difflib
import os
import re
from typing import TYPE_CHECKING, Optional, List, Tuple

import numpy as np
import unicodedata

from app.models.chat.chat import ChatInteraction
from app.models.guideline_evaluation.evaluation_results.generation_result import (
    GenerationResult, EvaluationResponseLatency, EvaluationAccuracy,
    EvaluationRetrieval,
)
from app.models.knowledge.guidelines import GuidelineReference, ReferenceType
from app.services.chat import ChatService
from app.services.guideline_evaluation.question_dataset import QuestionDatasetService
from app.services.knowledge.guidelines import GuidelineService
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.utils.automatic_evaluators import get_rouge, get_bleu, get_meteor, get_bertscore
from app.utils.guideline_evaluation import GPTScoreEvaluator
from app.utils.logger import setup_logger
from app.utils.vectorizer import OpenAI3LargeEmbedder

if TYPE_CHECKING:
    from app.services.guideline_evaluation.evaluation_results import ResultGenerationService

logger = setup_logger(__name__)


class AutomaticEvaluationService:
    """
    Service to create automatically generatable evaluation scores based on generation results and questions with
    correct answer / retrieval entries
    """
    
    def __init__(
            self, dataset_service: QuestionDatasetService, generated_results_service: "ResultGenerationService",
            chat_service: ChatService, references_service: GuidelineReferenceService, guideline_service: GuidelineService,
    ):
        self.dataset_service = dataset_service
        self.generated_results_service = generated_results_service
        self.chat_service = chat_service
        self.references_service = references_service
        self.guideline_service = guideline_service
        self.open_ai_3_large_embedder = OpenAI3LargeEmbedder()
        self.gpt_sim_evaluator = GPTScoreEvaluator(model="azure-gpt-4.1", api_version="2024-08-01-preview")
        
        logger.info("Loading evaluators")
        self.rouge_evaluator = get_rouge()  # https://huggingface.co/spaces/evaluate-metric/rouge
        self.bleu_evaluator = get_bleu()  # https://huggingface.co/spaces/evaluate-metric/bleu
        self.meteor_evaluator = get_meteor()  # https://huggingface.co/spaces/evaluate-metric/meteor
        self.bert_score_evaluator = get_bertscore()  # https://huggingface.co/spaces/evaluate-metric/bertscore, ASSUME GERMAN!!
    
    def _get_to_be_evaluated_interaction(self, generation_result: GenerationResult) -> ChatInteraction:
        logger.debug(f"Getting interaction to evaluate for generation result {generation_result.id}")
        whole_chat = self.chat_service.get_chat_entry_by_id(generation_result.related_chat)
        if not whole_chat.interactions:
            logger.error(f"Cannot evaluate for empty chat with ID {generation_result.related_chat}")
            raise ValueError(f"Can not evaluate for emtpy chat")
        to_be_evaluated_interaction = whole_chat.interactions[-1]
        logger.debug(f"Retrieved interaction for evaluation: {to_be_evaluated_interaction}")
        return to_be_evaluated_interaction
    
    def _get_matching_expected_answer(self, generation_result: GenerationResult) -> str:
        logger.debug(f"Getting expected answer for generation result {generation_result.id}")
        whole_question_entry = self.dataset_service.get_question_entry_by_id(generation_result.related_question)
        if not whole_question_entry.correct_answer:
            logger.error(f"Cannot evaluate - empty correct answer for question {generation_result.related_question}")
            raise ValueError(f"Can not evaluate since empty correct answer")
        logger.debug(f"Retrieved expected answer: {whole_question_entry.correct_answer}")
        return whole_question_entry.correct_answer
    
    def _get_matching_expected_retrievals(self, generation_result: GenerationResult) -> List[GuidelineReference]:
        logger.debug(f"Getting expected retrievals for generation result {generation_result.id}")
        whole_question_entry = self.dataset_service.get_question_entry_by_id(generation_result.related_question)
        if not whole_question_entry.expected_retrieval:
            logger.warning(f"No expected retrievals found for question {generation_result.related_question}")
            return []
        else:
            retrievals = [
                self.references_service.get_reference_by_id(reference_id=ref_id)
                for ref_id in whole_question_entry.expected_retrieval
            ]
            logger.debug(f"Retrieved {len(retrievals)} expected retrievals")
            return retrievals
    
    def extract_response_latency(self, generation_result: GenerationResult) -> GenerationResult:
        logger.debug(f"Writing response latency for generation result {generation_result.id}")
        eval_i = self._get_to_be_evaluated_interaction(generation_result)
        time_execution_start, time_execution_end = eval_i.time_question_input, eval_i.time_response_output
        
        response_latency = (time_execution_end - time_execution_start).total_seconds()
        logger.info(f"Calculated response latency: {response_latency} seconds")
        
        response_latency_evaluation = EvaluationResponseLatency(
            response_latency=response_latency,
        )
        logger.info(f"Created response latency evaluation: {response_latency_evaluation}")
        updated_result = self.generated_results_service.update_generation_result_entry(
            gen_result_entry_id=generation_result.id,
            update_data={
                "automatic_evaluation.latency_evaluation": response_latency_evaluation,
            },
        )
        return updated_result
    
    async def run_accuracy_analysis(self, generation_result: GenerationResult) -> GenerationResult:
        logger.debug(f"Running accuracy analysis for generation result {generation_result.id}")
        eval_i = self._get_to_be_evaluated_interaction(generation_result)
        provided_answer = eval_i.generator_output
        expected_answer = self._get_matching_expected_answer(generation_result)
        
        if provided_answer and expected_answer:
            try:
                matching_answer = self.dataset_service.get_question_entry_by_id(generation_result.related_question)
                matching_retrievals = []
                for r in matching_answer.expected_retrieval if matching_answer.expected_retrieval else []:
                    reference = self.references_service.get_reference_by_id(r)
                    guideline = self.guideline_service.get_guideline_by_id(reference.guideline_id)
                    content = reference.extract_content()
                    matching_retrievals.append(
                        {"guideline": f"{guideline.awmf_register_number} - {guideline.title}", "content": content},
                    )
                logger.info(f"Retrieved {len(matching_retrievals)} matching retrieval entries")
                logger.debug(matching_retrievals)
                
                def _get_embedding_measures(prediction, reference):
                    logger.info("Computing embedding measures using text-embedding-3-large")
                    embeddings = self.open_ai_3_large_embedder.embed_texts([prediction, reference])
                    pred_emb, ref_emb = np.array(embeddings[0]), np.array(embeddings[1])
                    logger.info("Computing cosine similarity")
                    cos_sim = np.dot(pred_emb, ref_emb) / (np.linalg.norm(pred_emb) * np.linalg.norm(ref_emb))
                    logger.info("Computing euclidean distance")
                    eucl_dist = np.linalg.norm(np.array(pred_emb) - np.array(ref_emb))
                    logger.info(
                        f"Embedding measures - Cosine similarity: {cos_sim}, Euclidean distance: {eucl_dist}",
                    )
                    return {"cosine_similarity": (cos_sim + 1) / 2, "euclidean_distance": eucl_dist}
                
                logger.info("Computing evaluation scores")
                if provided_answer.strip() == "" or expected_answer.strip() == "":
                    if provided_answer.strip() == "" and expected_answer.strip() == "":
                        logger.warning("Both provided and expected answer are empty, setting all scores to 1.0 (since the same)")
                        bleu_score = 1.0
                        rouge_1_score = 1.0
                        rouge_l_score = 1.0
                        meteor_score = 1.0
                        scaled_emb_sim = 1.0
                        euclidean_dist = 0.0
                        bert_score_f1 = 1.0
                        bert_score_precision = 1.0
                        bert_score_recall = 1.0
                        gpt_likert_similarity = 5.0
                    else:
                        logger.warning(
                            f"Either provided string '{provided_answer[:4]}' or expected string '{expected_answer[:4]}' is empty, so no matching scores can be computed. Setting all scores to 0.0 (dist to -1)",
                        )
                        bleu_score = 0.0
                        rouge_1_score = 0.0
                        rouge_l_score = 0.0
                        meteor_score = 0.0
                        scaled_emb_sim = 0.0
                        euclidean_dist = 1.0
                        bert_score_f1 = 0.0
                        bert_score_precision = 0.0
                        bert_score_recall = 0.0
                        gpt_likert_similarity = 1.0
                else:
                    bleu_score = self.bleu_evaluator.compute(
                        predictions=[provided_answer], references=[[expected_answer]],
                    )["bleu"]
                    
                    rouge_1_score, rouge_l_score = (rouge_scores := self.rouge_evaluator.compute(
                        predictions=[provided_answer], references=[expected_answer],
                    ))["rouge1"], rouge_scores["rougeL"]
                    
                    meteor_score = self.meteor_evaluator.compute(
                        predictions=[provided_answer], references=[expected_answer],
                    )[f"meteor"]
                    
                    scaled_emb_sim, euclidean_dist = (emb_scores := _get_embedding_measures(
                        prediction=provided_answer, reference=expected_answer,
                    ))["cosine_similarity"], emb_scores["euclidean_distance"]
                    
                    model_id = os.getenv("BERTSCORE_MODEL_ID", "xlm-roberta-large")
                    bert_score = self.bert_score_evaluator.compute(
                        predictions=[provided_answer],
                        references=[expected_answer],
                        lang="de",
                        model_type=model_id,
                    )
                    bert_score_f1 = bert_score["f1"][0]
                    bert_score_precision = bert_score["precision"][0]
                    bert_score_recall = bert_score["recall"][0]
                    
                    gpt_likert_similarity = (await self.gpt_sim_evaluator.evaluate_similarity_with_reason(
                        question=matching_answer.question, actual_response=provided_answer, expected_answer=expected_answer,
                        expected_retrieval=matching_retrievals,
                    ))["similarity"]
                logger.debug(
                    f"Response from GPT similarity generator: {gpt_likert_similarity}",
                )
                
                logger.info(
                    f"Computed scores - BLEU: {bleu_score:.4f}, ROUGE-1: {rouge_1_score:.4f}, "
                    f"ROUGE-L: {rouge_l_score:.4f}, METEOR: {meteor_score:.4f}, Cos-similarity: {scaled_emb_sim:.4f}, "
                    f"Euclidean-distance: {euclidean_dist:.4f}, BERTScore (de, F1): {bert_score_f1:.4f}, GPT Likert: {gpt_likert_similarity}",
                )
            
            except Exception as e:
                logger.error(f"Error computing evaluation scores: {str(e)}", exc_info=True)
                raise e
        else:
            logger.warning("Missing provided or expected answer, setting all scores to 0.0 (dist to -1)")
            bleu_score = 0.0
            rouge_1_score = 0.0
            rouge_l_score = 0.0
            meteor_score = 0.0
            scaled_emb_sim = 0.0
            euclidean_dist = -1.0
            bert_score_f1 = 0.0
            bert_score_precision = 0.0
            bert_score_recall = 0.0
            gpt_likert_similarity = 1.0
        
        accuracy_evaluation = EvaluationAccuracy(
            bleu_score=bleu_score,
            rouge_1_score=rouge_1_score,
            rouge_l_score=rouge_l_score,
            meteor_score=meteor_score,
            cosine_similarity=scaled_emb_sim,
            euclidean_distance=euclidean_dist,
            bert_score_f1=bert_score_f1,
            bert_score_precision=bert_score_precision,
            bert_score_recall=bert_score_recall,
            gpt_likert_similarity=gpt_likert_similarity,
        )
        updated_result = self.generated_results_service.update_generation_result_entry(
            gen_result_entry_id=generation_result.id,
            update_data={
                "automatic_evaluation.accuracy_evaluation": accuracy_evaluation,
            },
        )
        return updated_result
    
    @staticmethod
    def _string_to_unit_count(string: str) -> int:
        """Count the number of non-whitespace characters and log it."""
        cleaned = ''.join(string.split())
        count = len(cleaned)
        logger.debug(f"Counting {count} non-whitespace characters in: '{string[:25]}...'")
        return count
    
    # noinspection DuplicatedCode
    def run_retrieval_performance_analysis(self, generation_result: GenerationResult) -> GenerationResult:
        logger.info(f"Running retrieval performance analysis for generation result {generation_result.id}")
        eval_i = self._get_to_be_evaluated_interaction(generation_result)
        expected_retrieval = self._get_matching_expected_retrievals(generation_result)
        provided_retrieval = [
            self.references_service.get_reference_by_id(r.reference_id)
            for r in eval_i.retrieval_output if r.reference_id
        ]
        provided_wo_refs = [r for r in eval_i.retrieval_output if not r.reference_id]
        
        # Normalize -> we want to ignore any white spaces AND have equivalent bullet points (*-•)
        er_guidelines_and_texts = []
        pr_guidelines_and_texts = []
        
        def _clean_text(text) -> str:
            s = unicodedata.normalize("NFKC", str(text).strip())
            
            # Glyph sets to remove (ignore)
            _BULLET_GLYPHS = '•·⋅◦▪▫‣⁃●○►▸▹'
            _DQUOTES = '"“”„«»‟″'
            _SQUOTES = "'’‘ʼ′`"  # common apostrophes/quotes
            
            # Normalize newlines
            s = s.replace('\r\n', '\n').replace('\r', '\n')
            
            # 1) Remove line-start bullet markers like "- " or "* " or any bullet glyph + spaces (multiline safe)
            bullet_class = re.escape(_BULLET_GLYPHS)
            s = re.sub(rf'(?m)^\s*([\-*{bullet_class}])\s+', '', s)
            
            # 2) Delete standalone bullet glyphs and all quote variants anywhere
            delete_map = {ord(c): None for c in (_BULLET_GLYPHS + _DQUOTES + _SQUOTES)}
            s = s.translate(delete_map)
            
            # 3) Collapse whitespace (incl. tabs/newlines & NBSP) to a single space
            s = s.replace('\u00A0', ' ')
            s = re.sub(r'\s+', ' ', s).strip()
            
            return s
        
        for er in expected_retrieval:
            content = er.extract_content() or ""
            if er.type == ReferenceType.RECOMMENDATION:
                content = er.recommendation_content
            elif er.type == ReferenceType.STATEMENT:
                content = er.statement_content
            elif er.type == ReferenceType.TABLE:
                content = er.caption
            elif er.type == ReferenceType.IMAGE:
                content = er.caption
            er_guidelines_and_texts.append(
                {
                    "gl": er.guideline_id,
                    "text": _clean_text(content),
                },
            )
        for pr in provided_retrieval:
            content = pr.extract_content() or ""
            if pr.type == ReferenceType.RECOMMENDATION:
                content = pr.recommendation_content
            elif pr.type == ReferenceType.STATEMENT:
                content = pr.statement_content
            elif pr.type == ReferenceType.TABLE:
                content = pr.caption
            elif pr.type == ReferenceType.IMAGE:
                content = pr.caption
            pr_guidelines_and_texts.append(
                {
                    "gl": pr.guideline_id,
                    "text": _clean_text(content),
                },
            )
        for pr in provided_wo_refs:
            pr_guidelines_and_texts.append(
                {
                    "gl": pr.source_id,
                    "text": _clean_text(pr.retrieval or ""),
                },
            )
        
        logger.info(f"Retrieved {len(er_guidelines_and_texts)} expected and {len(pr_guidelines_and_texts)} provided retrievals")
        
        logger.info("Computing retrieval metrics")
        tp_strings, fn_strings, fp_strings = self._get_tp_fp_fn_strings(
            er_guidelines_and_texts, pr_guidelines_and_texts,
        )
        
        logger.debug(f"EXPECTED RETRIEVALS: {er_guidelines_and_texts}")
        tp = sum(self._string_to_unit_count(s) for s in tp_strings)
        fn = sum(self._string_to_unit_count(s) for s in fn_strings)
        fp = sum(self._string_to_unit_count(s) for s in fp_strings)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        logger.info(f"Computed metrics - TP: {tp}, FP: {fp}, FN: {fn}")
        logger.info(f"Final scores - Precision: {precision:.2f}, Recall: {recall:.2f}, F1: {f1:.2f}")
        
        evaluation = EvaluationRetrieval(
            retrieval_latency=eval_i.retrieval_latency,
            precision=precision,
            recall=recall,
            f1=f1,
        )
        
        logger.info(f"Created retrieval evaluation: {evaluation}")
        return self.generated_results_service.update_generation_result_entry(
            gen_result_entry_id=generation_result.id,
            update_data={"automatic_evaluation.retrieval_evaluation": evaluation},
        )
    
    @staticmethod
    def _get_tp_fp_fn_strings(
            er_guidelines_and_texts, pr_guidelines_and_texts,
    ) -> Tuple[List[str], List[str], List[str]]:
        
        # noinspection PyShadowingNames
        def get_lcs(s1: str, s2: str) -> Optional[str]:
            matcher = difflib.SequenceMatcher(None, s1, s2)
            match = matcher.find_longest_match(0, len(s1), 0, len(s2))
            if match.size == 0:
                logger.debug(f"[LCS] No common substring found between:\n  ER: {s1[:50]}...\n  PR: {s2[:50]}...")
                return None
            lcs = s1[match.a:match.a + match.size]
            logger.debug(f"[LCS] Found LCS '{lcs}' (len={len(lcs)}) at ER[{match.a}] and PR[{match.b}]")
            return lcs
        
        tp_strings = []
        
        er_index = 0
        while er_index < len(er_guidelines_and_texts):
            er_gl, er_text = er_guidelines_and_texts[er_index]["gl"], er_guidelines_and_texts[er_index]["text"]
            
            pr_index = 0
            while pr_index < len(pr_guidelines_and_texts):
                pr_gl, pr_text = pr_guidelines_and_texts[pr_index]["gl"], pr_guidelines_and_texts[pr_index]["text"]
                
                if er_gl != pr_gl:
                    pr_index += 1
                    continue
                
                lcs = get_lcs(er_text, pr_text)
                if lcs is None:
                    pr_index += 1
                    continue
                
                # Match one of the cases
                # 1: PR = ... + ER + ...
                if pr_text == lcs:
                    tp_strings.append(pr_text)
                    pr_guidelines_and_texts[pr_index] = {"gl": pr_gl, "text": ""}
                    remaining_er_texts = er_text.split(pr_text)
                    er_guidelines_and_texts[er_index] = {"gl": er_gl, "text": remaining_er_texts[0]}
                    er_guidelines_and_texts.insert(er_index + 1, {"gl": er_gl, "text": remaining_er_texts[1]})
                
                # 2>: ... + PR + ... = ER
                elif er_text == lcs:
                    tp_strings.append(er_text)
                    er_guidelines_and_texts[er_index] = {"gl": er_gl, "text": ""}
                    remaining_pr_texts = pr_text.split(er_text)
                    pr_guidelines_and_texts[pr_index] = {"gl": pr_gl, "text": remaining_pr_texts[0]}
                    pr_guidelines_and_texts.insert(pr_index + 1, {"gl": pr_gl, "text": remaining_pr_texts[1]})
                
                # 3: PR + ... = ... + ER
                elif pr_text.startswith(lcs) and er_text.endswith(lcs):
                    tp_strings.append(lcs)
                    er_guidelines_and_texts[er_index] = {"gl": er_gl, "text": er_text[:-len(lcs)]}
                    pr_guidelines_and_texts[pr_index] = {"gl": pr_gl, "text": pr_text[len(lcs):]}
                
                # 4: ... + PR = ER + ...
                elif pr_text.endswith(lcs) and er_text.startswith(lcs):
                    tp_strings.append(lcs)
                    er_guidelines_and_texts[er_index] = {"gl": er_gl, "text": er_text[len(lcs):]}
                    pr_guidelines_and_texts[pr_index] = {"gl": pr_gl, "text": pr_text[:-len(lcs)]}
                
                else:
                    logger.warning(f"Found no matching case for longest common substring '{lcs}'")
                
                pr_index += 1
            
            er_index += 1
        
        fp_strings = []
        for pr_text in pr_guidelines_and_texts:
            if pr_text["text"]:
                fp_strings.append(pr_text["text"])
        
        fn_strings = []
        for er_text in er_guidelines_and_texts:
            if er_text["text"]:
                fn_strings.append(er_text["text"])
        
        return tp_strings, fn_strings, fp_strings
