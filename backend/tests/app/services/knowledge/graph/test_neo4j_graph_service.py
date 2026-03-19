from datetime import date

from bson import ObjectId

from app.exceptions.knowledge.graph import GraphNotFoundError
from app.models.knowledge.graph import GraphSyncRequest
from app.models.knowledge.guideline import (
    GuidelineDownloadInformation,
    GuidelineEntry,
    GuidelineHierarchyEntry,
    GuidelineTextReference,
    GuidelineValidityInformation,
    OrganizationEntry,
)
from app.services.knowledge.graph.neo4j_graph_service import Neo4jGraphService


class _FakeGuidelineService:
    def get_guideline_by_id(self, guideline_id):
        assert guideline_id == "69b2b1ea9ced93a73a11bcdf"
        return GuidelineEntry(
            _id=ObjectId(guideline_id),
            awmf_register_number="001-001",
            awmf_register_number_full="001-001l",
            title="Appendicitis guideline",
            publishing_organizations=[OrganizationEntry(name="DGMKG", is_leading=True)],
            download_information=GuidelineDownloadInformation(url="https://example.org/guideline.pdf"),
            validity_information=GuidelineValidityInformation(
                version="1.0",
                guideline_creation_date=date(2025, 1, 1),
                valid=True,
                extended_validity=False,
            ),
        )


class _FakeGuidelineReferenceService:
    def list_references(self, reference_group_id, guideline_id=None):
        assert reference_group_id == "group-1"
        assert guideline_id is None
        return [
            GuidelineTextReference(
                _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
                reference_group_id=ObjectId(),
                guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                contained_text="Ultrasound is recommended.",
                associated_keywords=["Appendicitis", "Pregnancy"],
                document_hierarchy=[
                    GuidelineHierarchyEntry(
                        title="Diagnostics",
                        heading_level=1,
                        heading_number="2",
                        order=2,
                    ),
                ],
            ),
        ]

    def get_reference_by_id(self, reference_id):
        mapping = {
            "69b2b1ea9ced93a73a11bcde": "Ultrasound is recommended.",
            "69b2b1ea9ced93a73a11bce0": "MRI is an alternative in selected cases.",
            "69b2b1ea9ced93a73a11bce1": "CT should be avoided when ultrasound and MRI suffice.",
        }
        return GuidelineTextReference(
            _id=ObjectId(str(reference_id)),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text=mapping[str(reference_id)],
        )


class _FakeEmbeddingService:
    def __init__(self, embeddings):
        self.embeddings = embeddings
        self.calls = []

    def embed_texts(self, provider, texts, **kwargs):
        self.calls.append({"provider": provider, "texts": texts, **kwargs})
        return [list(vector) for vector in self.embeddings[:len(texts)]]


def test_sync_reference_group_uses_keyword_query_without_merge_match_violation():
    recorded_queries = []

    service = object.__new__(Neo4jGraphService)
    service.guideline_service = _FakeGuidelineService()
    service.guideline_reference_service = _FakeGuidelineReferenceService()
    service.embedding_service = None
    service._run = lambda cypher, params=None: recorded_queries.append(" ".join(cypher.split())) or []

    result = service.sync_reference_group(
        GraphSyncRequest(
            graph_name="guideline_graph_v1",
            reference_group_id="group-1",
            include_keyword_edges=True,
        ),
    )

    assert result.reference_count == 1
    assert result.keyword_count == 2
    assert result.similarity_edge_count == 0
    keyword_queries = [query for query in recorded_queries if "HAS_KEYWORD" in query]
    assert len(keyword_queries) == 2
    assert all("MATCH (r:Reference" in query and "MERGE (k:Keyword" in query for query in keyword_queries)
    assert all("MERGE (k:Keyword" not in query.split("MATCH (r:Reference")[0] for query in keyword_queries)


