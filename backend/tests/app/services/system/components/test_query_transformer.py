from bson import ObjectId

import app.services.system.components.component_registry  # noqa: F401
from app.models.system.system_chat_interaction import Chat, ChatInteraction
from app.services.system.components.query_transformer.hyde_query_transformer import HyDEQueryTransformer
from app.services.system.components.query_transformer.keyword_transformer import KeywordQueryTransformer
from app.services.system.components.query_transformer.query_context_merger import QueryContextMergerTransformer
from app.services.system.components.query_transformer.query_rewriter import QueryRewriteTransformer
from app.services.system.components.structure.start_component import StartComponent
from app.services.system.prompt_store import get_prompt_definition, list_prompt_templates
from app.services.tools.query_transformation_service import HyDEQueryResult, QueryMergeResult, QueryRewriteResult
from app.utils.system.resolve_component_path import resolve_component_path


def test_resolve_component_path_for_query_transformers():
    assert resolve_component_path(["query_transformer", "rewrite"]) is QueryRewriteTransformer
    assert resolve_component_path(["query_transformer", "keyword_extractor"]) is KeywordQueryTransformer
    assert resolve_component_path(["query_transformer", "hyde"]) is HyDEQueryTransformer
    assert resolve_component_path(["query_transformer", "query_context_merger"]) is QueryContextMergerTransformer


def test_prompt_store_exposes_hyde_prompt():
    prompt = get_prompt_definition("hyde_awmf_query_transform_v1")
    assert "hyde_awmf_query_transform_v1" in list_prompt_templates()
    assert "retrieval augmentation" in prompt.system_prompt
    assert "QUESTION:" in prompt.prompt
    assert "{query}" in prompt.prompt


def test_query_rewriter_cleans_query(monkeypatch):
    class FakeQueryTransformationService:
        def rewrite_query(self, **kwargs):
            return QueryRewriteResult(
                query=kwargs["query"],
                system_prompt=kwargs["system_prompt"],
                prompt=kwargs["prompt"],
                full_response="Was sind Symptome einer Appendizitis?",
                rewritten_query="Was sind Symptome einer Appendizitis?",
                session_id=kwargs["session_id"],
            )
    
    monkeypatch.setattr(
        "app.services.system.components.query_transformer.query_rewriter.get_query_transformation_service",
        lambda: FakeQueryTransformationService(),
    )
    
    transformer = QueryRewriteTransformer(
        component_id="rewrite",
        name="Rewrite query",
        parameters={
            "rewrite_instructions": "Clean the query by fixing misspellings only.",
            "llm_settings": {"model": "gpt-test"},
        },
        variant="rewrite",
    )
    
    data, next_component_id = transformer.execute({"start.current_user_input": "Was sind Symtome einer Appendizitis ?"})
    
    assert next_component_id is None
    assert data["rewrite.query"] == "Was sind Symtome einer Appendizitis ?"
    assert data["rewrite.rewritten_query"] == "Was sind Symptome einer Appendizitis?"
    assert data["rewrite.primary_query"] == "Was sind Symptome einer Appendizitis?"
    assert "Clean the query by fixing misspellings only." in data["rewrite.system_prompt"]
    assert "<query>Was sind Symtome einer Appendizitis ?</query>" in data["rewrite.prompt"]


def test_keyword_transformer_without_synonyms(monkeypatch):
    class FakeKeywordService:
        def extract_yake(self, **kwargs):
            assert kwargs["text"] == "Appendizitis Symptome Diagnostik"
            return ["appendizitis", "symptome", "diagnostik"]
    
    monkeypatch.setattr(
        "app.services.system.components.query_transformer.keyword_transformer.get_keyword_service",
        lambda: FakeKeywordService(),
    )
    
    transformer = KeywordQueryTransformer(
        component_id="keywords",
        name="Keyword extraction",
        parameters={
            "query": "{rewrite.primary_query}",
            "extraction_method": "yake",
            "expand_with_synonyms": False,
        },
        variant="keyword_extractor",
    )
    
    data, next_component_id = transformer.execute({"rewrite.primary_query": "Appendizitis Symptome Diagnostik"})
    
    assert next_component_id is None
    assert data["keywords.keywords"] == ["appendizitis", "symptome", "diagnostik"]
    assert data["keywords.expanded_keywords"] == ["appendizitis", "symptome", "diagnostik"]
    assert data["keywords.queries"] == ["appendizitis", "symptome", "diagnostik"]
    assert data["keywords.joined_query"] == "appendizitis symptome diagnostik"


