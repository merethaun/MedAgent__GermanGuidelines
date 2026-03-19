import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from app.constants.neo4j_constants import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from app.exceptions.knowledge.graph import GraphNotFoundError
from app.models.knowledge.graph import GraphSearchHit, GraphSearchReason, GraphSyncRequest, GraphSyncResponse
from app.models.knowledge.guideline import GuidelineHierarchyEntry, GuidelineReference
from app.models.knowledge.vector import EmbeddingPurpose
from app.services.knowledge.guideline import GuidelineReferenceService, GuidelineService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)
_MAX_NEIGHBOR_DEPTH = 10
_MIN_SHARED_KEYWORDS_FOR_RATIO_MATCH = 2


def _normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _normalized_keywords(values: Optional[List[str]]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for value in values or []:
        keyword = _normalize_keyword(value)
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized.append(keyword)
    return normalized


def _extract_query_keywords(value: str) -> List[str]:
    return _normalized_keywords([token for token in re.split(r"[^\w]+", value or "") if len(token) >= 3])


def _heading_path(entries: List[GuidelineHierarchyEntry]) -> str:
    return " > ".join(entry.title for entry in (entries or []) if entry.title)


def _section_key(guideline_id: str, entries: List[GuidelineHierarchyEntry]) -> str:
    numbered = []
    for index, entry in enumerate(entries or []):
        numbered.append(f"{entry.heading_number}|{entry.title or ''}|{index}")
    return f"{guideline_id}::" + " > ".join(numbered)


def _reference_sort_key(reference: Any) -> tuple:
    hierarchy = getattr(reference, "document_hierarchy", []) or []
    orders = [int(getattr(entry, "order", 0) or 0) for entry in hierarchy]
    bboxs = getattr(reference, "bboxs", []) or []
    first_bbox = bboxs[0] if bboxs else None
    page = int(getattr(first_bbox, "page", 0) or 0) if first_bbox else 0
    positions = getattr(first_bbox, "positions", ()) if first_bbox else ()
    y = float(positions[1]) if len(positions) > 1 else 0.0
    x = float(positions[0]) if len(positions) > 0 else 0.0
    return tuple(orders), page, y, x, str(getattr(reference, "id", ""))


def _similarity_text(reference: GuidelineReference, *, max_chars: int) -> str:
    heading_path = _heading_path(getattr(reference, "document_hierarchy", []) or [])
    content = (reference.extract_content() or "").strip()
    joined = f"{heading_path}\n\n{content}" if heading_path and content else (heading_path or content)
    return joined[:max_chars].strip()


@dataclass
class Neo4jGraphService:
    guideline_service: GuidelineService
    guideline_reference_service: GuidelineReferenceService
    embedding_service: Optional[Any] = None

    def __post_init__(self) -> None:
        self._driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self._ensure_schema()

    def close(self) -> None:
        self._driver.close()

    def ping(self) -> bool:
        with self._driver.session() as session:
            return bool(session.run("RETURN 1 AS ok").single()["ok"])

    def _run(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> list[Any]:
        with self._driver.session() as session:
            return list(session.run(cypher, params or {}))

    def _ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT graph_guideline_unique IF NOT EXISTS FOR (g:Guideline) REQUIRE (g.graph_name, g.id) IS UNIQUE",
            "CREATE CONSTRAINT graph_section_unique IF NOT EXISTS FOR (s:Section) REQUIRE (s.graph_name, s.id) IS UNIQUE",
            "CREATE CONSTRAINT graph_reference_unique IF NOT EXISTS FOR (r:Reference) REQUIRE (r.graph_name, r.id) IS UNIQUE",
            "CREATE CONSTRAINT graph_keyword_unique IF NOT EXISTS FOR (k:Keyword) REQUIRE (k.graph_name, k.value) IS UNIQUE",
            "CREATE FULLTEXT INDEX graph_reference_search IF NOT EXISTS FOR (r:Reference) ON EACH [r.text, r.heading_path]",
        ]
        for statement in statements:
            self._run(statement)

    def _ensure_graph_exists(self, graph_name: str) -> str:
        normalized_graph_name = (graph_name or "").strip()
        if not normalized_graph_name:
            raise ValueError("graph_name must not be empty.")

        records = self._run(
            """
            MATCH (r:Reference {graph_name: $graph_name})
            RETURN count(r) > 0 AS exists
            """,
            {"graph_name": normalized_graph_name},
        )
        graph_exists = bool(records[0]["exists"]) if records else False
        if not graph_exists:
            logger.warning("Graph lookup failed because the graph does not exist: graph=%s", normalized_graph_name)
            raise GraphNotFoundError(normalized_graph_name)
        return normalized_graph_name

    def delete_graph(self, graph_name: str) -> None:
        self._run("MATCH (n {graph_name: $graph_name}) DETACH DELETE n", {"graph_name": graph_name})

    def _materialize_hits(self, hits: List[GraphSearchHit]) -> tuple[List[GuidelineReference], List[GraphSearchHit]]:
        references: List[GuidelineReference] = []
        kept_hits: List[GraphSearchHit] = []
        for hit in hits:
            try:
                reference = self.guideline_reference_service.get_reference_by_id(hit.reference_id)
            except Exception:
                logger.warning("Skipping graph hit for missing reference_id=%s", hit.reference_id)
                continue
            references.append(reference)
            kept_hits.append(hit)
        return references, kept_hits

    @staticmethod
    def _select_similarity_edges(
            reference_ids: List[str],
            embeddings: List[List[float]],
            *,
            threshold: float,
            top_k: int,
    ) -> List[Tuple[str, str, float]]:
        if len(reference_ids) < 2:
            return []

        try:
            import torch

            matrix = torch.tensor(embeddings, dtype=torch.float32)
            scores = matrix @ matrix.T
            scores.fill_diagonal_(-1.0)

            edges: List[Tuple[str, str, float]] = []
            for source_index, source_id in enumerate(reference_ids):
                row = scores[source_index]
                added = 0
                for target_index in torch.argsort(row, descending=True).tolist():
                    score = float(row[target_index].item())
                    if score < threshold:
                        break
                    if source_index == int(target_index):
                        continue
                    edges.append((source_id, reference_ids[int(target_index)], score))
                    added += 1
                    if added >= top_k:
                        break
            return edges
        except Exception:
            edges: List[Tuple[str, str, float]] = []
            for source_index, source_id in enumerate(reference_ids):
                source_embedding = embeddings[source_index]
                scored_targets: List[Tuple[float, str]] = []
                for target_index, target_id in enumerate(reference_ids):
                    if source_index == target_index:
                        continue
                    score = float(sum(left * right for left, right in zip(source_embedding, embeddings[target_index])))
                    if score >= threshold:
                        scored_targets.append((score, target_id))
                scored_targets.sort(key=lambda item: item[0], reverse=True)
                edges.extend((source_id, target_id, score) for score, target_id in scored_targets[:top_k])
            return edges

    def _sync_similarity_edges(self, *, graph_name: str, references: List[GuidelineReference], request: GraphSyncRequest) -> int:
        if not request.include_similarity_edges:
            return 0

        embedding_service = getattr(self, "embedding_service", None)
        if embedding_service is None:
            logger.warning("Skipping similarity-edge sync for graph '%s' because no embedding service is configured.", graph_name)
            return 0

        reference_ids: List[str] = []
        texts: List[str] = []
        for reference in references:
            if getattr(reference, "id", None) is None:
                continue
            text = _similarity_text(reference, max_chars=request.similarity_text_max_chars)
            if not text:
                continue
            reference_ids.append(str(reference.id))
            texts.append(text)

        if len(texts) < 2:
            return 0

        embeddings = embedding_service.embed_texts(
            request.similarity_provider,
            texts,
            provider_settings=request.similarity_provider_settings,
            purpose=EmbeddingPurpose.DOCUMENT,
            normalize=True,
        )
        edges = self._select_similarity_edges(
            reference_ids,
            embeddings,
            threshold=request.similarity_threshold,
            top_k=request.similarity_top_k,
        )

        for source_id, target_id, score in edges:
            self._run(
                """
                MATCH (source:Reference {graph_name: $graph_name, id: $source_id})
                MATCH (target:Reference {graph_name: $graph_name, id: $target_id})
                MERGE (source)-[rel:SIMILAR]->(target)
                SET rel.score = $score
                """,
                {
                    "graph_name": graph_name,
                    "source_id": source_id,
                    "target_id": target_id,
                    "score": score,
                },
            )
        logger.info(
            "Graph similarity sync completed: graph=%s references=%d embedded=%d edges=%d provider=%s threshold=%.2f top_k=%d",
            graph_name,
            len(references),
            len(texts),
            len(edges),
            request.similarity_provider,
            request.similarity_threshold,
            request.similarity_top_k,
        )
        return len(edges)

    def retrieve_references(
            self,
            *,
            graph_name: str,
            query: str,
            seed_limit: int,
            result_limit: int,
            neighbor_depth: int,
            include_section_references: bool,
            section_max_children: int,
            include_keyword_matches: bool,
            keyword_overlap_min: int,
            keyword_overlap_ratio_min: float,
            include_similarity_matches: bool,
            similarity_threshold: float,
    ) -> tuple[List[Any], List[GraphSearchHit], float]:
        logger.info(
            "Graph retrieval started: graph=%s query_chars=%d seed_limit=%d result_limit=%d neighbor_depth=%d include_section=%s include_keywords=%s include_similarity=%s",
            graph_name,
            len((query or "").strip()),
            seed_limit,
            result_limit,
            neighbor_depth,
            include_section_references,
            include_keyword_matches,
            include_similarity_matches,
        )
        started = time.time()
        hits = self.search(
            graph_name=graph_name,
            query=query,
            seed_limit=seed_limit,
            result_limit=result_limit,
            neighbor_depth=neighbor_depth,
            include_section_references=include_section_references,
            section_max_children=section_max_children,
            include_keyword_matches=include_keyword_matches,
            keyword_overlap_min=keyword_overlap_min,
            keyword_overlap_ratio_min=keyword_overlap_ratio_min,
            include_similarity_matches=include_similarity_matches,
            similarity_threshold=similarity_threshold,
        )
        latency = time.time() - started
        references, kept_hits = self._materialize_hits(hits)
        logger.info(
            "Graph retrieval completed: graph=%s query_chars=%d references=%d hits=%d latency=%.2fs",
            graph_name,
            len((query or "").strip()),
            len(references),
            len(kept_hits),
            latency,
        )
        return references, kept_hits, latency

    def expand_from_references(
            self,
            *,
            graph_name: str,
            seed_references: List[GuidelineReference],
            result_limit: int,
            include_seed_references: bool,
            neighbor_depth: int,
            include_section_references: bool,
            section_max_children: int,
            include_keyword_matches: bool,
            keyword_overlap_min: int,
            keyword_overlap_ratio_min: float,
            include_similarity_matches: bool,
            similarity_threshold: float,
    ) -> tuple[List[GuidelineReference], List[GuidelineReference], List[GraphSearchHit], float]:
        graph_name = self._ensure_graph_exists(graph_name)
        logger.info(
            "Graph expansion started: graph=%s seeds=%d result_limit=%d include_seed=%s neighbor_depth=%d include_section=%s include_keywords=%s include_similarity=%s",
            graph_name,
            len(seed_references),
            result_limit,
            include_seed_references,
            neighbor_depth,
            include_section_references,
            include_keyword_matches,
            include_similarity_matches,
        )
        started = time.time()
        seed_ids = [str(reference.id) for reference in seed_references if getattr(reference, "id", None) is not None]
        if not seed_ids:
            logger.info("Graph expansion skipped: graph=%s reason=no_seed_references", graph_name)
            return [], [], [], 0.0

        aggregated: Dict[str, GraphSearchHit] = {}
        seed_id_set = set(seed_ids)
        seed_record_count = 0
        neighbor_record_count = 0
        section_record_count = 0
        keyword_record_count = 0
        similarity_record_count = 0

        def add_reason(reference_id: str, score: float, kind: str, detail: Optional[str], heading_path: Optional[str], guideline_id: Optional[str]) -> None:
            hit = aggregated.get(reference_id)
            if hit is None:
                hit = GraphSearchHit(
                    reference_id=reference_id,
                    score=0.0,
                    reasons=[],
                    heading_path=heading_path,
                    guideline_id=guideline_id,
                )
                aggregated[reference_id] = hit
            hit.score += float(score)
            hit.reasons.append(GraphSearchReason(kind=kind, score=float(score), detail=detail))

        if include_seed_references:
            seed_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                RETURN seed.id AS reference_id, seed.heading_path AS heading_path, seed.guideline_id AS guideline_id
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                },
            )
            seed_record_count = len(seed_records)
            for record in seed_records:
                add_reason(
                    reference_id=record["reference_id"],
                    score=1.0,
                    kind="seed",
                    detail="Provided as an input seed reference.",
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        if neighbor_depth > 0:
            neighbor_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                CALL (seed) {
                  MATCH path = (seed)-[:NEXT*1..10]->(neighbor:Reference {graph_name: $graph_name})
                  WHERE length(path) <= $neighbor_depth
                  RETURN neighbor, length(path) AS hops
                  UNION
                  MATCH path = (seed)-[:PREV*1..10]->(neighbor:Reference {graph_name: $graph_name})
                  WHERE length(path) <= $neighbor_depth
                  RETURN neighbor, length(path) AS hops
                }
                RETURN DISTINCT neighbor.id AS reference_id, neighbor.heading_path AS heading_path, neighbor.guideline_id AS guideline_id, hops
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                    "neighbor_depth": min(neighbor_depth, _MAX_NEIGHBOR_DEPTH),
                },
            )
            neighbor_record_count = len(neighbor_records)
            for record in neighbor_records:
                hops = int(record["hops"])
                add_reason(
                    reference_id=record["reference_id"],
                    score=max(0.1, 0.7 - (0.15 * hops)),
                    kind="neighbor",
                    detail=f"Adjacent to a seed reference within {hops} graph hop(s).",
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        if include_section_references:
            section_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})-[:PART_OF]->(section:Section {graph_name: $graph_name})<-[:PART_OF]-(candidate:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                RETURN DISTINCT candidate.id AS reference_id, candidate.heading_path AS heading_path, candidate.guideline_id AS guideline_id, section.heading_path AS section_path
                LIMIT $section_limit
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                    "section_limit": max(section_max_children, result_limit * 4),
                },
            )
            section_record_count = len(section_records)
            for record in section_records:
                add_reason(
                    reference_id=record["reference_id"],
                    score=0.45,
                    kind="section",
                    detail=f"Shares the section '{record['section_path'] or ''}' with a seed reference.",
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        if include_keyword_matches:
            keyword_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})-[:HAS_KEYWORD]->(k:Keyword {graph_name: $graph_name})<-[:HAS_KEYWORD]-(candidate:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                WITH seed, candidate, collect(DISTINCT k.value) AS shared_keywords
                WITH seed, candidate, shared_keywords,
                     size(shared_keywords) AS shared_count,
                     coalesce(seed.keyword_count, 0) AS seed_keyword_count,
                     coalesce(candidate.keyword_count, 0) AS candidate_keyword_count
                WITH candidate, shared_keywords, shared_count, seed_keyword_count, candidate_keyword_count,
                     CASE
                       WHEN seed_keyword_count = 0 OR candidate_keyword_count = 0 THEN 0.0
                       WHEN seed_keyword_count <= candidate_keyword_count THEN toFloat(shared_count) / toFloat(seed_keyword_count)
                       ELSE toFloat(shared_count) / toFloat(candidate_keyword_count)
                     END AS overlap_ratio
                WHERE shared_count >= $keyword_overlap_min
                   OR (
                     shared_count >= $keyword_overlap_ratio_floor
                     AND overlap_ratio >= $keyword_overlap_ratio_min
                   )
                RETURN candidate.id AS reference_id,
                       candidate.heading_path AS heading_path,
                       candidate.guideline_id AS guideline_id,
                       shared_keywords,
                       shared_count,
                       overlap_ratio
                LIMIT $keyword_limit
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                    "keyword_overlap_min": keyword_overlap_min,
                    "keyword_overlap_ratio_floor": _MIN_SHARED_KEYWORDS_FOR_RATIO_MATCH,
                    "keyword_overlap_ratio_min": keyword_overlap_ratio_min,
                    "keyword_limit": result_limit * 4,
                },
            )
            keyword_record_count = len(keyword_records)
            for record in keyword_records:
                shared_keywords = record["shared_keywords"] or []
                overlap_ratio = float(record["overlap_ratio"] or 0.0)
                add_reason(
                    reference_id=record["reference_id"],
                    score=max(min(1.0, 0.25 * len(shared_keywords)), overlap_ratio),
                    kind="keyword",
                    detail=(
                        f"Shares canonical keyword(s): {', '.join(shared_keywords[:5])} "
                        f"({int(record['shared_count'])} shared; normalized overlap {overlap_ratio:.2f})."
                    ),
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        if include_similarity_matches:
            similarity_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})-[rel:SIMILAR]->(candidate:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                  AND rel.score >= $similarity_threshold
                WITH candidate, max(rel.score) AS similarity_score
                RETURN candidate.id AS reference_id,
                       candidate.heading_path AS heading_path,
                       candidate.guideline_id AS guideline_id,
                       similarity_score
                ORDER BY similarity_score DESC
                LIMIT $similarity_limit
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                    "similarity_threshold": similarity_threshold,
                    "similarity_limit": max(result_limit * 4, 16),
                },
            )
            similarity_record_count = len(similarity_records)
            for record in similarity_records:
                similarity_score = float(record["similarity_score"] or 0.0)
                add_reason(
                    reference_id=record["reference_id"],
                    score=similarity_score,
                    kind="similarity",
                    detail=f"Semantically similar to a seed reference (cosine similarity {similarity_score:.2f}).",
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        ranked_hits = sorted(
            aggregated.values(),
            key=lambda hit: (hit.score, hit.reference_id in seed_id_set),
            reverse=True,
        )
        if not include_seed_references:
            ranked_hits = [hit for hit in ranked_hits if hit.reference_id not in seed_id_set]
        ranked_hits = ranked_hits[:result_limit]
        references, kept_hits = self._materialize_hits(ranked_hits)
        added_references = [reference for reference in references if str(reference.id) not in seed_id_set]
        latency = time.time() - started
        logger.info(
            "Graph expansion completed: graph=%s seeds=%d matched_seed_nodes=%d returned=%d added=%d hits=%d neighbors=%d sections=%d keywords=%d similarities=%d latency=%.2fs",
            graph_name,
            len(seed_ids),
            seed_record_count,
            len(references),
            len(added_references),
            len(kept_hits),
            neighbor_record_count,
            section_record_count,
            keyword_record_count,
            similarity_record_count,
            latency,
        )
        return references, added_references, kept_hits, latency

    def sync_reference_group(self, request: GraphSyncRequest) -> GraphSyncResponse:
        graph_name = request.graph_name.strip()
        if not graph_name:
            raise ValueError("graph_name must not be empty.")
        logger.info(
            "Graph sync started: graph=%s reference_group_id=%s guideline_id=%s include_keyword_edges=%s include_similarity_edges=%s",
            graph_name,
            request.reference_group_id,
            request.guideline_id,
            request.include_keyword_edges,
            request.include_similarity_edges,
        )

        references = self.guideline_reference_service.list_references(
            reference_group_id=request.reference_group_id,
            guideline_id=request.guideline_id,
        )
        if not references:
            raise ValueError("No references found for the requested reference group / guideline combination.")

        self.delete_graph(graph_name)

        guideline_cache: Dict[str, Any] = {}
        section_ids_seen: set[str] = set()
        keyword_ids_seen: set[str] = set()
        refs_by_guideline: Dict[str, List[Any]] = {}
        for reference in references:
            refs_by_guideline.setdefault(str(reference.guideline_id), []).append(reference)

        for guideline_oid, guideline_references in refs_by_guideline.items():
            guideline = guideline_cache.get(guideline_oid)
            if guideline is None:
                guideline = self.guideline_service.get_guideline_by_id(guideline_oid)
                guideline_cache[guideline_oid] = guideline

            self._run(
                """
                MERGE (g:Guideline {graph_name: $graph_name, id: $id})
                SET g.title = $title,
                    g.awmf_register_number = $awmf_register_number,
                    g.awmf_register_number_full = $awmf_register_number_full
                """,
                {
                    "graph_name": graph_name,
                    "id": guideline_oid,
                    "title": guideline.title,
                    "awmf_register_number": guideline.awmf_register_number,
                    "awmf_register_number_full": guideline.awmf_register_number_full,
                },
            )

            sorted_refs = sorted(guideline_references, key=_reference_sort_key)
            previous_reference_id: Optional[str] = None

            for reference in sorted_refs:
                reference_id = str(reference.id)
                heading_path = _heading_path(reference.document_hierarchy)
                section_id = _section_key(guideline_oid, reference.document_hierarchy) if reference.document_hierarchy else None
                normalized_keywords = _normalized_keywords(reference.associated_keywords)

                self._run(
                    """
                    MATCH (g:Guideline {graph_name: $graph_name, id: $guideline_id})
                    MERGE (r:Reference {graph_name: $graph_name, id: $id})
                    SET r.reference_group_id = $reference_group_id,
                        r.guideline_id = $guideline_id,
                        r.type = $type,
                        r.text = $text,
                        r.heading_path = $heading_path,
                        r.keyword_count = $keyword_count
                    MERGE (r)-[:IN_GUIDELINE]->(g)
                    """,
                    {
                        "graph_name": graph_name,
                        "id": reference_id,
                        "reference_group_id": str(reference.reference_group_id) if reference.reference_group_id else None,
                        "guideline_id": guideline_oid,
                        "type": reference.type.value,
                        "text": reference.extract_content(),
                        "heading_path": heading_path,
                        "keyword_count": len(normalized_keywords),
                    },
                )

                if previous_reference_id is not None:
                    self._run(
                        """
                        MATCH (prev:Reference {graph_name: $graph_name, id: $previous_id})
                        MATCH (curr:Reference {graph_name: $graph_name, id: $current_id})
                        MERGE (prev)-[:NEXT]->(curr)
                        MERGE (curr)-[:PREV]->(prev)
                        """,
                        {
                            "graph_name": graph_name,
                            "previous_id": previous_reference_id,
                            "current_id": reference_id,
                        },
                    )
                previous_reference_id = reference_id

                parent_section_id: Optional[str] = None
                for index in range(len(reference.document_hierarchy or [])):
                    section_entries = reference.document_hierarchy[: index + 1]
                    current_section_id = _section_key(guideline_oid, section_entries)
                    entry = section_entries[-1]
                    self._run(
                        """
                        MATCH (g:Guideline {graph_name: $graph_name, id: $guideline_id})
                        MERGE (s:Section {graph_name: $graph_name, id: $section_id})
                        SET s.guideline_id = $guideline_id,
                            s.title = $title,
                            s.heading_number = $heading_number,
                            s.heading_level = $heading_level,
                            s.heading_path = $heading_path,
                            s.section_order = $section_order
                        MERGE (s)-[:IN_GUIDELINE]->(g)
                        """,
                        {
                            "graph_name": graph_name,
                            "guideline_id": guideline_oid,
                            "section_id": current_section_id,
                            "title": entry.title,
                            "heading_number": entry.heading_number,
                            "heading_level": entry.heading_level,
                            "heading_path": _heading_path(section_entries),
                            "section_order": entry.order,
                        },
                    )
                    section_ids_seen.add(current_section_id)
                    if parent_section_id is not None:
                        self._run(
                            """
                            MATCH (child:Section {graph_name: $graph_name, id: $child_id})
                            MATCH (parent:Section {graph_name: $graph_name, id: $parent_id})
                            MERGE (child)-[:SUBSECTION_OF]->(parent)
                            """,
                            {
                                "graph_name": graph_name,
                                "child_id": current_section_id,
                                "parent_id": parent_section_id,
                            },
                        )
                    parent_section_id = current_section_id

                if section_id:
                    self._run(
                        """
                        MATCH (r:Reference {graph_name: $graph_name, id: $reference_id})
                        MATCH (s:Section {graph_name: $graph_name, id: $section_id})
                        MERGE (r)-[:PART_OF]->(s)
                        """,
                        {
                            "graph_name": graph_name,
                            "reference_id": reference_id,
                            "section_id": section_id,
                        },
                    )

                if request.include_keyword_edges:
                    for normalized in normalized_keywords:
                        self._run(
                            """
                            MATCH (r:Reference {graph_name: $graph_name, id: $reference_id})
                            MERGE (k:Keyword {graph_name: $graph_name, value: $value})
                            MERGE (r)-[:HAS_KEYWORD]->(k)
                            """,
                            {
                                "graph_name": graph_name,
                                "value": normalized,
                                "reference_id": reference_id,
                            },
                        )
                        keyword_ids_seen.add(normalized)

        similarity_edge_count = self._sync_similarity_edges(
            graph_name=graph_name,
            references=references,
            request=request,
        )

        response = GraphSyncResponse(
            graph_name=graph_name,
            reference_group_id=request.reference_group_id,
            guideline_id=request.guideline_id,
            guideline_count=len(refs_by_guideline),
            section_count=len(section_ids_seen),
            reference_count=len(references),
            keyword_count=len(keyword_ids_seen),
            similarity_edge_count=similarity_edge_count,
        )
        logger.info(
            "Graph sync completed: graph=%s guidelines=%d sections=%d references=%d keywords=%d similarity_edges=%d",
            graph_name,
            response.guideline_count,
            response.section_count,
            response.reference_count,
            response.keyword_count,
            response.similarity_edge_count,
        )
        return response

    def search(
            self,
            *,
            graph_name: str,
            query: str,
            seed_limit: int,
            result_limit: int,
            neighbor_depth: int,
            include_section_references: bool,
            section_max_children: int,
            include_keyword_matches: bool,
            keyword_overlap_min: int,
            keyword_overlap_ratio_min: float,
            include_similarity_matches: bool,
            similarity_threshold: float,
    ) -> List[GraphSearchHit]:
        graph_name = self._ensure_graph_exists(graph_name)
        normalized_query = (query or "").strip()
        if not normalized_query:
            logger.info("Graph search skipped: graph=%s reason=empty_query", graph_name)
            return []
        logger.info(
            "Graph search started: graph=%s query_chars=%d seed_limit=%d result_limit=%d neighbor_depth=%d include_section=%s include_keywords=%s include_similarity=%s",
            graph_name,
            len(normalized_query),
            seed_limit,
            result_limit,
            neighbor_depth,
            include_section_references,
            include_keyword_matches,
            include_similarity_matches,
        )

        seed_records = self._run(
            """
            CALL db.index.fulltext.queryNodes('graph_reference_search', $query) YIELD node, score
            WHERE node.graph_name = $graph_name
            RETURN node.id AS reference_id, node.heading_path AS heading_path, node.guideline_id AS guideline_id, score
            ORDER BY score DESC
            LIMIT $seed_limit
            """,
            {
                "graph_name": graph_name,
                "query": normalized_query,
                "seed_limit": seed_limit,
            },
        )
        if not seed_records:
            logger.info("Graph search returned no seed hits: graph=%s query_chars=%d", graph_name, len(normalized_query))
            return []

        aggregated: Dict[str, GraphSearchHit] = {}
        seed_ids = [record["reference_id"] for record in seed_records]
        keyword_tokens = _extract_query_keywords(normalized_query)
        neighbor_record_count = 0
        section_record_count = 0
        keyword_record_count = 0
        similarity_record_count = 0

        def add_reason(reference_id: str, score: float, kind: str, detail: Optional[str], heading_path: Optional[str], guideline_id: Optional[str]) -> None:
            hit = aggregated.get(reference_id)
            if hit is None:
                hit = GraphSearchHit(
                    reference_id=reference_id,
                    score=0.0,
                    reasons=[],
                    heading_path=heading_path,
                    guideline_id=guideline_id,
                )
                aggregated[reference_id] = hit
            hit.score += float(score)
            hit.reasons.append(GraphSearchReason(kind=kind, score=float(score), detail=detail))

        for rank, record in enumerate(seed_records):
            score = float(record["score"]) + max(0.0, (seed_limit - rank) * 0.05)
            add_reason(
                reference_id=record["reference_id"],
                score=score,
                kind="seed",
                detail="Matched the Neo4j fulltext reference index.",
                heading_path=record["heading_path"],
                guideline_id=record["guideline_id"],
            )

        if neighbor_depth > 0:
            neighbor_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                CALL (seed) {
                  MATCH path = (seed)-[:NEXT*1..10]->(neighbor:Reference {graph_name: $graph_name})
                  WHERE length(path) <= $neighbor_depth
                  RETURN neighbor, length(path) AS hops
                  UNION
                  MATCH path = (seed)-[:PREV*1..10]->(neighbor:Reference {graph_name: $graph_name})
                  WHERE length(path) <= $neighbor_depth
                  RETURN neighbor, length(path) AS hops
                }
                RETURN DISTINCT neighbor.id AS reference_id, neighbor.heading_path AS heading_path, neighbor.guideline_id AS guideline_id, hops
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                    "neighbor_depth": min(neighbor_depth, _MAX_NEIGHBOR_DEPTH),
                },
            )
            neighbor_record_count = len(neighbor_records)
            for record in neighbor_records:
                hops = int(record["hops"])
                add_reason(
                    reference_id=record["reference_id"],
                    score=max(0.1, 0.7 - (0.15 * hops)),
                    kind="neighbor",
                    detail=f"Adjacent to a seed reference within {hops} graph hop(s).",
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        if include_section_references:
            section_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})-[:PART_OF]->(section:Section {graph_name: $graph_name})<-[:PART_OF]-(candidate:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                RETURN DISTINCT candidate.id AS reference_id, candidate.heading_path AS heading_path, candidate.guideline_id AS guideline_id, section.heading_path AS section_path
                LIMIT $section_limit
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                    "section_limit": max(section_max_children, result_limit * 4),
                },
            )
            section_record_count = len(section_records)
            for record in section_records:
                add_reason(
                    reference_id=record["reference_id"],
                    score=0.45,
                    kind="section",
                    detail=f"Shares the section '{record['section_path'] or ''}' with a seed reference.",
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        if include_keyword_matches and keyword_tokens:
            keyword_records = self._run(
                """
                MATCH (candidate:Reference {graph_name: $graph_name})-[:HAS_KEYWORD]->(k:Keyword {graph_name: $graph_name})
                WHERE k.value IN $keywords
                WITH candidate, collect(DISTINCT k.value) AS shared_keywords
                WITH candidate, shared_keywords,
                     size(shared_keywords) AS shared_count,
                     coalesce(candidate.keyword_count, 0) AS candidate_keyword_count
                WITH candidate, shared_keywords, shared_count, candidate_keyword_count,
                     CASE
                       WHEN candidate_keyword_count = 0 OR $query_keyword_count = 0 THEN 0.0
                       WHEN $query_keyword_count <= candidate_keyword_count THEN toFloat(shared_count) / toFloat($query_keyword_count)
                       ELSE toFloat(shared_count) / toFloat(candidate_keyword_count)
                     END AS overlap_ratio
                WHERE shared_count >= $keyword_overlap_min
                   OR (
                     shared_count >= $keyword_overlap_ratio_floor
                     AND overlap_ratio >= $keyword_overlap_ratio_min
                   )
                RETURN candidate.id AS reference_id,
                       candidate.heading_path AS heading_path,
                       candidate.guideline_id AS guideline_id,
                       shared_keywords,
                       shared_count,
                       overlap_ratio
                LIMIT $keyword_limit
                """,
                {
                    "graph_name": graph_name,
                    "keywords": keyword_tokens,
                    "query_keyword_count": len(keyword_tokens),
                    "keyword_overlap_min": keyword_overlap_min,
                    "keyword_overlap_ratio_floor": _MIN_SHARED_KEYWORDS_FOR_RATIO_MATCH,
                    "keyword_overlap_ratio_min": keyword_overlap_ratio_min,
                    "keyword_limit": result_limit * 4,
                },
            )
            keyword_record_count = len(keyword_records)
            for record in keyword_records:
                shared_keywords = record["shared_keywords"] or []
                overlap_ratio = float(record["overlap_ratio"] or 0.0)
                add_reason(
                    reference_id=record["reference_id"],
                    score=max(min(1.0, 0.25 * len(shared_keywords)), overlap_ratio),
                    kind="keyword",
                    detail=(
                        f"Shares canonical keyword(s): {', '.join(shared_keywords[:5])} "
                        f"({int(record['shared_count'])} shared; normalized overlap {overlap_ratio:.2f})."
                    ),
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        if include_similarity_matches:
            similarity_records = self._run(
                """
                MATCH (seed:Reference {graph_name: $graph_name})-[rel:SIMILAR]->(candidate:Reference {graph_name: $graph_name})
                WHERE seed.id IN $seed_ids
                  AND rel.score >= $similarity_threshold
                WITH candidate, max(rel.score) AS similarity_score
                RETURN candidate.id AS reference_id,
                       candidate.heading_path AS heading_path,
                       candidate.guideline_id AS guideline_id,
                       similarity_score
                ORDER BY similarity_score DESC
                LIMIT $similarity_limit
                """,
                {
                    "graph_name": graph_name,
                    "seed_ids": seed_ids,
                    "similarity_threshold": similarity_threshold,
                    "similarity_limit": max(result_limit * 4, 16),
                },
            )
            similarity_record_count = len(similarity_records)
            for record in similarity_records:
                similarity_score = float(record["similarity_score"] or 0.0)
                add_reason(
                    reference_id=record["reference_id"],
                    score=similarity_score,
                    kind="similarity",
                    detail=f"Semantically similar to a seed reference (cosine similarity {similarity_score:.2f}).",
                    heading_path=record["heading_path"],
                    guideline_id=record["guideline_id"],
                )

        ranked_hits = sorted(
            aggregated.values(),
            key=lambda hit: (hit.score, sum(reason.kind == "seed" for reason in hit.reasons)),
            reverse=True,
        )
        limited_hits = ranked_hits[:result_limit]
        logger.info(
            "Graph search completed: graph=%s query_chars=%d seeds=%d returned=%d neighbors=%d sections=%d keywords=%d similarities=%d",
            graph_name,
            len(normalized_query),
            len(seed_records),
            len(limited_hits),
            neighbor_record_count,
            section_record_count,
            keyword_record_count,
            similarity_record_count,
        )
        return limited_hits
