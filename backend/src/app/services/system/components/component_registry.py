from app.services.system.components import AbstractComponent
from app.services.system.components.decision import AbstractDecisionComponent
from app.services.system.components.expander import AbstractExpander
from app.services.system.components.filter import AbstractFilter
from app.services.system.components.generator import LLMGenerator
from app.services.system.components.query_transformer import AbstractQueryTransformer
from app.services.system.components.retriever import AbstractRetriever
from app.services.system.components.structure import DeciderComponent, EndComponent, ListComponent, MergeComponent, StartComponent

AbstractComponent.variants = {
    # Structure components
    "start": StartComponent,
    "end": EndComponent,
    "list": ListComponent,
    "merge": MergeComponent,
    "decider": DeciderComponent,
    
    # Tools
    "decision": AbstractDecisionComponent,
    "generator": LLMGenerator,
    "expander": AbstractExpander,
    "filter": AbstractFilter,
    "query_transformer": AbstractQueryTransformer,
    "retriever": AbstractRetriever,
}

# Tool variants
