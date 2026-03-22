import pytest

from app.models.evaluation.dataset import ExpectedRetrievalSnippet
from app.models.evaluation.run import EvaluationSample


TEXT_REFERENCE = "Es bleibt bei bis zu 80% junger Erwachsener mindestens ein Weisheitszahn im Kiefer retiniert"

BULLET_TEXT_REFERENCE = """• Perikoronare Infektion
• Erweiterung des radiologischen Perikoronarraumes
• Perikoronare Auftreibung (beispielsweise durch Zystenbildung)
• Schmerzen/Spannungsgefühl im Kiefer-Gesichtsbereich
• Parodontale Schäden, insbesondere distal an 12-Jahr Molaren
• Resorptionen an Nachbarzähnen (siehe Hintergrundtext unter 9.2)
• Elongation/Kippung
• kariöse Zerstörung/Pulpitis"""

BULLET_TEXT_REFERENCE_WITHOUT_GLYPHS = """Perikoronare Infektion
Erweiterung des radiologischen Perikoronarraumes
Perikoronare Auftreibung (beispielsweise durch Zystenbildung)
Schmerzen/Spannungsgefühl im Kiefer-Gesichtsbereich
Parodontale Schäden, insbesondere distal an 12-Jahr Molaren
Resorptionen an Nachbarzähnen (siehe Hintergrundtext unter 9.2)
Elongation/Kippung
kariöse Zerstörung/Pulpitis"""

RECOMMENDATION_REFERENCE = (
    "Eine dreidimensionale Bildgebung (beispielsweise DVT/CT) kann indiziert sein, wenn in der "
    "konventionellen zweidimensionalen Bildgebung Hinweise auf eine unmittelbare Lagebeziehung zu "
    "Risikostrukturen oder pathologischen Veränderungen vorhanden sind und gleichzeitig aus Sicht des "
    "Behandlers weitere räumliche Informationen entweder für die Risikoaufklärung des Patienten, "
    "Eingriffsplanung oder auch für die intraoperative Orientierung erforderlich sind."
)

TABLE_TITLE = "Tabelle 1: ICD-Codes der potenziellen Erkrankungsbilder (ICD-10-GM)"

TABLE_PLAIN_TEXT = """Leitlinie ICD
Weisheitszähne K00.2 Abnormitäten in Größe und Form der Zähne
K00.4 Störung der Zahnbildung
K00.6 Störungen des Zahndurchbruchs
K00.9 Störung der Zahnentwicklung, nicht näher bezeichnet
K01.0 Retinierte Zähne
K01.01 Impaktierte Zähne
K03.3 Pathologische Zahnresorption
K03.5 Ankylose der Zähne"""


def _build_sample(expected_retrieval, retrieval_output):
    return EvaluationSample(
        run_id="507f1f77bcf86cd799439011",
        source_type="question_group_batch",
        expected_retrieval=expected_retrieval,
        retrieval_output=retrieval_output,
        retrieval_latency=0.4,
    )


def test_compute_retrieval_metrics_matches_text_reference_content(metric_service):
    sample = _build_sample(
        expected_retrieval=[
            ExpectedRetrievalSnippet(
                reference_type="text",
                retrieval_text=TEXT_REFERENCE,
            ),
        ],
        retrieval_output=[
            {"weaviate_properties": {"contained_text": TEXT_REFERENCE}},
        ],
    )

    metrics = metric_service._compute_retrieval_metrics(sample)

    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(1.0)
    assert metrics.retrieval_latency == pytest.approx(0.4)


def test_compute_retrieval_metrics_ignores_bullet_glyphs_in_text_matching(metric_service):
    sample = _build_sample(
        expected_retrieval=[
            ExpectedRetrievalSnippet(
                reference_type="text",
                retrieval_text=BULLET_TEXT_REFERENCE,
            ),
        ],
        retrieval_output=[
            {
                "retrieval": BULLET_TEXT_REFERENCE_WITHOUT_GLYPHS,
            },
        ],
    )

    metrics = metric_service._compute_retrieval_metrics(sample)

    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(1.0)


def test_compute_retrieval_metrics_matches_recommendation_content(metric_service):
    sample = _build_sample(
        expected_retrieval=[
            ExpectedRetrievalSnippet(
                reference_type="recommendation",
                retrieval_text=RECOMMENDATION_REFERENCE,
            ),
        ],
        retrieval_output=[
            {
                "weaviate_properties": {
                    "recommendation_content": RECOMMENDATION_REFERENCE,
                },
            },
        ],
    )

    metrics = metric_service._compute_retrieval_metrics(sample)

    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(1.0)


def test_compute_retrieval_metrics_prefers_table_plain_text_over_title(metric_service):
    sample = _build_sample(
        expected_retrieval=[
            ExpectedRetrievalSnippet(
                reference_type="table",
                retrieval_text=TABLE_PLAIN_TEXT,
            ),
        ],
        retrieval_output=[
            {
                "weaviate_properties": {
                    "caption": TABLE_TITLE,
                    "plain_text": TABLE_PLAIN_TEXT,
                },
            },
        ],
    )

    metrics = metric_service._compute_retrieval_metrics(sample)

    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(1.0)
