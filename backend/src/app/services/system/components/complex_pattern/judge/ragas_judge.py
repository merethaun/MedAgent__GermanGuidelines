import asyncio
import os
from typing import Dict, Any, List

from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import (
    ResponseRelevancy, ContextRelevance, ResponseGroundedness, Faithfulness, FaithfulnesswithHHEM, AspectCritic, SimpleCriteriaScore,
)

from app.services.system.components.complex_pattern.judge.abstract_judge import AbstractJudge
from app.utils.logger import setup_logger
from app.utils.ragas_integration.embedder_interaction import AzureOpenAI_RagasEmbeddings, HuggingFaceEmbeddingsLocal
from app.utils.ragas_integration.llm_interaction import AzureOpenAI_RagasLLM, Ollama_RagasLLM

logger = setup_logger(__name__)


class RAGAsJudge(AbstractJudge, variant_name="ragas"):
    default_parameters: Dict[str, Any] = {
        **AbstractJudge.default_parameters,
        "generator_backend": "azure",  # "azure" | "ollama"
        "embedding_backend": "huggingface",  # "azure" | "huggingface"
        # Azure LLM config
        "azure_api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
        "azure_api_base": os.getenv("AZURE_OPENAI_API_BASE", ""),
        "azure_api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        "azure_chat_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1"),
        "azure_temperature": 0.0,
        "azure_max_tokens": 1024,
        # Ollama LLM config
        "ollama_api_base": os.getenv("WARHOL_OLLAMA_API_BASE", "http://localhost:11434"),
        "ollama_model": "llama3.3:70b",
        "ollama_temperature": 0.7,
        "ollama_max_tokens": 1024,
        "ollama_timeout_seconds": 120.0,
        "ollama_think": False,
        # Azure embeddings config (also uses api key)
        "azure_embeddings_deployment": None,  # e.g., "text-embedding-3-large"
        # HuggingFace local embeddings config
        "hf_model_name": "sentence-transformers/all-MiniLM-L6-v2",
        "hf_device": None,  # "cpu" | "cuda" | "mps" | None
        "hf_normalize": True,
        "hf_batch_size": 32,
        # Metrics controls
        "evaluate_response_relevancy": True,
        "evaluate_context_relevance": True,
        "evaluate_response_groundedness": True,
        "evaluate_faithfulness": True,
        "faithfulness_use_hhem": False,  # use the HHEM variant if True
        "aspect_critics": [],
        "simple_criteria": [],
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.llm = None
        self.embeddings = None
        
        p: Dict = {**self.default_parameters, **(parameters or {})}
        
        backend = (p.get("generator_backend") or "azure").lower()
        if backend == "azure":
            self.llm = AzureOpenAI_RagasLLM(
                api_key=p["azure_api_key"], azure_endpoint=p["azure_api_base"], api_version=p["azure_api_version"],
                deployment=p["azure_chat_deployment"], temperature=float(p["azure_temperature"]), max_tokens=int(p["azure_max_tokens"]),
            )
        elif backend == "ollama":
            self.llm = Ollama_RagasLLM(
                api_base=p["ollama_api_base"], model=p["ollama_model"], temperature=float(p["ollama_temperature"]),
                max_tokens=int(p["ollama_max_tokens"]), request_timeout=float(p["ollama_timeout_seconds"]), think=bool(p["ollama_think"]),
            )
        else:
            raise ValueError(f"Unsupported generator_backend: {backend}")
        
        emb_backend = (p.get("embedding_backend") or "huggingface").lower()
        if emb_backend == "azure":
            self.embeddings = AzureOpenAI_RagasEmbeddings(
                api_key=p["azure_api_key"], azure_endpoint=p["azure_api_base"], api_version=p["azure_api_version"],
                deployment=p["azure_embeddings_deployment"],
            )
        elif emb_backend == "huggingface":
            self.embeddings = HuggingFaceEmbeddingsLocal(
                model_name=p.get("hf_model_name", "sentence-transformers/all-MiniLM-L6-v2"),
                device=p.get("hf_device"), normalize=bool(p.get("hf_normalize", True)), batch_size=int(p.get("hf_batch_size", 32)),
            )
        else:
            raise ValueError(f"Unsupported embedding_backend: {emb_backend}")
        
        self.criteria_eval = {
            "response_relevancy": bool(p.get("evaluate_response_relevancy", True)),
            "context_relevance": bool(p.get("evaluate_context_relevance", True)),
            "response_groundedness": bool(p.get("evaluate_response_groundedness", True)),
            "faithfulness": bool(p.get("evaluate_faithfulness", True)),
            "faithfulness_use_hhem": bool(p.get("faithfulness_use_hhem", False)),
            "aspect_critics": p.get("aspect_critics") or [],
            "simple_criteria": p.get("simple_criteria") or [],
            "reference_key": p.get("reference_key", "reference"),
        }
        
        if self.criteria_eval["response_relevancy"] and self.embeddings is None:
            raise ValueError(f"ResponseRelevancy requested but embeddings are not configured.")
    
    def response_relevancy(self, sample: SingleTurnSample) -> float:
        """
        Evaluates how relevant the model's RESPONSE is to the USER QUERY.
        - 1.0 = fully relevant; 0.0 = irrelevant.
        - Requires an embedding model.
        """
        assert self.embeddings is not None, "ResponseRelevancy needs embeddings"
        metric = ResponseRelevancy(llm=self.llm, embeddings=self.embeddings)
        value = asyncio.run(metric.single_turn_ascore(sample))
        return max(0.0, min(1.0, (value + 1.0) / 2.0))
    
    def context_relevance(self, sample: SingleTurnSample) -> float:
        """
        Evaluates how relevant the RETRIEVED CONTEXT is to the USER QUERY.
        - 1.0 = highly relevant; 0.0 = noisy/irrelevant.
        """
        metric = ContextRelevance(llm=self.llm)
        value = asyncio.run(metric.single_turn_ascore(sample))
        return value
    
    def response_groundedness(self, sample: SingleTurnSample) -> float:
        """
        Evaluates how well the RESPONSE is SUPPORTED by the CONTEXT.
        - 1.0 = fully grounded; 0.0 = hallucinated.
        """
        metric = ResponseGroundedness(llm=self.llm)
        value = asyncio.run(metric.single_turn_ascore(sample))
        return value
    
    def faithfulness(self, sample: SingleTurnSample, use_hhem=True) -> float:
        """
        Evaluates whether all claims in the RESPONSE are supported by CONTEXT.
        - With HHEM enabled, a hierarchical hallucination evaluator is used.
        """
        metric = FaithfulnesswithHHEM(llm=self.llm) if use_hhem else Faithfulness(llm=self.llm)
        return asyncio.run(metric.single_turn_ascore(sample))
    
    def aspect_critic(self, sample: SingleTurnSample, name: str, definition: str) -> float:
        """
        Evaluates whether the RESPONSE satisfies a custom ASPECT/CONSTRAINT. -> Focus on yes, no decisions
        - Returns 1.0 if satisfied, else 0.0 (depending on metric behavior).
        """
        metric = AspectCritic(name=name, definition=definition, llm=self.llm)
        return asyncio.run(metric.single_turn_ascore(sample))
    
    def simple_criteria(self, sample: SingleTurnSample, *, name: str, definition: str) -> float:
        """
        Evaluates a user-defined SIMPLE CRITERION (0..1 or int-like score depending on definition). -> Focus on scalar custom scores
        """
        metric = SimpleCriteriaScore(name=name, definition=definition, llm=self.llm)
        return float(asyncio.run(metric.single_turn_ascore(sample)))
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        
        ragas_params = {
            "generator_backend": {
                "type": "string",
                "description": "LLM backend to use.",
                "enum": ["azure", "ollama"],
                "default": "azure",
            },
            "embedding_backend": {
                "type": "string",
                "description": "Embedding backend to use.",
                "enum": ["azure", "huggingface"],
                "default": "huggingface",
            },
            # Metrics selection
            "evaluate_response_relevancy": {"type": "boolean", "description": "Compute ResponseRelevancy.", "default": True},
            "evaluate_context_relevance": {"type": "boolean", "description": "Compute ContextRelevance.", "default": True},
            "evaluate_response_groundedness": {"type": "boolean", "description": "Compute ResponseGroundedness.", "default": True},
            "evaluate_faithfulness": {"type": "boolean", "description": "Compute Faithfulness.", "default": True},
            "faithfulness_use_hhem": {"type": "boolean", "description": "Use HHEM variant for Faithfulness.", "default": False},
            "aspect_critics": {
                "type": "list",
                "description": "List of custom aspects: [{'name': str, 'definition': str}, ...].",
                "default": [],
            },
            "simple_criteria": {
                "type": "list",
                "description": "List of custom simple criteria: [{'name': str, 'definition': str}, ...].",
                "default": [],
            },
        }
        
        gen_azure_params = {
            "azure_api_key": {"type": "string", "description": "Azure OpenAI API key."},
            "azure_api_base": {"type": "string", "description": "Azure OpenAI endpoint, e.g., https://<resource>.openai.azure.com"},
            "azure_api_version": {"type": "string", "description": "Azure OpenAI API version.", "default": "2024-06-01"},
            "azure_chat_deployment": {"type": "string", "description": "Azure chat deployment name."},
            "azure_temperature": {"type": "number", "description": "Sampling temperature.", "default": 0.0},
            "azure_max_tokens": {"type": "integer", "description": "Max tokens (completion).", "default": 512},
        }
        embedder_azure_params = {
            "azure_embeddings_deployment": {"type": "string", "description": "Azure embeddings deployment name (e.g., text-embedding-3-large)."},
            
        }
        
        gen_ollama_params = {
            "ollama_api_base": {"type": "string", "description": "Ollama base URL.", "default": "http://localhost:11434"},
            "ollama_model": {"type": "string", "description": "Ollama model name.", "default": "deepseek-r1:7b"},
            "ollama_temperature": {"type": "number", "description": "Sampling temperature.", "default": 0.7},
            "ollama_max_tokens": {"type": "integer", "description": "Num tokens to predict.", "default": 256},
            "ollama_timeout_seconds": {"type": "number", "description": "HTTP timeout seconds.", "default": 120.0},
            "ollama_think": {"type": "boolean", "description": "Enable 'think' option.", "default": False},
            
        }
        embedder_huggingface_params = {
            "hf_model_name": {
                "type": "string", "description": "HF sentence-transformers or HF model id.", "default": "sentence-transformers/all-MiniLM-L6-v2",
            },
            "hf_device": {"type": "string", "description": "Device: cpu|cuda|mps (optional).", "default": None},
            "hf_normalize": {"type": "boolean", "description": "L2-normalize embeddings.", "default": True},
            "hf_batch_size": {"type": "integer", "description": "Batch size for encoding.", "default": 32},
            
        }
        
        return {
            **base_params, **ragas_params, **gen_azure_params, **embedder_azure_params, **gen_ollama_params, **embedder_huggingface_params,
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_output_spec()
        base_params.update(
            {
                "ragas.response_relevancy": {"type": "number", "description": "RAGAS ResponseRelevancy score [0..1]."},
                "ragas.context_relevance": {"type": "number", "description": "RAGAS ContextRelevance score [0..1]."},
                "ragas.response_groundedness": {"type": "number", "description": "RAGAS ResponseGroundedness score [0..1]."},
                "ragas.faithfulness": {"type": "number", "description": "RAGAS Faithfulness score [0..1]."},
                "ragas.aspect_scores": {"type": "dict", "description": "Scores per AspectCritic as {name: score}."},
                "ragas.criteria_scores": {"type": "dict", "description": "Scores per SimpleCriteria as {name: score}."},
            },
        )
        return base_params
    
    def judge(self, query: str, current_retrieval: List[str], current_response: str, data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"{self.id}: Starting evaluation")
        
        sample = SingleTurnSample(
            user_input=str(query or ""), response=str(current_response or ""), retrieved_contexts=current_retrieval, reference=current_response,
        )
        
        if self.criteria_eval["response_relevancy"]:
            try:
                if not current_response:
                    response_relevancy_score = 0.0
                else:
                    logger.info(f"{self.id}: Evaluating response relevancy")
                    response_relevancy_score = self.response_relevancy(sample)
                data[f"{self.id}.response_relevancy"] = response_relevancy_score
                logger.info(f"{self.id}: Response relevancy score: {data[f'{self.id}.response_relevancy']}")
            except Exception as e:
                logger.error(f"ResponseRelevancy failed: {e}", exc_info=True)
                raise ValueError(f"ResponseRelevancy failed: {e}") from e
        
        if self.criteria_eval["context_relevance"]:
            try:
                if not current_retrieval:
                    context_relevance_score = 0.0
                else:
                    logger.info(f"{self.id}: Evaluating context relevance")
                    context_relevance_score = self.context_relevance(sample)
                data[f"{self.id}.context_relevance"] = context_relevance_score
                logger.info(f"{self.id}: Context relevance score: {data[f'{self.id}.context_relevance']}")
            except Exception as e:
                logger.error(f"ContextRelevancy failed: {e}", exc_info=True)
                raise ValueError(f"ContextRelevancy failed: {e}") from e
        
        if self.criteria_eval["response_groundedness"]:
            try:
                if not current_response or not current_retrieval:
                    response_groundedness_score = 0.0
                else:
                    logger.info(f"{self.id}: Evaluating response groundedness")
                    response_groundedness_score = self.response_groundedness(sample)
                data[f"{self.id}.response_groundedness"] = response_groundedness_score
                logger.info(f"{self.id}: Response groundedness score: {data[f'{self.id}.response_groundedness']}")
            except Exception as e:
                logger.error(f"ResponseGroundedness failed: {e}", exc_info=True)
                raise ValueError(f"ResponseGroundedness failed: {e}") from e
        
        if self.criteria_eval["faithfulness"]:
            try:
                if not current_response or not current_retrieval:
                    faithfulness_score = 0.0
                else:
                    logger.info(f"{self.id}: Evaluating faithfulness")
                    faithfulness_score = self.faithfulness(sample, use_hhem=self.criteria_eval["faithfulness_use_hhem"])
                data[f"{self.id}.faithfulness"] = faithfulness_score
                logger.info(f"{self.id}: Faithfulness score: {data[f'{self.id}.faithfulness']}")
            except Exception as e:
                logger.error(f"Faithfulness failed: {e}", exc_info=True)
                data[f"{self.id}.faithfulness"] = None
        
        if self.criteria_eval["aspect_critics"]:
            logger.info(f"{self.id}: Evaluating aspect critics")
            data[f"{self.id}.aspect_critics"] = {}
            for aspect in self.criteria_eval["aspect_critics"]:
                try:
                    name = aspect.get("name")
                    definition = aspect.get("definition")
                    if name and definition:
                        logger.info(f"{self.id}: Evaluating aspect critic '{name}'")
                        score = self.aspect_critic(sample, name=name, definition=definition)
                        data[f"{self.id}.aspect_critics"][name] = score
                        logger.info(f"{self.id}: Aspect critic '{name}' score: {score}")
                    else:
                        raise ValueError(f"AspectCritic '{aspect}' missing name or definition.")
                except Exception as e:
                    logger.error(f"AspectCritic '{aspect}' failed: {e}", exc_info=True)
        
        if self.criteria_eval["simple_criteria"]:
            logger.info(f"{self.id}: Evaluating simple criteria")
            data[f"{self.id}.simple_criteria"] = {}
            for crit in self.criteria_eval["simple_criteria"]:
                try:
                    name = crit.get("name")
                    definition = crit.get("definition")
                    if name and definition:
                        logger.info(f"{self.id}: Evaluating simple criterion '{name}'")
                        score = self.simple_criteria(sample, name=name, definition=definition)
                        data[f"{self.id}.simple_criteria"][name] = score
                        logger.info(f"{self.id}: Simple criterion '{name}' score: {score}")
                    else:
                        raise ValueError(f"SimpleCriteria '{crit}' missing name or definition.")
                except Exception as e:
                    logger.error(f"SimpleCriteria '{crit}' failed: {e}", exc_info=True)
            logger.debug(data)
        
        logger.info(f"{self.id}: Evaluation complete")
        return data
