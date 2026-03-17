from app.models.tools.llm_interaction import LLMSettings
from app.services.tools.query_transformation_service import QueryTransformationService


class _FakeLLMInteractionService:
    def __init__(self, response: str):
        self.response = response
        self.calls = []
    
    def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_query_transformation_service_rewrites_query():
    llm_service = _FakeLLMInteractionService("Korrigierte Frage")
    service = QueryTransformationService(llm_service)
    
    result = service.rewrite_query(
        query="Korigierte Frage",
        system_prompt="Rewrite instructions",
        prompt="<query>Korigierte Frage</query>",
        llm_settings=LLMSettings(model="gpt-test"),
        session_id="rewrite-session",
    )
    
    assert result.rewritten_query == "Korrigierte Frage"
    assert result.session_id == "rewrite-session"
    assert llm_service.calls[0]["system_prompt"] == "Rewrite instructions"


def test_query_transformation_service_extracts_and_filters_hyde_documents():
    llm_service = _FakeLLMInteractionService(
        "<document>Ausfuehrlicher HyDE Text zur Appendizitis mit klinischer Einordnung.</document>"
        "<document>Ausfuehrlicher HyDE Text zur Appendizitis mit klinischer Einordnung.</document>",
    )
    service = QueryTransformationService(llm_service)
    
    result = service.generate_hyde_documents(
        query="Appendizitis",
        system_prompt="HyDE instructions",
        prompt='QUESTION:\n"""Appendizitis"""',
        llm_settings=LLMSettings(model="gpt-test"),
        session_id="hyde-session",
        min_chars=20,
        max_similarity=0.9,
    )
    
    assert result.documents == ["Ausfuehrlicher HyDE Text zur Appendizitis mit klinischer Einordnung."]
    assert result.session_id == "hyde-session"


def test_query_transformation_service_merges_query_without_session_history():
    llm_service = _FakeLLMInteractionService("Appendizitis in der Schwangerschaft Diagnostik")
    service = QueryTransformationService(llm_service)
    
    result = service.merge_query_with_history(
        query="Und wie ist das in der Schwangerschaft?",
        system_prompt="Merge instructions",
        prompt="CURRENT QUERY ...",
        llm_settings=LLMSettings(model="gpt-test"),
    )
    
    assert result.merged_query == "Appendizitis in der Schwangerschaft Diagnostik"
    assert "session_id" not in llm_service.calls[0]
