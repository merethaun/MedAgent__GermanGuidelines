import pytest

from app.models.evaluation.dataset import QuestionClassification


@pytest.mark.parametrize(
    ("super_class", "sub_class", "expected_super", "expected_sub"),
    [
        ("Simple", "Text", "simple", "text"),
        ("complex", "multiple guidelines", "complex", "multiple_guidelines"),
        ("negative", "mal-formed", "negative", "malformed"),
        ("complex", "muliiti/step resoning", "complex", "multi_step_reasoning"),
    ],
)
def test_question_classification_normalizes_expected_values(super_class, sub_class, expected_super, expected_sub):
    classification = QuestionClassification(super_class=super_class, sub_class=sub_class)

    assert classification.super_class.value == expected_super
    assert classification.sub_class == expected_sub


def test_question_classification_rejects_invalid_combination():
    with pytest.raises(ValueError, match="not valid for super_class"):
        QuestionClassification(super_class="simple", sub_class="multiple_guidelines")
