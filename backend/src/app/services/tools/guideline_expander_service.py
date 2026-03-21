import time
from collections import defaultdict
from typing import Dict, List, Optional

from app.models.knowledge.guideline.guideline_reference import GuidelineReference
from app.models.tools.guideline_expander import (
    GuidelineExpanderKind,
    GuidelineExpanderRequest,
    GuidelineExpanderResponse,
    GuidelineExpanderSettings,
    NeighborhoodDirection,
)
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class GuidelineExpanderService:
    def __init__(self, reference_service, hierarchy_index_service):
        self.reference_service = reference_service
        self.hierarchy_index_service = hierarchy_index_service

    def expand_references(self, request: GuidelineExpanderRequest) -> GuidelineExpanderResponse:
        started = time.time()
        if request.settings.kind == GuidelineExpanderKind.NEIGHBORHOOD:
            references = self._expand_neighborhood(request.references, request.settings)
        elif request.settings.kind == GuidelineExpanderKind.HIERARCHY:
            references = self._expand_hierarchy(request.references, request.settings)
        else:
            raise ValueError(f"Unsupported expander kind: {request.settings.kind}")

        original_ids = {str(reference.id) for reference in request.references if getattr(reference, "id", None)}
        added = [reference for reference in references if str(reference.id) not in original_ids]
        latency = time.time() - started
        return GuidelineExpanderResponse(
            kind=request.settings.kind,
            references=references,
            added_references=added,
            latency=latency,
        )

    def _expand_neighborhood(
            self,
            references: List[GuidelineReference],
            settings: GuidelineExpanderSettings,
    ) -> List[GuidelineReference]:
        expanded: List[GuidelineReference] = list(references)
        grouped = self._group_by_reference_group(references, settings)

        for reference_group_id, group_references in grouped.items():
            all_group_references = self.reference_service.list_references(reference_group_id=reference_group_id)
            per_guideline: Dict[str, List[GuidelineReference]] = defaultdict(list)
            for reference in sorted(all_group_references, key=self._reference_sort_key):
                per_guideline[str(reference.guideline_id)].append(reference)

            index_lookup: Dict[str, int] = {}
            for guideline_references in per_guideline.values():
                for idx, reference in enumerate(guideline_references):
                    if getattr(reference, "id", None) is not None:
                        index_lookup[str(reference.id)] = idx

            for seed in group_references:
                seed_id = str(seed.id) if getattr(seed, "id", None) else None
                if seed_id is None:
                    continue
                guideline_references = per_guideline.get(str(seed.guideline_id), [])
                seed_index = index_lookup.get(seed_id)
                if seed_index is None:
                    continue

                for neighbor_index in self._neighbor_indices(seed_index, settings.context_window_size, settings.direction):
                    if 0 <= neighbor_index < len(guideline_references):
                        expanded.append(guideline_references[neighbor_index])

        return self._dedupe_references(expanded)

    def _expand_hierarchy(
            self,
            references: List[GuidelineReference],
            settings: GuidelineExpanderSettings,
    ) -> List[GuidelineReference]:
        expanded_ids: List[str] = []
        grouped = self._group_by_reference_group(references, settings)

        for reference_group_id, group_references in grouped.items():
            reference_ids = [str(reference.id) for reference in group_references if getattr(reference, "id", None)]
            expanded_ids.extend(
                self.hierarchy_index_service.expand(
                    reference_group_id,
                    reference_ids,
                    mode=settings.mode.value,
                    levels_up=settings.levels_up,
                    heading_level=settings.heading_level,
                    simple_ratio_threshold=settings.simple_ratio_threshold,
                ),
            )

        resolved = [self.reference_service.get_reference_by_id(reference_id) for reference_id in expanded_ids]
        return self._dedupe_references(resolved)

    @staticmethod
    def _group_by_reference_group(
            references: List[GuidelineReference],
            settings: GuidelineExpanderSettings,
    ) -> Dict[str, List[GuidelineReference]]:
        grouped: Dict[str, List[GuidelineReference]] = defaultdict(list)
        for reference in references:
            reference_group_id = getattr(reference, "reference_group_id", None)
            resolved_group_id = str(reference_group_id) if reference_group_id is not None else settings.reference_group_id
            if not resolved_group_id:
                raise ValueError("Each reference must carry reference_group_id or settings.reference_group_id must be set.")
            grouped[str(resolved_group_id)].append(reference)
        return grouped

    @staticmethod
    def _reference_sort_key(reference) -> tuple:
        hierarchy = reference.document_hierarchy or []
        hierarchy_key = tuple((entry.heading_level, entry.order, entry.heading_number or "", entry.title or "") for entry in hierarchy)
        return str(reference.guideline_id), hierarchy_key, str(reference.id)

    @staticmethod
    def _neighbor_indices(index: int, window_size: int, direction: NeighborhoodDirection) -> List[int]:
        indices: List[int] = []
        if direction in {NeighborhoodDirection.PRECEDING, NeighborhoodDirection.BOTH}:
            indices.extend(range(max(0, index - window_size), index))
        if direction in {NeighborhoodDirection.SUCCEEDING, NeighborhoodDirection.BOTH}:
            indices.extend(range(index + 1, index + window_size + 1))
        return indices

    @staticmethod
    def _dedupe_references(references: List[GuidelineReference]) -> List[GuidelineReference]:
        seen = set()
        deduped: List[GuidelineReference] = []
        for reference in references:
            key = str(reference.id) if getattr(reference, "id", None) else f"{reference.guideline_id}:{reference.type}:{reference.extract_content()}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(reference)
        return deduped
