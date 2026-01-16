from typing import Dict, Any, Tuple, List, Optional

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.models.system.complex_pattern.adapt_models import Action, RAGAsResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ActionTrackerComponent(AbstractComponent, variant_name="action_tracker"):
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        self.next_component_id = None
        
        self.actions: List[Action] = []
        self.retrieval: List[WeaviateSearchChunkResult] = []
        self.generation_result: str = ""
        
        self.retrieval_template = self.parameters["retrieval"]
        self.filter_result_template = self.parameters["filter_result"]
        self.generation_template = self.parameters["generation"]
        self.last_action_template = self.parameters["last_action"]
        self.last_scoring_template = self.parameters.get("last_scoring")
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "retrieval": {
                "type": "str",
                "description": "Template for how to get to retrieval (especially in first iterations, can also return empty).",
            },
            "filter_result": {
                "type": "str",
                "description": "Template for how to get to filter result (especially in first iterations, can also return empty).",
            },
            "generation": {
                "type": "str",
                "description": "Template for how to get to generation result (especially in first iterations, can also return empty).",
            },
            "last_action": {
                "type": "str",
                "description": "Template for how to get to last executed action -> rendered of type Action",
            },
            "last_scoring": {
                "type": "str",
                "description": "Template for how to get to last scoring result (especially in first iterations, can also return empty).",
                "default": None,
            },
        }
    
    def _get_score(self, data: Dict[str, Any]) -> Optional[RAGAsResult]:
        score_result = render_template(self.last_scoring_template, data)
        if score_result is None:
            return None
        
        if isinstance(score_result, RAGAsResult):
            return score_result
        elif isinstance(score_result, dict):
            return RAGAsResult(**score_result)
        else:
            raise TypeError(f"Last scoring result must be of type 'RAGAsResult', but is {type(score_result)}")
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        last_action: Optional[Action] = render_template(self.last_action_template, data)
        last_scoring_result: Optional[RAGAsResult] = self._get_score(data)
        
        if last_action is not None:
            if last_action.action_type == "retrieve":
                self.retrieval = render_template(self.retrieval_template, data)
                self.generation_result = ""
                logger.debug(f"Found last action to be retrieve -> update {len(self.retrieval)} results; reset generation;")
            elif last_action.action_type == "filter":
                self.retrieval = render_template(self.filter_result_template, data)
                logger.debug(f"Found last action to be filter -> update {len(self.retrieval)} results")
            elif last_action.action_type == "generate":
                self.generation_result = render_template(self.generation_template, data)
                logger.debug(f"Found last action to be generation -> update generation")
            else:
                raise ValueError(f"Unknown action type: {last_action.action_type}")
            
            if last_scoring_result is None:
                logger.warning("!!Not using scoring")
            else:
                last_action.score = last_scoring_result
            
            self.actions.append(last_action)
            logger.debug(f"Found last action to be {last_action.action_type} -> update action list")
        
        data[f"{self.id}.actions"] = self.actions
        data[f"{self.id}.retrieval"] = self.retrieval
        data[f"{self.id}.generation_result"] = self.generation_result
        
        return data, self.next_component_id
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "action_tracker.actions": {
                "type": List[Action],
                "description": "Tracks the action with their settings + results (in form of scores) -> can track progress",
            },
            "retrieval": {
                "type": List[WeaviateSearchChunkResult],
                "description": "The current retrieval result",
            },
            "generation_result": {
                "type": str,
                "description": "The current generation result",
            },
        }
