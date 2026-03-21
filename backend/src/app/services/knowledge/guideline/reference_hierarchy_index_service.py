import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.constants.mongodb_config import REFERENCE_GROUP_HIERARCHY_INDEX_FOLDER
from app.models.knowledge.guideline.reference_hierarchy_models import (
    ReferenceHierarchyIndexBuildResponse,
    ReferenceHierarchyIndexNode,
    ReferenceHierarchyIndexSnapshot,
)
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class ReferenceHierarchyIndexService:
    def __init__(self, guideline_reference_service):
        self.guideline_reference_service = guideline_reference_service
        self._cache: Dict[str, ReferenceHierarchyIndexSnapshot] = {}

    @staticmethod
    def _index_folder() -> Path:
        folder = Path(REFERENCE_GROUP_HIERARCHY_INDEX_FOLDER)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _index_path(self, reference_group_id: str) -> Path:
        return self._index_folder() / f"{reference_group_id}.json"

    def load(self, reference_group_id: str) -> Optional[ReferenceHierarchyIndexSnapshot]:
        cached = self._cache.get(reference_group_id)
        if cached is not None:
            return cached

        path = self._index_path(reference_group_id)
        if not path.exists():
            return None

        snapshot = ReferenceHierarchyIndexSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        self._cache[reference_group_id] = snapshot
        logger.info("Loaded reference hierarchy index for group %s from %s", reference_group_id, path)
        return snapshot

    def build(self, reference_group_id: str, *, force: bool = False) -> ReferenceHierarchyIndexSnapshot:
        if not force:
            existing = self.load(reference_group_id)
            if existing is not None:
                return existing

        references = self.guideline_reference_service.list_references(reference_group_id=reference_group_id)
        references = sorted(references, key=self._reference_sort_key)
        nodes: Dict[str, ReferenceHierarchyIndexNode] = {}
        reference_to_node: Dict[str, str] = {}

        for reference in references:
            reference_id = str(reference.id)
            guideline_id = str(reference.guideline_id)
            hierarchy = list(reference.document_hierarchy or [])

            if not hierarchy:
                node_id = self._node_id(reference_group_id, guideline_id, [])
                node = nodes.get(node_id)
                if node is None:
                    node = ReferenceHierarchyIndexNode(
                        id=node_id,
                        reference_group_id=reference_group_id,
                        guideline_id=guideline_id,
                        label=guideline_id,
                    )
                    nodes[node_id] = node
                node.descendant_reference_ids.append(reference_id)
                reference_to_node[reference_id] = node_id
                continue

            parent_id = None
            for depth, entry in enumerate(hierarchy):
                path_parts = [
                    f"{item.heading_level}|{item.heading_number or ''}|{item.title or ''}"
                    for item in hierarchy[: depth + 1]
                ]
                node_id = self._node_id(reference_group_id, guideline_id, path_parts)
                node = nodes.get(node_id)
                if node is None:
                    label = " ".join(part for part in [entry.heading_number or "", entry.title or ""] if part).strip()
                    node = ReferenceHierarchyIndexNode(
                        id=node_id,
                        reference_group_id=reference_group_id,
                        guideline_id=guideline_id,
                        heading_level=entry.heading_level,
                        heading_number=entry.heading_number or "",
                        title=entry.title or "",
                        label=label or guideline_id,
                        parent_id=parent_id,
                    )
                    nodes[node_id] = node
                node.descendant_reference_ids.append(reference_id)
                parent_id = node_id

            reference_to_node[reference_id] = parent_id

        snapshot = ReferenceHierarchyIndexSnapshot(
            reference_group_id=reference_group_id,
            nodes=nodes,
            reference_to_node=reference_to_node,
        )
        self._cache[reference_group_id] = snapshot
        self._persist(snapshot)
        return snapshot

    def build_response(self, reference_group_id: str, *, force: bool = False) -> ReferenceHierarchyIndexBuildResponse:
        snapshot = self.build(reference_group_id, force=force)
        return ReferenceHierarchyIndexBuildResponse(
            reference_group_id=reference_group_id,
            node_count=len(snapshot.nodes),
            mapped_reference_count=len(snapshot.reference_to_node),
            persisted_path=str(self._index_path(reference_group_id)),
        )

    def expand(
            self,
            reference_group_id: str,
            reference_ids: List[str],
            *,
            mode: str,
            levels_up: int = 1,
            heading_level: Optional[int] = None,
            simple_ratio_threshold: Optional[float] = None,
    ) -> List[str]:
        snapshot = self.build(reference_group_id)
        if simple_ratio_threshold is not None:
            return self._expand_with_section_promotion(
                snapshot=snapshot,
                reference_ids=reference_ids,
                mode=mode,
                levels_up=levels_up,
                heading_level=heading_level,
                simple_ratio_threshold=simple_ratio_threshold,
            )

        ordered_ids: List[str] = []
        seen = set()

        for reference_id in reference_ids:
            node_id = snapshot.reference_to_node.get(reference_id)
            if not node_id:
                if reference_id not in seen:
                    seen.add(reference_id)
                    ordered_ids.append(reference_id)
                continue

            target_node = self._resolve_target_node(
                snapshot=snapshot,
                node_id=node_id,
                mode=mode,
                levels_up=levels_up,
                heading_level=heading_level,
            )
            node = snapshot.nodes.get(target_node)
            for candidate_id in (node.descendant_reference_ids if node is not None else [reference_id]):
                if candidate_id not in seen:
                    seen.add(candidate_id)
                    ordered_ids.append(candidate_id)

        return ordered_ids

    def _expand_with_section_promotion(
            self,
            *,
            snapshot: ReferenceHierarchyIndexSnapshot,
            reference_ids: List[str],
            mode: str,
            levels_up: int,
            heading_level: Optional[int],
            simple_ratio_threshold: float,
    ) -> List[str]:
        ordered_ids: List[str] = []
        seen = set()
        promoted_reference_ids: Set[str] = set()
        coverage_by_node: Dict[str, Set[str]] = {}
        resolved_target_by_reference: Dict[str, str] = {}

        for reference_id in reference_ids:
            node_id = snapshot.reference_to_node.get(reference_id)
            if not node_id:
                continue

            target_node = self._resolve_target_node(
                snapshot=snapshot,
                node_id=node_id,
                mode=mode,
                levels_up=levels_up,
                heading_level=heading_level,
            )
            resolved_target_by_reference[reference_id] = target_node
            coverage_by_node.setdefault(target_node, set()).add(reference_id)

        candidate_nodes: Set[str] = set()
        for node_id, covered_reference_ids in coverage_by_node.items():
            node = snapshot.nodes.get(node_id)
            if node is None:
                continue

            descendant_count = max(1, len(node.descendant_reference_ids))
            coverage_ratio = len(covered_reference_ids) / float(descendant_count)
            if coverage_ratio >= simple_ratio_threshold:
                candidate_nodes.add(node_id)

        promoted_node_ids: List[str] = []
        seen_promoted_nodes: Set[str] = set()
        for reference_id in reference_ids:
            target_node = resolved_target_by_reference.get(reference_id)
            if target_node is None or target_node not in candidate_nodes or target_node in seen_promoted_nodes:
                continue
            if self._has_candidate_ancestor(snapshot, target_node, candidate_nodes):
                continue
            promoted_node_ids.append(target_node)
            seen_promoted_nodes.add(target_node)

        logger.debug(
            "ReferenceHierarchyIndexService.expand thresholded: mode=%s threshold=%.3f references=%d candidate_sections=%d promoted_sections=%d",
            mode,
            simple_ratio_threshold,
            len(reference_ids),
            len(candidate_nodes),
            len(promoted_node_ids),
        )

        for node_id in promoted_node_ids:
            node = snapshot.nodes.get(node_id)
            if node is None:
                continue
            for candidate_id in node.descendant_reference_ids:
                promoted_reference_ids.add(candidate_id)
                if candidate_id not in seen:
                    seen.add(candidate_id)
                    ordered_ids.append(candidate_id)

        for reference_id in reference_ids:
            if reference_id in promoted_reference_ids:
                continue
            if reference_id not in seen:
                seen.add(reference_id)
                ordered_ids.append(reference_id)

        return ordered_ids

    def _has_candidate_ancestor(
            self,
            snapshot: ReferenceHierarchyIndexSnapshot,
            node_id: str,
            candidate_nodes: Set[str],
    ) -> bool:
        current = snapshot.nodes.get(node_id)
        while current is not None and current.parent_id:
            if current.parent_id in candidate_nodes:
                return True
            current = snapshot.nodes.get(current.parent_id)
        return False

    def _resolve_target_node(
            self,
            *,
            snapshot: ReferenceHierarchyIndexSnapshot,
            node_id: str,
            mode: str,
            levels_up: int,
            heading_level: Optional[int],
    ) -> str:
        current = snapshot.nodes.get(node_id)
        if current is None:
            return node_id

        if mode == "direct_parent":
            return current.parent_id or current.id

        if mode == "levels_up":
            target = current
            remaining = levels_up
            while remaining > 0 and target.parent_id:
                parent = snapshot.nodes.get(target.parent_id)
                if parent is None:
                    break
                target = parent
                remaining -= 1
            return target.id

        if mode == "heading_level":
            target = current
            while target.parent_id:
                if target.heading_level <= int(heading_level):
                    break
                parent = snapshot.nodes.get(target.parent_id)
                if parent is None:
                    break
                target = parent
            return target.id

        return current.id

    def _persist(self, snapshot: ReferenceHierarchyIndexSnapshot) -> None:
        path = self._index_path(snapshot.reference_group_id)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _reference_sort_key(reference) -> tuple:
        hierarchy = reference.document_hierarchy or []
        hierarchy_key = tuple((entry.heading_level, entry.order, entry.heading_number or "", entry.title or "") for entry in hierarchy)
        return str(reference.guideline_id), hierarchy_key, str(reference.id)

    @staticmethod
    def _node_id(reference_group_id: str, guideline_id: str, path_parts: List[str]) -> str:
        raw = reference_group_id + "|" + guideline_id + "|" + "|".join(path_parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
