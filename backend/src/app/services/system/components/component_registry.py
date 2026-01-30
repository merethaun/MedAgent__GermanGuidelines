from app.services.system.components import AbstractComponent
from app.services.system.components.generator import LLMGenerator
from app.services.system.components.structure import EndComponent, StartComponent

AbstractComponent.variants = {
    # Structure components
    "start": StartComponent,
    "end": EndComponent,
    
    # Tools
    "generator": LLMGenerator,
}

# Tool variants
