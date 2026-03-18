from typing import Any, Dict, List, Tuple

from app.models.knowledge.guideline.guideline_reference import GuidelineReference
from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


class MergeComponent(AbstractComponent, variant_name="merge"):
    default_parameters: Dict[str, Any] = {
        "items": [],
        "item_key": None,
        "latency_key": "latency",
        "deduplicate": True,
        "dedupe_key": None,
        "limit": None,
    }

    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "items": {
                "type": "list",
                "description": "List of lists or list of dicts that should be merged.",
            },
            "item_key": {
                "type": "string",
                "description": "Optional key extracted from each top-level item before flattening, e.g. 'references'.",
            },
            "latency_key": {
                "type": "string",
                "description": "Optional key summed across top-level items to provide aggregate retrieval latency.",
                "default": "latency",
            },
            "deduplicate": {
                "type": "bool",
                "description": "If true, remove duplicate merged items.",
                "default": True,
            },
            "dedupe_key": {
                "type": "string",
                "description": "Optional dotted path used as a custom deduplication key.",
            },
            "limit": {
                "type": "int",
                "description": "Optional cap applied after merging and deduplication.",
            },
        }

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "merge.items": {
                "type": "list",
                "description": "Merged items after flattening, deduplication, and optional limiting.",
            },
            "merge.references": {
                "type": "list",
                "description": "Alias for merged retrieval results.",
            },
            "merge.latency": {
                "type": "float",
                "description": "Summed latency across top-level items when latency_key is present.",
            },
            "merge.total_input_items": {
                "type": "int",
                "description": "Total number of flattened input items before deduplication.",
            },
            "merge.merged_count": {
                "type": "int",
                "description": "Number of merged items after deduplication and optional limiting.",
            },
        }

    @staticmethod
    def _ensure_iterable_items(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

    @staticmethod
    def _resolve_dotted_path(item: Any, path: str) -> Any:
        current = item
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
            if current is None:
                return None
        return current

    @staticmethod
    def _default_dedupe_key(item: Any) -> str:
        if isinstance(item, GuidelineReference):
            if getattr(item, "id", None) is not None:
                return f"reference:{item.id}"
            return f"guideline:{item.guideline_id}|type:{item.type.value}|text:{item.extract_content()}"
        if isinstance(item, dict):
            for candidate in ("id", "_id", "reference_id", "uuid", "weaviate_uuid"):
                value = item.get(candidate)
                if value is not None:
                    return f"{candidate}:{value}"
        if hasattr(item, "id") and getattr(item, "id", None) is not None:
            return f"id:{getattr(item, 'id')}"
        return str(item)

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        raw_items = self.parameters.get("items", self.default_parameters["items"])
        resolved_items = render_template(raw_items, data) if isinstance(raw_items, str) else raw_items
        top_level_items = self._ensure_iterable_items(resolved_items)
        item_key = self.parameters.get("item_key", self.default_parameters["item_key"])
        latency_key = self.parameters.get("latency_key", self.default_parameters["latency_key"])
        custom_dedupe_key = self.parameters.get("dedupe_key", self.default_parameters["dedupe_key"])
        deduplicate = bool(self.parameters.get("deduplicate", self.default_parameters["deduplicate"]))
        limit = self.parameters.get("limit", self.default_parameters["limit"])

        merged_items: List[Any] = []
        total_latency = 0.0

        for entry in top_level_items:
            if latency_key and isinstance(entry, dict):
                try:
                    total_latency += float(entry.get(latency_key) or 0.0)
                except (TypeError, ValueError):
                    logger.debug("Skipping non-numeric latency value in MergeComponent entry: %r", entry.get(latency_key))

            nested_items = entry.get(item_key) if item_key and isinstance(entry, dict) else entry
            merged_items.extend(self._ensure_iterable_items(nested_items))

        total_input_items = len(merged_items)
        if deduplicate:
            unique_items: List[Any] = []
            seen = set()
            for item in merged_items:
                dedupe_value = self._resolve_dotted_path(item, custom_dedupe_key) if custom_dedupe_key else None
                key = str(dedupe_value) if dedupe_value is not None else self._default_dedupe_key(item)
                if key in seen:
                    continue
                seen.add(key)
                unique_items.append(item)
            merged_items = unique_items

        if limit is not None:
            merged_items = merged_items[: int(limit)]

        data[f"{self.id}.items"] = merged_items
        data[f"{self.id}.references"] = merged_items
        data[f"{self.id}.latency"] = total_latency
        data[f"{self.id}.total_input_items"] = total_input_items
        data[f"{self.id}.merged_count"] = len(merged_items)
        logger.info(
            "MergeComponent succeeded: component_id=%s input_items=%d merged_items=%d latency=%.2fs",
            self.id,
            total_input_items,
            len(merged_items),
            total_latency,
        )
        return data, self.next_component_id or ""