def test_sync_reference_group_creates_similarity_edges():
    recorded_queries = []

    class _MultiReferenceService(_FakeGuidelineReferenceService):
        def list_references(self, reference_group_id, guideline_id=None):
            assert reference_group_id == "group-1"
            assert guideline_id is None
            return [
                GuidelineTextReference(
                    _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
                    reference_group_id=ObjectId(),
                    guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                    contained_text="Ultrasound is recommended.",
                    associated_keywords=["Appendicitis", "Pregnancy"],
                    document_hierarchy=[
                        GuidelineHierarchyEntry(title="Diagnostics", heading_level=1, heading_number="2", order=2),
                    ],
                ),
                GuidelineTextReference(
                    _id=ObjectId("69b2b1ea9ced93a73a11bce0"),
                    reference_group_id=ObjectId(),
                    guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                    contained_text="MRI is an alternative in selected cases.",
                    associated_keywords=["Appendicitis", "MRI"],
                    document_hierarchy=[
                        GuidelineHierarchyEntry(title="Diagnostics", heading_level=1, heading_number="2", order=3),
                    ],
                ),
                GuidelineTextReference(
                    _id=ObjectId("69b2b1ea9ced93a73a11bce1"),
                    reference_group_id=ObjectId(),
                    guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                    contained_text="Antibiotics can be considered in uncomplicated cases.",
                    associated_keywords=["Appendicitis", "Antibiotics"],
                    document_hierarchy=[
                        GuidelineHierarchyEntry(title="Therapy", heading_level=1, heading_number="3", order=4),
                    ],
                ),
            ]

    service = object.__new__(Neo4jGraphService)
    service.guideline_service = _FakeGuidelineService()
    service.guideline_reference_service = _MultiReferenceService()
    service.embedding_service = _FakeEmbeddingService(
        embeddings=[
            [1.0, 0.0],
            [0.8, 0.6],
            [0.0, 1.0],
        ],
    )
    service._run = lambda cypher, params=None: recorded_queries.append((" ".join(cypher.split()), params or {})) or []

    result = service.sync_reference_group(
        GraphSyncRequest(
            graph_name="guideline_graph_v1",
            reference_group_id="group-1",
            include_keyword_edges=False,
            include_similarity_edges=True,
            similarity_threshold=0.7,
            similarity_top_k=1,
        ),
    )

    assert result.reference_count == 3
    assert result.similarity_edge_count == 2
    similarity_queries = [query for query, _ in recorded_queries if "MERGE (source)-[rel:SIMILAR]->(target)" in query]
    assert len(similarity_queries) == 2
    assert service.embedding_service.calls[0]["provider"] == "baai-bge-m3"
    assert len(service.embedding_service.calls[0]["texts"]) == 3


