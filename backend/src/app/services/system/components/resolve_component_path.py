from typing import List, Type

from app.services.system.components import AbstractComponent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _resolve_base_class(base_type: str) -> Type[AbstractComponent]:
    logger.debug(f"Resolving base class for base_type: {base_type}")
    if base_type not in AbstractComponent.variants:
        raise ValueError(f"No base component class found for '{base_type}'")
    return AbstractComponent.variants[base_type]


def resolve_component_path(path: List[str]) -> Type[AbstractComponent]:
    logger.debug(f"Resolving component path: {path}")
    current_cls = _resolve_base_class(path[0])
    for variant_name in path[1:]:
        # logger.debug(f"Checking variant '{variant_name}' for class '{current_cls.__name__}'.")
        if not hasattr(current_cls, "variants") or not isinstance(current_cls.variants, dict):
            raise TypeError(f"'{current_cls.__name__}' must define a 'variants' dictionary.")
        if variant_name not in current_cls.variants:
            raise ValueError(
                f"Variant '{variant_name}' not found in '{current_cls.__name__}'. Available: {list(current_cls.variants.keys())}",
            )
        current_cls = current_cls.variants[variant_name]
    logger.debug(f"Found variant '{current_cls.__name__}'")
    return current_cls
