import importlib.util
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
sys.modules.setdefault("litellm", types.SimpleNamespace(completion=None))

from app.models.tools.llm_interaction import LLMSettings  # noqa: E402
from app.models.tools.snomed_interaction import SnomedSettings, SnomedSynonym  # noqa: E402

_SNOMED_SERVICE_PATH = Path(__file__).resolve().parents[4] / "src" / "app" / "services" / "tools" / "snomed_service.py"
_SPEC = importlib.util.spec_from_file_location("test_snomed_service_module", _SNOMED_SERVICE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC is not None and _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)

SnomedService = _MODULE.SnomedService
SnomedSynonymsCacheEntry = _MODULE.SnomedSynonymsCacheEntry


class SnomedServiceTest(unittest.TestCase):
    def test_snomed_settings_use_local_defaults(self):
        settings = SnomedSettings()
        
        self.assertEqual(settings.base_url, "http://snomed-lite:8080/fhir")
        self.assertEqual(settings.version, "http://snomed.info/sct/11000274103/version/20250515")
    
    def setUp(self):
        class FakeLLMInteractionService:
            def generate_text(self, **kwargs):
                return "translated"
        
        self.service = SnomedService(FakeLLMInteractionService())
        self.llm_settings = LLMSettings(model="fake-model")
        self.snomed_settings = SnomedSettings(base_url="http://localhost:8080/fhir")
    
    def test_extract_first_match_prefers_display_and_language_filtered_synonyms(self):
        expand_json = {
            "expansion": {
                "contains": [
                    {
                        "code": "123",
                        "display": "Appendizitis",
                        "designation": [
                            {"language": "de", "use": {"display": "Synonym"}, "value": "Blinddarmentzündung"},
                            {"language": "en", "use": {"display": "Synonym"}, "value": "Appendicitis"},
                            {"language": "de-DE", "use": {"display": "Synonym"}, "value": "Wurmfortsatzentzündung"},
                        ],
                    },
                ],
            },
        }
        
        concept_id, canonical, synonyms = self.service._extract_first_match(expand_json, target_language="de")
        
        self.assertEqual(concept_id, "123")
        self.assertEqual(canonical, "Appendizitis")
        self.assertEqual(
            [syn.synonym for syn in synonyms],
            ["Appendizitis", "Blinddarmentzündung", "Wurmfortsatzentzündung"],
        )
    
    def test_extract_versions_from_codesystem_bundle(self):
        bundle_json = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "CodeSystem",
                        "url": "http://snomed.info/sct",
                        "version": "http://snomed.info/sct/11000274103/version/20250515",
                        "title": "SNOMED CT Germany Edition",
                    },
                },
                {
                    "resource": {
                        "resourceType": "CodeSystem",
                        "url": "http://snomed.info/sct",
                        "version": "http://snomed.info/sct/900000000000207008/version/20250131",
                        "title": "SNOMED CT International",
                    },
                },
            ],
        }
        
        versions = self.service._extract_versions_from_codesystem(bundle_json)
        
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].version, "http://snomed.info/sct/11000274103/version/20250515")
        self.assertEqual(versions[0].title, "SNOMED CT Germany Edition")
    
    def test_extract_versions_from_metadata_fallback(self):
        metadata_json = {
            "software": {"version": "10.7.1"},
            "fhirVersion": "4.0.1",
        }
        
        versions = self.service._extract_versions_from_metadata(metadata_json)
        
        self.assertEqual([item.version for item in versions], ["10.7.1", "4.0.1"])
    
    def test_expand_keywords_deduplicates_original_canonical_and_synonyms(self):
        def fake_get_synonyms(*args, **kwargs):
            return SnomedSynonymsCacheEntry(
                queried_term="Appendizitis",
                matched_term="Appendizitis",
                canonical_form="Appendizitis",
                concept_id="123",
                translated_via_llm=False,
                synonyms=[
                    SnomedSynonym(synonym="Appendizitis", preference=1.0),
                    SnomedSynonym(synonym="Blinddarmentzündung", preference=1.0),
                ],
            )
        
        self.service.get_synonyms = fake_get_synonyms
        
        items = self.service.expand_keywords(
            ["Appendizitis"],
            llm_settings=self.llm_settings,
            snomed_settings=self.snomed_settings,
        )
        
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].expanded_terms, ["Appendizitis", "Blinddarmentzündung"])


if __name__ == "__main__":
    unittest.main()
