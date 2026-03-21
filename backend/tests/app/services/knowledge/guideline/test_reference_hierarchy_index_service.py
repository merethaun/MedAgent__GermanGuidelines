from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineHierarchyEntry, GuidelineTextReference
from app.services.knowledge.guideline.reference_hierarchy_index_service import ReferenceHierarchyIndexService


def _make_reference(
        reference_id: str,
        text: str,
        order: int,
        *,
        section_title: str,
        section_number: str,
        group_id: str = "69b2b1ea9ced93a73a11bcee",
        guideline_id: str = "69b2b1ea9ced93a73a11bcdf",
):
    return GuidelineTextReference(
        _id=ObjectId(reference_id),
        reference_group_id=ObjectId(group_id),
        guideline_id=ObjectId(guideline_id),
        contained_text=text,
        document_hierarchy=[
            GuidelineHierarchyEntry(title="Diagnostik", heading_level=1, heading_number="2", order=10),
            GuidelineHierarchyEntry(title=section_title, heading_level=2, heading_number=section_number, order=order),
        ],
    )


def test_reference_hierarchy_index_service_promotes_section_when_threshold_met(monkeypatch, tmp_path):
    group_id = "69b2b1ea9ced93a73a11bcee"
    section_a_references = [
        _make_reference("69b2b1ea9ced93a73a11bcde", "Bildgebung A", 11, section_title="Bildgebung", section_number="2.1"),
        _make_reference("69b2b1ea9ced93a73a11bce0", "Bildgebung B", 12, section_title="Bildgebung", section_number="2.1"),
        _make_reference("69b2b1ea9ced93a73a11bce1", "Bildgebung C", 13, section_title="Bildgebung", section_number="2.1"),
        _make_reference("69b2b1ea9ced93a73a11bce2", "Bildgebung D", 14, section_title="Bildgebung", section_number="2.1"),
    ]
    other_section_reference = _make_reference(
        "69b2b1ea9ced93a73a11bce3",
        "Labor A",
        21,
        section_title="Labor",
        section_number="2.2",
    )

    class FakeReferenceService:
        def list_references(self, reference_group_id=None):
            assert str(reference_group_id) == group_id
            return [other_section_reference, section_a_references[2], section_a_references[0], section_a_references[3], section_a_references[1]]

    monkeypatch.setattr(ReferenceHierarchyIndexService, "_index_folder", staticmethod(lambda: tmp_path))
    service = ReferenceHierarchyIndexService(FakeReferenceService())

    expanded_ids = service.expand(
        group_id,
        [str(section_a_references[0].id), str(section_a_references[1].id)],
        mode="heading_level",
        heading_level=2,
        simple_ratio_threshold=0.5,
    )

    assert expanded_ids == [str(reference.id) for reference in section_a_references]


def test_reference_hierarchy_index_service_keeps_original_seeds_when_threshold_not_met(monkeypatch, tmp_path):
    group_id = "69b2b1ea9ced93a73a11bcee"
    references = [
        _make_reference("69b2b1ea9ced93a73a11bcde", "Bildgebung A", 11, section_title="Bildgebung", section_number="2.1"),
        _make_reference("69b2b1ea9ced93a73a11bce0", "Bildgebung B", 12, section_title="Bildgebung", section_number="2.1"),
        _make_reference("69b2b1ea9ced93a73a11bce1", "Bildgebung C", 13, section_title="Bildgebung", section_number="2.1"),
        _make_reference("69b2b1ea9ced93a73a11bce2", "Bildgebung D", 14, section_title="Bildgebung", section_number="2.1"),
    ]

    class FakeReferenceService:
        def list_references(self, reference_group_id=None):
            assert str(reference_group_id) == group_id
            return list(references)

    monkeypatch.setattr(ReferenceHierarchyIndexService, "_index_folder", staticmethod(lambda: tmp_path))
    service = ReferenceHierarchyIndexService(FakeReferenceService())

    expanded_ids = service.expand(
        group_id,
        [str(references[0].id), str(references[1].id)],
        mode="heading_level",
        heading_level=2,
        simple_ratio_threshold=0.75,
    )

    assert expanded_ids == [str(references[0].id), str(references[1].id)]
