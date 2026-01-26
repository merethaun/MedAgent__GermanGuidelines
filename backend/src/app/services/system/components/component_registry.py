from app.services.system.components import AbstractComponent
from app.services.system.components.structure import EndComponent, StartComponent

AbstractComponent.variants = {
    "start": StartComponent,
    "end": EndComponent,
}
