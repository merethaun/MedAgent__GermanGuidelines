ACCESS_TOKEN = "user-access-token"


def test_dataset_import_and_export_round_trip_uses_guideline_source_and_bounding_boxes(dataset_service, seeded_question_group):
    csv_content = (
        "Question supercategory,Question subcategory,Question,Correct Answer,Answer Guideline Source,Answer Guideline Title,Answer Bounding Boxes,Answer Reference Type,Retrieval Text,Comment\n"
        "Simple,Text,What is the indication?,Expected answer,https://example.org/guidelines/007-001.pdf,Guideline A,\"[{\"\"page\"\": 12, \"\"positions\"\": [10, 20, 30, 40]}]\",text,Guideline snippet,Imported\n"
    ).encode("utf-8")

    inserted = dataset_service.import_questions_from_csv(str(seeded_question_group.id), csv_content, ACCESS_TOKEN)

    assert len(inserted) == 1
    assert inserted[0].expected_retrieval[0].guideline_title == "Guideline A"
    assert inserted[0].expected_retrieval[0].guideline_source == "https://example.org/guidelines/007-001.pdf"
    assert inserted[0].expected_retrieval[0].bounding_boxes[0].page == 12

    exported = dataset_service.export_questions_to_csv(question_group_id=str(seeded_question_group.id))

    inserted_id = str(inserted[0].id)

    assert "Question ID" in exported
    assert "Answer Guideline Source" in exported
    assert "Answer Bounding Boxes" in exported
    assert "Guideline A" in exported
    assert inserted_id in exported
    assert "question_group_id" not in exported
    assert "reference_id" not in exported


def test_dataset_import_with_modern_columns_does_not_require_backend_lookup(dataset_service, seeded_question_group):
    def fail_list_guidelines(access_token):
        raise AssertionError("list_guidelines should not be called for modern CSV imports")

    dataset_service.backend_client.list_guidelines = fail_list_guidelines

    csv_content = (
        "Question supercategory,Question subcategory,Question,Correct Answer,Answer Guideline Source,Answer Guideline Title,Answer Bounding Boxes,Answer Reference Type,Retrieval Text,Comment\n"
        "Simple,Text,What is the indication?,Expected answer,https://example.org/guidelines/007-001.pdf,Guideline A,\"[{\"\"page\"\": 12, \"\"positions\"\": [10, 20, 30, 40]}]\",text,Guideline snippet,Imported\n"
    ).encode("utf-8")

    inserted = dataset_service.import_questions_from_csv(str(seeded_question_group.id), csv_content, ACCESS_TOKEN)

    assert len(inserted) == 1
    assert inserted[0].expected_retrieval[0].guideline_source == "https://example.org/guidelines/007-001.pdf"


def test_dataset_import_legacy_guideline_and_page_resolves_source_and_bounding_boxes(dataset_service, seeded_question_group):
    csv_content = (
        "Question supercategory,Question subcategory,Question,Correct Answer,Answer Guideline,Answer Gpage,Answer Reference Type,Retrieval Text,Comment\n"
        "Simple,Text,What is the indication?,Expected answer,007-001,12,text,Guideline snippet,Imported\n"
    ).encode("utf-8")

    inserted = dataset_service.import_questions_from_csv(str(seeded_question_group.id), csv_content, ACCESS_TOKEN)
    snippet = inserted[0].expected_retrieval[0]

    assert snippet.guideline_source == "https://example.org/guidelines/007-001.pdf"
    assert snippet.guideline_title == "Guideline A"
    assert snippet.bounding_boxes[0].page == 12
    assert list(snippet.bounding_boxes[0].positions) == [10.0, 20.0, 30.0, 40.0]
