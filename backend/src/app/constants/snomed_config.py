import os

SNOMED_BASE_URL = os.getenv("SNOMED_BASE_URL", "http://snomed-lite:8080/fhir")
SNOMED_VALUE_SET_URL = os.getenv("SNOMED_VALUE_SET_URL", "http://snomed.info/sct?fhir_vs=ecl/*")
SNOMED_VERSION = os.getenv("SNOMED_VERSION", "http://snomed.info/sct/11000274103/version/20250515")
SNOMED_DISPLAY_LANGUAGE_DE = os.getenv("SNOMED_DISPLAY_LANGUAGE_DE", "de")
SNOMED_DISPLAY_LANGUAGE_EN = os.getenv("SNOMED_DISPLAY_LANGUAGE_EN", "en")
SNOMED_MAX_RESULTS = int(os.getenv("SNOMED_MAX_RESULTS", "10"))
SNOMED_TIMEOUT_S = int(os.getenv("SNOMED_TIMEOUT_S", "20"))
