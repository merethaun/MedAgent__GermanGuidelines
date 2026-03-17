from app.services.system.components import AbstractComponent
from app.services.system.components.filter import AbstractFilter
from app.services.system.components.generator import LLMGenerator
from app.services.system.components.query_transformer import AbstractQueryTransformer
from app.services.system.components.retriever import AbstractRetriever
from app.services.system.components.structure import EndComponent, StartComponent

AbstractComponent.variants = {
    # Structure components
    "start": StartComponent,
    "end": EndComponent,
    
    # Tools
    "generator": LLMGenerator,
    "filter": AbstractFilter,
    "query_transformer": AbstractQueryTransformer,
    "retriever": AbstractRetriever,
}

# Tool variants
