from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineHierarchyEntry, GuidelineTextReference
from app.models.tools.guideline_context_filter import (
    GuidelineContextFilterKind,
    GuidelineContextFilterMethod,
    GuidelineContextFilterRequest,
    GuidelineContextFilterSettings,
)
from app.services.tools.guideline_context_filter_service import GuidelineContextFilterService


class _FakeLLMInteractionService:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _references():
    return [
        GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text="Appendicitis should be evaluated promptly.",
            document_hierarchy=[GuidelineHierarchyEntry(title="Appendicitis", heading_level=1, heading_number="1.1", order=91)],
        ),
        GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bce0"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text="Gallstones may present differently.",
            document_hierarchy=[GuidelineHierarchyEntry(title="Gallstones", heading_level=1, heading_number="4.2", order=42)],
        ),
    ]


def test_score_filter_can_rank_and_cut_top_k():
    service = GuidelineContextFilterService(llm_interaction_service=_FakeLLMInteractionService("[]"))
    response = service.filter_references(
        GuidelineContextFilterRequest(
            filter_input="appendicitis",
            references=_references(),
            settings=GuidelineContextFilterSettings(
                kind=GuidelineContextFilterKind.RELEVANCE,
                method=GuidelineContextFilterMethod.SCORE,
                score_field="document_hierarchy.0.order",
                keep_top_k=1,
            ),
        ),
    )

    assert len(response.kept_references) == 1
    assert str(response.kept_references[0].id) == "69b2b1ea9ced93a73a11bcde"
    assert len(response.dropped_references) == 1
    assert response.decisions[0].kept is True
    assert response.decisions[1].kept is False


def test_cross_encoder_filter_uses_multiple_properties(monkeypatch):
    service = GuidelineContextFilterService(llm_interaction_service=_FakeLLMInteractionService("[]"))

    class FakeTokenizer:
        def __call__(self, queries, documents, **kwargs):
            assert queries == ["appendicitis in pregnancy", "appendicitis in pregnancy"]
            assert "text: Appendicitis should be evaluated promptly." in documents[0]
            assert "section: Appendicitis" in documents[0]
            return {"input_ids": [[1, 2], [3, 4]]}

    class FakeModel:
        def __call__(self, **kwargs):
            return type("Output", (), {"logits": [[2.5], [-0.5]]})()

    monkeypatch.setattr(
        GuidelineContextFilterService,
        "_get_cross_encoder_bundle",
        classmethod(lambda cls, model_name: (FakeTokenizer(), FakeModel())),
    )
    monkeypatch.setattr(
        GuidelineContextFilterService,
        "_normalize_cross_encoder_logits",
        staticmethod(lambda logits: [0.92, 0.38]),
    )

    response = service.filter_references(
        GuidelineContextFilterRequest(
            filter_input="appendicitis in pregnancy",
            references=_references(),
            settings=GuidelineContextFilterSettings(
                kind=GuidelineContextFilterKind.RELEVANCE,
                method=GuidelineContextFilterMethod.CROSS_ENCODER,
                minimum_score=0.5,
                properties=[
                    {"path": "content", "label": "text"},
                    {"path": "heading_path", "label": "section"},
                ],
            ),
        ),
    )

    assert len(response.kept_references) == 1
    assert str(response.kept_references[0].id) == "69b2b1ea9ced93a73a11bcde"
    assert response.decisions[0].score > response.decisions[1].score


def test_llm_filter_parses_json_and_keeps_selected_items():
    llm = _FakeLLMInteractionService(
        """
        [
          {"index": 0, "keep": true, "score": 0.93, "reason": "Directly discusses appendicitis."},
          {"index": 1, "keep": false, "score": 0.12, "reason": "Off-topic biliary result."}
        ]
        """.strip(),
    )
    service = GuidelineContextFilterService(llm_interaction_service=llm)

    response = service.filter_references(
        GuidelineContextFilterRequest(
            filter_input="appendicitis diagnostics",
            references=_references(),
            settings=GuidelineContextFilterSettings(
                kind=GuidelineContextFilterKind.RELEVANCE,
                method=GuidelineContextFilterMethod.LLM,
                llm_settings={"model": "gpt-test"},
                properties=[
                    {"path": "content", "label": "text"},
                    {"path": "heading_path", "label": "section"},
                ],
            ),
        ),
    )

    assert len(response.kept_references) == 1
    assert response.decisions[0].kept is True
    assert response.decisions[1].kept is False
    assert len(llm.calls) == 1
    assert "References" in llm.calls[0]["prompt"]


def test_deduplicate_filter_keeps_highest_scoring_duplicate():
    references = [
        GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text="Appendicitis should be evaluated promptly.",
            document_hierarchy=[GuidelineHierarchyEntry(title="Appendicitis", heading_level=1, heading_number="1.1", order=55)],
        ),
        GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bce1"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text=" appendicitis should be evaluated promptly. ",
            document_hierarchy=[GuidelineHierarchyEntry(title="Appendicitis", heading_level=1, heading_number="1.1", order=91)],
        ),
        GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bce2"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text="Ultrasound is preferred as initial imaging.",
            document_hierarchy=[GuidelineHierarchyEntry(title="Imaging", heading_level=1, heading_number="2.1", order=72)],
        ),
    ]
    service = GuidelineContextFilterService(llm_interaction_service=_FakeLLMInteractionService("[]"))

    response = service.filter_references(
        GuidelineContextFilterRequest(
            filter_input="appendicitis diagnostics",
            references=references,
            settings=GuidelineContextFilterSettings(
                kind=GuidelineContextFilterKind.DEDUPLICATE,
                properties=[{"path": "content", "label": "text", "include_label": False}],
                score_field="document_hierarchy.0.order",
                sort_by_score=True,
            ),
        ),
    )

    assert len(response.kept_references) == 2
    assert [str(item.id) for item in response.kept_references] == [
        "69b2b1ea9ced93a73a11bce1",
        "69b2b1ea9ced93a73a11bce2",
    ]
    assert response.decisions[0].kept is False
    assert response.decisions[1].kept is True
    assert response.decisions[2].kept is True
