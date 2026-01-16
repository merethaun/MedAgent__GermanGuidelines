from abc import abstractmethod
from typing import Dict, Any, Tuple, Type, Optional, List

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AbstractKeywordExtractor(AbstractComponent, variant_name="keyword_extractor"):
    variants: Dict[str, Type["AbstractKeywordExtractor"]] = {}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: Optional[str] = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id: Optional[str] = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractKeywordExtractor.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):  # noqa: D401
        """No-op for now; hook to restore previous state if desired."""
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        """Parameters common to all keyword extractors.
        
        Notes:
        - `text` can reference variables in the workflow context and will be template-rendered.
        """
        return {
            "text": {
                "type": "string",
                "description": (
                    "Text to extract keyphrases from (will be resolved with the variables specified)."
                ),
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "extractor.text": {
                "type": "string",
                "description": "The text used for extraction, available under the component namespace.",
            },
            "extractor.keywords": {
                "type": "list",
                "description": "List of extracted, normalized, deduplicated keyphrases (ranked).",
            },
        }
    
    @abstractmethod
    def extract(self, text: str, data: Dict[str, Any]) -> List[str]:
        """Return (keywords, latency). Must be implemented by subclasses."""
        raise NotImplementedError
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            logger.info(f"[KeywordExtractor] Starting execution for {self.__class__.__name__} (ID: {self.id})")
            text_template = self.parameters.get("text", "")
            text: str = render_template(text_template, data) if isinstance(text_template, str) else str(text_template)
            
            if not text or not str(text).strip():
                logger.warning("[KeywordExtractor] Empty text input; returning empty keywords.")
                data[f"{self.id}.text"] = text or ""
                data[f"{self.id}.keywords"] = []
                return data, self.next_component_id
            
            data[f"{self.id}.text"] = text
            
            keywords = self.extract(text=text, data=data)
            logger.info(f"[KeywordExtractor] Extracted {len(keywords) if keywords else 0} keywords")
            data[f"{self.id}.keywords"] = keywords or []
            
            logger.info("[KeywordExtractor] Execution completed successfully")
            return data, self.next_component_id
        
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"[KeywordExtractor] Error details: {str(e)}", exc_info=True)
            raise RuntimeError(f"Keyword extractor execution failed: {e}")