def test_expand_from_references_returns_added_references_and_graph_hits():
    service = object.__new__(Neo4jGraphService)
    service.guideline_service = _FakeGuidelineService()
    service.guideline_reference_service = _FakeGuidelineReferenceService()
    service.embedding_service = None
    recorded_queries = []

    def fake_run(cypher, params=None):
        compact = " ".join(cypher.split())
        recorded_queries.append(compact)
        if "RETURN count(r) > 0 AS exists" in compact:
            return [{"exists": True}]
        if "RETURN seed.id AS reference_id" in compact:
            return [
                {
                    "reference_id": "69b2b1ea9ced93a73a11bcde",
                    "heading_path": "Diagnostics",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                },
            ]
        if "RETURN DISTINCT neighbor.id AS reference_id" in compact:
            return [
                {
                    "reference_id": "69b2b1ea9ced93a73a11bce0",
                    "heading_path": "Diagnostics",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                    "hops": 1,
                },
            ]
        if "section.heading_path AS section_path" in compact:
            return []
        if "shared_keywords" in compact:
            return []
        return []

    service._run = fake_run

    seed = GuidelineTextReference(
        _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
        guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
        contained_text="Ultrasound is recommended.",
    )

    references, added_references, graph_hits, latency = service.expand_from_references(
        graph_name="guideline_graph_v1",
        seed_references=[seed],
        result_limit=5,
        include_seed_references=True,
        neighbor_depth=1,
        include_section_references=True,
        section_max_children=20,
        include_keyword_matches=True,
        keyword_overlap_min=1,
        keyword_overlap_ratio_min=0.8,
        include_similarity_matches=False,
        similarity_threshold=0.5,
    )

    assert latency >= 0.0
    assert [reference.extract_content() for reference in references] == [
        "Ultrasound is recommended.",
        "MRI is an alternative in selected cases.",
    ]
    assert [reference.extract_content() for reference in added_references] == [
        "MRI is an alternative in selected cases.",
    ]
    assert graph_hits[0].reference_id == "69b2b1ea9ced93a73a11bcde"
    assert graph_hits[1].reasons[0].kind == "neighbor"
    neighbor_queries = [query for query in recorded_queries if "RETURN DISTINCT neighbor.id AS reference_id" in query]
    assert len(neighbor_queries) == 1
    assert "CALL (seed) {" in neighbor_queries[0]
    assert "CALL {" not in neighbor_queries[0]
    assert "WITH seed" not in neighbor_queries[0]
    assert "[:NEXT*1..10]" in neighbor_queries[0]
    assert "[:PREV*1..10]" in neighbor_queries[0]
    assert "length(path) <= $neighbor_depth" in neighbor_queries[0]
    assert "[:NEXT*1..$neighbor_depth]" not in neighbor_queries[0]
    assert "[:PREV*1..$neighbor_depth]" not in neighbor_queries[0]


def test_expand_from_references_supports_normalized_keyword_overlap_and_similarity():
    service = object.__new__(Neo4jGraphService)
    service.guideline_service = _FakeGuidelineService()
    service.guideline_reference_service = _FakeGuidelineReferenceService()
    service.embedding_service = None
    recorded_queries = []

    def fake_run(cypher, params=None):
        compact = " ".join(cypher.split())
        recorded_queries.append(compact)
        if "RETURN count(r) > 0 AS exists" in compact:
            return [{"exists": True}]
        if "RETURN seed.id AS reference_id" in compact:
            return [
                {
                    "reference_id": "69b2b1ea9ced93a73a11bcde",
                    "heading_path": "Diagnostics",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                },
            ]
        if "RETURN DISTINCT neighbor.id AS reference_id" in compact:
            return []
        if "section.heading_path AS section_path" in compact:
            return []
        if "shared_keywords, shared_count, overlap_ratio" in compact:
            return [
                {
                    "reference_id": "69b2b1ea9ced93a73a11bce0",
                    "heading_path": "Diagnostics",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                    "shared_keywords": ["appendicitis", "pregnancy"],
                    "shared_count": 2,
                    "overlap_ratio": 1.0,
                },
            ]
        if "similarity_score" in compact:
            return [
                {
                    "reference_id": "69b2b1ea9ced93a73a11bce1",
                    "heading_path": "Diagnostics",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                    "similarity_score": 0.73,
                },
            ]
        return []

    service._run = fake_run

    seed = GuidelineTextReference(
        _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
        guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
        contained_text="Ultrasound is recommended.",
    )

    references, added_references, graph_hits, _ = service.expand_from_references(
        graph_name="guideline_graph_v1",
        seed_references=[seed],
        result_limit=5,
        include_seed_references=True,
        neighbor_depth=0,
        include_section_references=False,
        section_max_children=20,
        include_keyword_matches=True,
        keyword_overlap_min=4,
        keyword_overlap_ratio_min=0.8,
        include_similarity_matches=True,
        similarity_threshold=0.5,
    )

    assert [reference.extract_content() for reference in references] == [
        "Ultrasound is recommended.",
        "MRI is an alternative in selected cases.",
        "CT should be avoided when ultrasound and MRI suffice.",
    ]
    assert [reference.extract_content() for reference in added_references] == [
        "MRI is an alternative in selected cases.",
        "CT should be avoided when ultrasound and MRI suffice.",
    ]
    assert any(reason.kind == "keyword" and "normalized overlap 1.00" in (reason.detail or "") for reason in graph_hits[1].reasons)
    assert any(reason.kind == "similarity" for reason in graph_hits[2].reasons)
    keyword_queries = [query for query in recorded_queries if "shared_keywords, shared_count, overlap_ratio" in query]
    assert len(keyword_queries) == 1
    assert "overlap_ratio >= $keyword_overlap_ratio_min" in keyword_queries[0]
    assert "shared_count >= $keyword_overlap_ratio_floor" in keyword_queries[0]