def test_keyword_transformer_with_synonyms(monkeypatch):
    class FakeKeywordService:
        def extract_yake(self, **kwargs):
            return ["appendizitis", "sonographie"]
    
    class FakeSnomedService:
        def expand_keywords(self, keywords, **kwargs):
            from app.models.tools.snomed_interaction import SnomedKeywordExpansionItem
            
            return [
                SnomedKeywordExpansionItem(
                    keyword="appendizitis",
                    canonical_form="Appendixentzuendung",
                    expanded_terms=["appendizitis", "Appendixentzuendung"],
                ),
                SnomedKeywordExpansionItem(
                    keyword="sonographie",
                    canonical_form="Ultraschall",
                    expanded_terms=["sonographie", "Ultraschall"],
                ),
            ]
    
    monkeypatch.setattr(
        "app.services.system.components.query_transformer.keyword_transformer.get_keyword_service",
        lambda: FakeKeywordService(),
    )
    monkeypatch.setattr(
        "app.services.system.components.query_transformer.keyword_transformer.get_snomed_service",
        lambda: FakeSnomedService(),
    )
    
    transformer = KeywordQueryTransformer(
        component_id="keywords",
        name="Keyword extraction",
        parameters={
            "extraction_method": "yake",
            "expand_with_synonyms": True,
            "llm_settings": {"model": "gpt-test"},
        },
        variant="keyword_extractor",
    )
    
    data, _ = transformer.execute({"start.current_user_input": "Appendizitis Sonographie"})
    
    assert data["keywords.expanded_keywords"] == [
        "appendizitis",
        "Appendixentzuendung",
        "sonographie",
        "Ultraschall",
    ]
    assert len(data["keywords.keyword_expansions"]) == 2


def test_hyde_transformer_uses_query_transformation_service(monkeypatch):
    class FakeQueryTransformationService:
        def generate_hyde_documents(self, **kwargs):
            return HyDEQueryResult(
                query=kwargs["query"],
                system_prompt=kwargs["system_prompt"],
                prompt=kwargs["prompt"],
                full_response="<document>Doc</document>",
                documents=["Doc"],
                session_id=kwargs["session_id"],
            )
    
    monkeypatch.setattr(
        "app.services.system.components.query_transformer.hyde_query_transformer.get_query_transformation_service",
        lambda: FakeQueryTransformationService(),
    )
    
    transformer = HyDEQueryTransformer(
        component_id="hyde",
        name="HyDE",
        parameters={
            "llm_settings": {"model": "gpt-test"},
        },
        variant="hyde",
    )
    
    data, next_component_id = transformer.execute({"start.current_user_input": "Wie wird Appendizitis diagnostiziert?"})
    
    assert next_component_id is None
    assert len(data["hyde.documents"]) == 1
    assert data["hyde.primary_query"] == "Doc"
    assert "retrieval augmentation" in data["hyde.system_prompt"]
    assert 'QUESTION:\n"""Wie wird Appendizitis diagnostiziert?"""' in data["hyde.prompt"]


def test_start_component_exposes_previous_interactions():
    start = StartComponent(component_id="start", name="Start", parameters={}, variant="start")
    chat = Chat(
        workflow_system_id=ObjectId(),
        interactions=[
            ChatInteraction(
                user_input="Wie wird Appendizitis diagnostiziert?",
                generator_output="Appendizitis wird klinisch und bildgebend diagnostiziert.",
            ),
            ChatInteraction(user_input="Und was gilt in der Schwangerschaft?"),
        ],
    )
    
    data, _ = start.execute({"chat": chat})
    
    assert data["start.current_user_input"] == "Und was gilt in der Schwangerschaft?"
    assert data["start.previous_interaction_count"] == 1
    assert data["start.previous_interactions"] == [
        {
            "turn": "1",
            "user_input": "Wie wird Appendizitis diagnostiziert?",
            "system_output": "Appendizitis wird klinisch und bildgebend diagnostiziert.",
        },
    ]


