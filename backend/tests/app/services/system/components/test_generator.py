from app.exceptions.tools import LLMChatSessionNotFoundError
from app.models.system.system_chat_interaction import RetrievalResult
from app.services.system.components.abstract_component import ComponentContext
from app.services.system.components.generator.generator import LLMGenerator
from app.services.system.prompt_store import get_prompt_definition, list_prompt_templates


class _FakeLLMInteractionService:
    def __init__(self):
        self.created = []
        self.prompts = []
        self._history = {}

    def create_session(self, llm_settings, session_id=None, system_prompt=None, initial_history=None):
        self.created.append(
            {
                "llm_settings": llm_settings,
                "session_id": session_id,
                "system_prompt": system_prompt,
                "initial_history": initial_history,
            },
        )
        self._history[session_id] = []

    def update_session_settings(self, session_id, llm_settings):
        if session_id not in self._history:
            raise LLMChatSessionNotFoundError("missing session")

    def reset_history(self, session_id, keep_system_prompt=True):
        self._history[session_id] = []

    def chat_text(self, session_id, prompt):
        self.prompts.append(prompt)
        self._history.setdefault(session_id, []).append({"role": "user", "content": prompt})
        self._history[session_id].append({"role": "assistant", "content": "ok"})
        return "ok"

    def get_history(self, session_id):
        return list(self._history.get(session_id, []))


def test_prompt_store_exposes_awfm_prompt():
    assert "awmf_clinical_qa_html_v1" in list_prompt_templates()
    prompt = get_prompt_definition("awmf_clinical_qa_html_v1")
    assert "strictly based on official AWMF guidelines" in prompt.system_prompt
    assert "<question>Beispielfrage zur Leitlinie</question>" in prompt.prompt


def test_generator_resolves_stored_awfm_prompt():
    service = _FakeLLMInteractionService()
    generator = LLMGenerator(
        component_id="generator",
        name="Generator",
        parameters={
            "prompt_key": "awmf_clinical_qa_html_v1",
            "prompt": "{\ncontexts = []\nfor i, ref in enumerate(retrieved_references):\n    properties = ref.weaviate_properties or {}\n    section = properties.get('headers', '')\n    text = properties.get('text') or ref.retrieval or ''\n    contexts.append(f'''<context_item id=\"{i}\" section=\"{section}\">\\n{text}\\n</context_item>''')\nreturn f'''<context>{chr(10).join(contexts)}</context>\\n<question>{question_text}</question>'''\n}",
            "llm_settings": {"model": "gpt-test"},
            "session_id_key": "chat.session_id",
        },
        variant="generator",
    )
    generator.bind_context(ComponentContext(wf_id="wf-1", llm_interaction_service=service))

    references = [
        RetrievalResult(
            reference_id="69b2b1ea9ced93a73a11bcde",
            source_id="69b2b1ea9ced93a73a11bcdf",
            retrieval="Bei Verdacht sollte eine rasche Abklaerung erfolgen.",
            weaviate_properties={"headers": "1 Akutes Abdomen / 1.1 Appendizitis"},
        ),
        RetrievalResult(
            source_id="69b2b1ea9ced93a73a11bce0",
            retrieval="Die Sonographie ist initial zu bevorzugen.",
            weaviate_properties={"headers": "2 Diagnostik / 2.1 Bildgebung"},
        ),
    ]

    data, next_component_id = generator.execute(
        {
            "question_text": "Was empfiehlt die Leitlinie zur Bildgebung?",
            "chat.session_id": "session-1",
            "retrieved_references": references,
        },
    )

    assert next_component_id is None
    assert data["generator.response"] == "ok"
    assert data["generator.session_id"] == "session-1"
    assert service.created[0]["system_prompt"] is not None
    assert "strictly based on official AWMF guidelines" in service.created[0]["system_prompt"]

    prompt = data["generator.prompt"]
    assert prompt.startswith("<context>")
    assert "<context_item id=\"0\" section=\"1 Akutes Abdomen / 1.1 Appendizitis\">" in prompt
    assert "Bei Verdacht sollte eine rasche Abklaerung erfolgen." in prompt
    assert "<context_item id=\"1\" section=\"2 Diagnostik / 2.1 Bildgebung\">" in prompt
    assert "Die Sonographie ist initial zu bevorzugen." in prompt
    assert "<question>Was empfiehlt die Leitlinie zur Bildgebung?</question>" in prompt


def test_generator_rejects_unknown_prompt_key():
    generator = LLMGenerator(
        component_id="generator",
        name="Generator",
        parameters={
            "prompt_key": "missing_prompt",
            "llm_settings": {"model": "gpt-test"},
        },
        variant="generator",
    )
    generator.bind_context(ComponentContext(wf_id="wf-1", llm_interaction_service=_FakeLLMInteractionService()))

    try:
        generator.execute({"start.current_user_input": "Frage"})
    except ValueError as exc:
        assert "Unknown prompt_key 'missing_prompt'" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown prompt_key")
