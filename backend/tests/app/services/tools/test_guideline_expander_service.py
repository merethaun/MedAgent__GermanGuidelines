from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineHierarchyEntry, GuidelineTextReference
from app.models.tools.guideline_expander import GuidelineExpanderRequest, GuidelineExpanderSettings
from app.services.tools.guideline_expander_service import GuidelineExpanderService


def _make_reference(reference_id: str, text: str, order: int, *, group_id: str = "69b2b1ea9ced93a73a11bcee"):
    return GuidelineTextReference(
        _id=ObjectId(reference_id),
        reference_group_id=ObjectId(group_id),
        guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
        contained_text=text,
        document_hierarchy=[
            GuidelineHierarchyEntry(title="Acute abdomen", heading_level=1, heading_number="1", order=10),
            GuidelineHierarchyEntry(title="Appendicitis", heading_level=2, heading_number="1.1", order=order),
        ],
    )


def test_guideline_expander_service_expands_neighbors_from_reference_group():
    previous = _make_reference("69b2b1ea9ced93a73a11bce0", "Previous chunk", 10)
    seed = _make_reference("69b2b1ea9ced93a73a11bcde", "Seed chunk", 11)
    following = _make_reference("69b2b1ea9ced93a73a11bce1", "Following chunk", 12)

    class FakeReferenceService:
        def list_references(self, reference_group_id=None):
            assert str(reference_group_id) == "69b2b1ea9ced93a73a11bcee"
            return [following, seed, previous]

    service = GuidelineExpanderService(FakeReferenceService(), hierarchy_index_service=None)
    response = service.expand_references(
        GuidelineExpanderRequest(
            references=[seed],
            settings=GuidelineExpanderSettings(kind="neighborhood", context_window_size=1, direction="both"),
        ),
    )

    assert [reference.extract_content() for reference in response.references] == [
        "Seed chunk",
        "Previous chunk",
        "Following chunk",
    ]


def test_guideline_expander_service_expands_hierarchy_from_reference_group():
    seed = _make_reference("69b2b1ea9ced93a73a11bcde", "Seed chunk", 11)
    sibling = _make_reference("69b2b1ea9ced93a73a11bce0", "Sibling chunk", 12)

    class FakeReferenceService:
        def get_reference_by_id(self, reference_id):
            lookup = {
                str(seed.id): seed,
                str(sibling.id): sibling,
            }
            return lookup[str(reference_id)]

    class FakeHierarchyIndexService:
        def expand(self, reference_group_id, reference_ids, *, mode, levels_up, heading_level, simple_ratio_threshold):
            assert str(reference_group_id) == "69b2b1ea9ced93a73a11bcee"
            assert reference_ids == [str(seed.id)]
            assert simple_ratio_threshold == 0.5
            return [str(seed.id), str(sibling.id)]

    service = GuidelineExpanderService(FakeReferenceService(), FakeHierarchyIndexService())
    response = service.expand_references(
        GuidelineExpanderRequest(
            references=[seed],
            settings=GuidelineExpanderSettings(kind="hierarchy", mode="direct_parent", simple_ratio_threshold=0.5),
        ),
    )

    assert [reference.extract_content() for reference in response.references] == [
        "Seed chunk",
        "Sibling chunk",
    ]