def test_search_uses_literal_neighbor_range_and_parameter_filter():
    service = object.__new__(Neo4jGraphService)
    service.guideline_service = _FakeGuidelineService()
    service.guideline_reference_service = _FakeGuidelineReferenceService()
    service.embedding_service = None
    recorded_queries = []

    def fake_run(cypher, params=None):
        compact = " ".join(cypher.split())
        recorded_queries.append(compact)
        if "RETURN count(r) > 0 AS exists" in compact:
            return [{"exists": True}]
        if "CALL db.index.fulltext.queryNodes('graph_reference_search'" in compact:
            return [
                {
                    "reference_id": "69b2b1ea9ced93a73a11bcde",
                    "heading_path": "Diagnostics",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                    "score": 1.1,
                },
            ]
        return []

    service._run = fake_run

    hits = service.search(
        graph_name="guideline_graph_v1",
        query="appendicitis pregnancy",
        seed_limit=4,
        result_limit=5,
        neighbor_depth=1,
        include_section_references=False,
        section_max_children=10,
        include_keyword_matches=False,
        keyword_overlap_min=2,
        keyword_overlap_ratio_min=0.8,
        include_similarity_matches=False,
        similarity_threshold=0.5,
    )

    assert len(hits) == 1
    neighbor_queries = [query for query in recorded_queries if "RETURN DISTINCT neighbor.id AS reference_id" in query]
    assert len(neighbor_queries) == 1
    assert "CALL (seed) {" in neighbor_queries[0]
    assert "CALL {" not in neighbor_queries[0]
    assert "WITH seed" not in neighbor_queries[0]
    assert "[:NEXT*1..10]" in neighbor_queries[0]
    assert "[:PREV*1..10]" in neighbor_queries[0]
    assert "length(path) <= $neighbor_depth" in neighbor_queries[0]
    assert "[:NEXT*1..$neighbor_depth]" not in neighbor_queries[0]
    assert "[:PREV*1..$neighbor_depth]" not in neighbor_queries[0]


def test_expand_from_references_raises_graph_not_found_for_unknown_graph():
    service = object.__new__(Neo4jGraphService)
    service.guideline_service = _FakeGuidelineService()
    service.guideline_reference_service = _FakeGuidelineReferenceService()
    service.embedding_service = None
    service._run = lambda cypher, params=None: [{"exists": False}] if "RETURN count(r) > 0 AS exists" in " ".join(cypher.split()) else []

    seed = GuidelineTextReference(
        _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
        guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
        contained_text="Ultrasound is recommended.",
    )

    try:
        service.expand_from_references(
            graph_name="missing_graph",
            seed_references=[seed],
            result_limit=5,
            include_seed_references=True,
            neighbor_depth=1,
            include_section_references=False,
            section_max_children=20,
            include_keyword_matches=False,
            keyword_overlap_min=1,
            keyword_overlap_ratio_min=0.8,
            include_similarity_matches=False,
            similarity_threshold=0.5,
        )
        assert False, "Expected GraphNotFoundError"
    except GraphNotFoundError as exc:
        assert str(exc) == "Graph 'missing_graph' does not exist."
