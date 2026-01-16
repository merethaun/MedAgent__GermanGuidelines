from abc import ABC
from typing import Dict, Any, Type, Optional

from app.services.knowledge.vector import AdvancedDBService
from app.services.system.components.post_processor.abstract_post_processor import AbstractPostProcessor
from app.utils.logger import setup_logger
from app.utils.service_creators import get_advanced_db_service

logger = setup_logger(__name__)


class ChunkFilterProcessor(AbstractPostProcessor, ABC, variant_name="chunk_filter"):
    variants: Dict[str, Type['ChunkFilterProcessor']] = {}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.advanced_vector_service: AdvancedDBService = get_advanced_db_service()
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            ChunkFilterProcessor.variants[variant_name] = cls
