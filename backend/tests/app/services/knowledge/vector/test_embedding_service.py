import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

from app.models.knowledge.vector import EmbeddingPurpose  # noqa: E402
from app.services.knowledge.vector import AbstractVectorizer, EmbeddingService  # noqa: E402


class FakeVectorizer(AbstractVectorizer):
    provider = "fake"
    display_name = "Fake"
    description = "Fake test vectorizer"

    def is_available(self, provider_settings=None):
        return True, None

    def _embed(self, texts, provider_settings=None):
        return [[3.0, 4.0] for _ in texts]


class EmbeddingServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = EmbeddingService()
        self.service._vectorizers = {"fake": FakeVectorizer()}

    def test_embeds_and_normalizes_vectors(self):
        embeddings = self.service.embed_texts(
            "fake",
            ["eins", "zwei"],
            purpose=EmbeddingPurpose.DOCUMENT,
            normalize=True,
        )

        self.assertEqual(len(embeddings), 2)
        self.assertAlmostEqual(embeddings[0][0], 0.6)
        self.assertAlmostEqual(embeddings[0][1], 0.8)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in embeddings[0])), 1.0)

    def test_lists_registered_vectorizers(self):
        descriptors = self.service.list_vectorizers()

        self.assertEqual(len(descriptors), 1)
        self.assertEqual(descriptors[0].provider, "fake")
        self.assertTrue(descriptors[0].is_available)


if __name__ == "__main__":
    unittest.main()
