import re
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Dict, Iterable, List, Sequence, Tuple

from app.exceptions.knowledge.guideline import (
    ChunkingUpdateSourceEmptyError,
    GuidelineReferenceGroupNotFoundError,
    InvalidChunkingConfigurationError,
    NarrativeReferenceNotFoundError, TextInGuidelineNotFoundError,
)
from app.models.knowledge.guideline import (
    BoundingBox,
    ChunkingStrategy,
    GuidelineEntry,
    GuidelineHierarchyEntry,
    GuidelineReference,
    GuidelineReferenceChunkingRequest,
    GuidelineReferenceChunkingResult,
    GuidelineReferenceChunkingUpdateRequest,
    GuidelineReferenceGroup,
    ReferenceType,
)
from app.services.knowledge.guideline.bounding_box_finder_service import BoundingBoxFinderService
from app.services.knowledge.guideline.guideline_reference_service import GuidelineReferenceService
from app.services.knowledge.guideline.guideline_service import GuidelineService


@dataclass
class GuidelineReferenceChunkingService:
    reference_service: GuidelineReferenceService
    guideline_service: GuidelineService
    bounding_box_finder_service: BoundingBoxFinderService
    
    def create_chunked_reference_group(
            self,
            request: GuidelineReferenceChunkingRequest,
    ) -> GuidelineReferenceChunkingResult:
        fixed_character_amount = self._validate_configuration(
            request.chunking_strategy,
            request.fixed_character_amount,
        )
        source_group = self.reference_service.get_reference_group_by_id(request.source_reference_group_id)
        source_references = self.reference_service.list_references(reference_group_id=request.source_reference_group_id)
        
        if not any(reference.type == ReferenceType.TEXT for reference in source_references):
            raise NarrativeReferenceNotFoundError(
                f"Reference group '{source_group.name}' does not contain any narrative text references.",
            )
        
        target_name = self._resolve_target_group_name(
            preferred_name=request.target_reference_group_name,
            source_group_name=source_group.name,
            strategy=request.chunking_strategy,
            fixed_character_amount=fixed_character_amount,
        )
        target_group = self.reference_service.create_reference_group(
            GuidelineReferenceGroup(name=target_name, is_chunking_result=True),
        )
        created_reference_ids, chunked_text_reference_count = self._copy_chunked_references(
            source_references=source_references,
            target_reference_group_id=str(target_group.id),
            strategy=request.chunking_strategy,
            fixed_character_amount=fixed_character_amount,
        )
        
        processed_guideline_ids = sorted(
            {reference.guideline_id for reference in source_references},
            key=str,
        )
        return GuidelineReferenceChunkingResult(
            target_reference_group_id=target_group.id,
            target_reference_group_name=target_group.name,
            source_reference_group_id=request.source_reference_group_id,
            processed_guideline_ids=processed_guideline_ids,
            created_reference_ids=created_reference_ids,
            chunking_strategy=request.chunking_strategy,
            fixed_character_amount=fixed_character_amount,
            source_reference_count=len(source_references),
            created_reference_count=len(created_reference_ids),
            chunked_text_reference_count=chunked_text_reference_count,
        )
    
    def update_chunked_guideline(
            self,
            request: GuidelineReferenceChunkingUpdateRequest,
    ) -> GuidelineReferenceChunkingResult:
        fixed_character_amount = self._validate_configuration(
            request.chunking_strategy,
            request.fixed_character_amount,
        )
        target_group = self.reference_service.get_reference_group_by_id(request.target_reference_group_id)
        source_references = self.reference_service.list_references(
            reference_group_id=request.source_reference_group_id,
            guideline_id=request.guideline_id,
        )
        if not source_references:
            raise ChunkingUpdateSourceEmptyError(
                "No source references found for the requested guideline in the selected source reference group.",
            )
        
        if not any(reference.type == ReferenceType.TEXT for reference in source_references):
            raise NarrativeReferenceNotFoundError(
                "The selected source references do not contain any narrative text references to chunk.",
            )
        
        _, deleted_reference_ids = self.reference_service.delete_references_by_group_and_guideline(
            reference_group_id=request.target_reference_group_id,
            guideline_id=request.guideline_id,
        )
        created_reference_ids, chunked_text_reference_count = self._copy_chunked_references(
            source_references=source_references,
            target_reference_group_id=str(target_group.id),
            strategy=request.chunking_strategy,
            fixed_character_amount=fixed_character_amount,
        )
        return GuidelineReferenceChunkingResult(
            target_reference_group_id=target_group.id,
            target_reference_group_name=target_group.name,
            source_reference_group_id=request.source_reference_group_id,
            processed_guideline_ids=[request.guideline_id],
            created_reference_ids=created_reference_ids,
            deleted_reference_ids=deleted_reference_ids,
            chunking_strategy=request.chunking_strategy,
            fixed_character_amount=fixed_character_amount,
            source_reference_count=len(source_references),
            created_reference_count=len(created_reference_ids),
            chunked_text_reference_count=chunked_text_reference_count,
        )
    
    def _copy_chunked_references(
            self,
            source_references: Sequence[GuidelineReference],
            target_reference_group_id: str,
            strategy: ChunkingStrategy,
            fixed_character_amount: int | None,
    ) -> Tuple[List, int]:
        references_by_guideline: DefaultDict[str, List[GuidelineReference]] = defaultdict(list)
        for reference in source_references:
            references_by_guideline[str(reference.guideline_id)].append(reference)
        
        created_reference_ids = []
        chunked_text_reference_count = 0
        
        for guideline_id, grouped_references in references_by_guideline.items():
            guideline = self.guideline_service.get_guideline_by_id(guideline_id)
            prepared_references, chunked_count = self._prepare_guideline_references(
                grouped_references,
                guideline=guideline,
                target_reference_group_id=target_reference_group_id,
                strategy=strategy,
                fixed_character_amount=fixed_character_amount,
            )
            chunked_text_reference_count += chunked_count
            for prepared_reference in prepared_references:
                prepared_reference.pop("__chunk_sequence", None)
                created_reference = self.reference_service.create_reference(prepared_reference)
                created_reference_ids.append(created_reference.id)
        
        return created_reference_ids, chunked_text_reference_count
    
    def _prepare_guideline_references(
            self,
            references: Sequence[GuidelineReference],
            guideline: GuidelineEntry,
            target_reference_group_id: str,
            strategy: ChunkingStrategy,
            fixed_character_amount: int | None,
    ) -> Tuple[List[Dict], int]:
        ordered_references = sorted(references, key=self._reference_sort_key)
        expanded_references: List[Dict] = []
        chunked_text_reference_count = 0
        sequence = 0
        
        for reference in ordered_references:
            if reference.type != ReferenceType.TEXT:
                payload = self._clone_reference_payload(reference, target_reference_group_id)
                payload["__chunk_sequence"] = sequence
                expanded_references.append(payload)
                sequence += 1
                continue
            
            chunks = self._split_text_reference(
                reference.contained_text,
                strategy=strategy,
                fixed_character_amount=fixed_character_amount,
            )
            if len(chunks) > 1:
                chunked_text_reference_count += 1
            for chunk in chunks:
                payload = self._clone_reference_payload(reference, target_reference_group_id, chunk)
                payload["bboxs"] = [
                    bbox.model_dump() if isinstance(bbox, BoundingBox) else bbox
                    for bbox in self._find_chunk_bounding_boxes(guideline, reference, chunk)
                ]
                payload["__chunk_sequence"] = sequence
                expanded_references.append(payload)
                sequence += 1
        
        self._reindex_document_hierarchy(expanded_references)
        return expanded_references, chunked_text_reference_count
    
    @staticmethod
    def _validate_configuration(
            strategy: ChunkingStrategy,
            fixed_character_amount: int | None,
    ) -> int | None:
        if strategy == ChunkingStrategy.FIXED_CHARACTERS:
            if fixed_character_amount is None:
                raise InvalidChunkingConfigurationError(
                    "fixed_character_amount is required when chunking_strategy is 'fixed_characters'.",
                )
            return fixed_character_amount
        return None
    
    def _resolve_target_group_name(
            self,
            preferred_name: str | None,
            source_group_name: str,
            strategy: ChunkingStrategy,
            fixed_character_amount: int | None,
    ) -> str:
        base_name = preferred_name or self._build_default_group_name(
            source_group_name=source_group_name,
            strategy=strategy,
            fixed_character_amount=fixed_character_amount,
        )
        if not self._reference_group_name_exists(base_name):
            return base_name
        
        suffix = 0
        while True:
            candidate = f"{base_name} {suffix}"
            if not self._reference_group_name_exists(candidate):
                return candidate
            suffix += 1
    
    @staticmethod
    def _build_default_group_name(
            source_group_name: str,
            strategy: ChunkingStrategy,
            fixed_character_amount: int | None,
    ) -> str:
        if strategy == ChunkingStrategy.FIXED_CHARACTERS:
            return f"{source_group_name}_{strategy.value}_{fixed_character_amount}"
        return f"{source_group_name}_{strategy.value}"
    
    def _reference_group_name_exists(self, name: str) -> bool:
        try:
            self.reference_service.get_reference_group_by_name(name)
            return True
        except GuidelineReferenceGroupNotFoundError:
            return False
    
    @staticmethod
    def _clone_reference_payload(
            reference: GuidelineReference,
            target_reference_group_id: str,
            content: str | None = None,
    ) -> Dict:
        payload = reference.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)
        payload["reference_group_id"] = target_reference_group_id
        if content is not None:
            payload["contained_text"] = content
        return payload
    
    def _find_chunk_bounding_boxes(
            self,
            guideline: GuidelineEntry,
            reference: GuidelineReference,
            chunk: str,
    ) -> List[BoundingBox]:
        if not reference.bboxs:
            return []
        
        start_page = min(bbox.page for bbox in reference.bboxs)
        end_page = max(bbox.page for bbox in reference.bboxs)
        try:
            return self.bounding_box_finder_service.text_to_bounding_boxes(
                guideline,
                chunk,
                start_page=start_page,
                end_page=end_page,
            )
        except TextInGuidelineNotFoundError as e:
            raise NarrativeReferenceNotFoundError(
                f"Could not find bounding boxes for reference '{reference.id}':" + e.args[0],
            ) from e
    
    @staticmethod
    def _reference_sort_key(reference: GuidelineReference) -> Tuple:
        hierarchy_orders = tuple(entry.order for entry in reference.document_hierarchy)
        bbox = reference.bboxs[0] if reference.bboxs else None
        bbox_key = (
            bbox.page,
            *bbox.positions,
        ) if bbox else (10 ** 9, 10 ** 9, 10 ** 9, 10 ** 9, 10 ** 9)
        return hierarchy_orders, len(reference.document_hierarchy), bbox_key, reference.extract_content()
    
    def _split_text_reference(
            self,
            text: str,
            strategy: ChunkingStrategy,
            fixed_character_amount: int | None,
    ) -> List[str]:
        if strategy == ChunkingStrategy.FIXED_CHARACTERS:
            assert fixed_character_amount is not None
            return self._split_fixed_characters_without_cutting_words(text, fixed_character_amount)
        
        if strategy == ChunkingStrategy.SENTENCE:
            return self._split_sentences(text)
        
        return self._split_paragraphs(text)
    
    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        matches = re.findall(r"[^.!?]+(?:[.!?]+(?=\s|$)|$)", text, flags=re.MULTILINE)
        return [match.strip() for match in matches if match.strip()] or [text]
    
    @staticmethod
    def _split_paragraphs(text: str) -> List[str]:
        return [
            paragraph.strip()
            for paragraph in re.split(r"(?:\r?\n){2,}", text)
            if paragraph.strip()
        ] or [text]
    
    @staticmethod
    def _split_fixed_characters_without_cutting_words(text: str, max_characters: int) -> List[str]:
        normalized_text = text.strip()
        if not normalized_text:
            return [text]
        
        chunks: List[str] = []
        remaining_text = normalized_text
        
        while len(remaining_text) > max_characters:
            candidate = remaining_text[:max_characters]
            if remaining_text[max_characters:max_characters + 1].isspace():
                split_index = max_characters
            else:
                split_index = candidate.rfind(" ")
            
            if split_index <= 0:
                # Fall back for single words longer than the limit.
                split_index = max_characters
            
            chunk = remaining_text[:split_index].strip()
            if not chunk:
                split_index = max_characters
                chunk = remaining_text[:split_index].strip()
            
            chunks.append(chunk)
            remaining_text = remaining_text[split_index:].strip()
        
        if remaining_text:
            chunks.append(remaining_text)
        
        return chunks or [text]
    
    def _reindex_document_hierarchy(self, references: Iterable[Dict]) -> None:
        grouped_references: DefaultDict[Tuple, List[Dict]] = defaultdict(list)
        for reference in references:
            hierarchy = reference.get("document_hierarchy", [])
            if not hierarchy:
                continue
            grouped_references[self._hierarchy_group_key(hierarchy)].append(reference)
        
        for group_references in grouped_references.values():
            ordered_references = sorted(group_references, key=self._payload_reference_sort_key)
            for order, reference in enumerate(ordered_references):
                hierarchy = list(reference["document_hierarchy"])
                last_entry = dict(hierarchy[-1])
                last_entry["order"] = order
                hierarchy[-1] = GuidelineHierarchyEntry.model_validate(last_entry).model_dump()
                reference["document_hierarchy"] = hierarchy
    
    @staticmethod
    def _hierarchy_group_key(hierarchy: Sequence[Dict | GuidelineHierarchyEntry]) -> Tuple:
        last_entry = hierarchy[-1]
        if isinstance(last_entry, GuidelineHierarchyEntry):
            last_level = last_entry.heading_level
        else:
            last_level = last_entry["heading_level"]
        
        parent_entries = []
        for entry in hierarchy[:-1]:
            if isinstance(entry, GuidelineHierarchyEntry):
                parent_entries.append((entry.title, entry.heading_level, entry.heading_number, entry.order))
            else:
                parent_entries.append((entry["title"], entry["heading_level"], entry["heading_number"], entry["order"]))
        return tuple(parent_entries), len(hierarchy), last_level
    
    @staticmethod
    def _payload_reference_sort_key(reference: Dict) -> Tuple:
        hierarchy = reference.get("document_hierarchy", [])
        orders = tuple(entry["order"] if isinstance(entry, dict) else entry.order for entry in hierarchy)
        bboxs = reference.get("bboxs", [])
        if bboxs:
            bbox = bboxs[0]
            bbox_key = (
                bbox["page"] if isinstance(bbox, dict) else bbox.page,
                *(bbox["positions"] if isinstance(bbox, dict) else bbox.positions),
            )
        else:
            bbox_key = (10 ** 9, 10 ** 9, 10 ** 9, 10 ** 9, 10 ** 9)
        return orders, len(hierarchy), bbox_key, reference.get("__chunk_sequence", 0)