def test_query_context_merger_merges_current_query_with_recent_history(monkeypatch):
    class FakeQueryTransformationService:
        def merge_query_with_history(self, **kwargs):
            assert kwargs["query"] == "Und was gilt in der Schwangerschaft?"
            assert "<user_input>Wie wird Appendizitis diagnostiziert?</user_input>" in kwargs["prompt"]
            assert "<system_output>Appendizitis wird klinisch und bildgebend diagnostiziert.</system_output>" in kwargs["prompt"]
            assert "<user_input>Welche Symptome sind typisch?</user_input>" in kwargs["prompt"]
            assert "<user_input>Und was gilt in der Schwangerschaft?</user_input>" not in kwargs["prompt"]
            return QueryMergeResult(
                query=kwargs["query"],
                system_prompt=kwargs["system_prompt"],
                prompt=kwargs["prompt"],
                full_response="Appendizitis Diagnostik und Besonderheiten in der Schwangerschaft",
                merged_query="Appendizitis Diagnostik und Besonderheiten in der Schwangerschaft",
            )
    
    monkeypatch.setattr(
        "app.services.system.components.query_transformer.query_context_merger.get_query_transformation_service",
        lambda: FakeQueryTransformationService(),
    )
    
    transformer = QueryContextMergerTransformer(
        component_id="context",
        name="Query context merger",
        parameters={
            "llm_settings": {"model": "gpt-test"},
            "max_history_items": 2,
            "max_output_chars": 80,
        },
        variant="query_context_merger",
    )
    
    data, next_component_id = transformer.execute(
        {
            "start.current_user_input": "Und was gilt in der Schwangerschaft?",
            "start.previous_interactions": [
                {
                    "turn": "1",
                    "user_input": "Wie wird Appendizitis diagnostiziert?",
                    "system_output": "Appendizitis wird klinisch und bildgebend diagnostiziert.",
                },
                {
                    "turn": "2",
                    "user_input": "Welche Symptome sind typisch?",
                    "system_output": "Typisch sind rechtsseitige Unterbauchschmerzen, Uebelkeit und Fieber.",
                },
            ],
        },
    )
    
    assert next_component_id is None
    assert data["context.history_item_count"] == 2
    assert data["context.merged_query"] == "Appendizitis Diagnostik und Besonderheiten in der Schwangerschaft"
    assert data["context.primary_query"] == "Appendizitis Diagnostik und Besonderheiten in der Schwangerschaft"
    assert len(data["context.history_items"]) == 2


def test_query_context_merger_can_skip_history(monkeypatch):
    class FakeQueryTransformationService:
        def merge_query_with_history(self, **kwargs):
            assert "No previous interactions available." in kwargs["prompt"]
            return QueryMergeResult(
                query=kwargs["query"],
                system_prompt=kwargs["system_prompt"],
                prompt=kwargs["prompt"],
                full_response="Neue isolierte Frage",
                merged_query="Neue isolierte Frage",
            )
    
    monkeypatch.setattr(
        "app.services.system.components.query_transformer.query_context_merger.get_query_transformation_service",
        lambda: FakeQueryTransformationService(),
    )
    
    transformer = QueryContextMergerTransformer(
        component_id="context",
        name="Query context merger",
        parameters={
            "llm_settings": {"model": "gpt-test"},
            "max_history_items": 0,
        },
        variant="query_context_merger",
    )
    
    data, _ = transformer.execute({"start.current_user_input": "Neue isolierte Frage"})
    
    assert data["context.history_item_count"] == 0
    assert data["context.merged_query"] == "Neue isolierte Frage"
