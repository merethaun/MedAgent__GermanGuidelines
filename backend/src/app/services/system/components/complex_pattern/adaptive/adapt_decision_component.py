import json
import os
import re
import textwrap
from dataclasses import is_dataclass, asdict
from typing import Dict, Any, Tuple, Optional, List

import requests
from openai import AzureOpenAI, OpenAI

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.models.system.complex_pattern.adapt_models import Action, RetrieveSettings, FilterSettings, GenerateSettings
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

DECIDER_PROMPT = r"""
You are the DECIDER in a RAG pipeline controller.
Your job: choose exactly ONE next action out of ["retrieve", "filter", "generate", or "end"] given the current state.
The current state is given by user input, previous actions, current retrieval, and current generation.

## Inputs
- User input (original question):
{user_input_block}

- Previous actions (most recent last; may be empty).
Each is an object matching: Action(action_type, settings, ragas_score) with the ragas_score being optional. They are provided as JSON list:
{actions_block}

- Current retrieval (may be empty).
A list of items with at least: text, headers, reference_id, chunk_index, scores (score, rerank_score):
{retrieval_block}

- Current generation result (may be empty).
The actual final answer is only the section contained in the `<action>` block, but the entire reasoning path is provided here anyways:
{generation_block}

- Optional: current evaluation metrics (ragas_score).
If provided, question_answered, relevance and faithfulness are floats between [0, 1]; response_groundedness and context relevance are either {{0, 0.5, 1}};
{metrics_block}

## What the actions do (MANDATORY behavior)
1. retrieve:
   * Provide a list of search queries that will be executed now.
   * You MAY include different query styles: cleaned question, sub-queries, HyDE-style hypotheses, etc.
   * You MUST set `top_k` (default {default_top_k_start}) and `context_size_c` (default {default_context_c_start}).
   * This action RESETS the generation (downstream system will discard prior generation).
   * Budget guardrails: do not exceed top_k > {max_top_k} or context_size_c > {max_context_c}.

2. filter:
   * Narrows the **existing** retrieval only (does NOT add new items).
   * Use **only if truly necessary** to trim a clearly mixed or overly large retrieval.
   * Two modes:
     a) option="query":
       Provide `query` and `threshold_query_relevance` in [0,1] (keep items with relevance >= threshold). Prefer this cheap mode when filtering is needed.
     b) option="generation_based":
       Provide `gen_result` (the current generation text).
       Use this **rarely**, when user-facing transparency or precise pruning is explicitly needed.

3. generate:
   * Produce a new answer strictly from the **current retrieval** (no hidden memory).
   * You may add `additional_comment` to guide faithfulness/focus, e.g., "Be strictly grounded in context", "During generation, focus on these subqueries: ...".
   * Always uses EXACTLY the current retrieval.
   * **If the question does not seem answerable with the available context or is outside scope, produce a clear, user-facing output explaining the limitation and, if helpful, suggest next steps or clarifications.**

4. end:
   * Use when the current answer is good enough or further steps are unlikely to improve it, or the question cannot be fully addressed with available context.
   * Prefer ending rather than looping if improvements are negligible.

## Cost-aware policy (follow strictly)
* Retrieval cost grows with larger `top_k` and `context_size_c`.
  * Start with `top_k≈{default_top_k_start}` and `context_size_c≈{default_context_c_start}`.
  * Escalate gradually only if metrics indicate missing or weak context (e.g., low context_relevance).
  * Do not exceed `top_k>{max_top_k}` or `context_size_c>{max_context_c}`.
* It is usually more important to get a **sufficient** set of relevant items than to make every item perfect.
* **Default to not filtering.** Use `filter` only when the retrieval set is clearly mixed or too large to safely generate from.
* Prefer efficiency: avoid repeated large retrieves/filters that don’t move metrics meaningfully.

## Decision policy (follow strictly; rely on metrics if available)
* **Out-of-scope shortcut:** If the question appears out-of-scope of {scope}, choose **"generate"** immediately (with a cautionary `additional_comment`). **Do not retrieve.**
* **Empty/useless retrieval shortcut:** If a retrieval step yields **no useful results** (e.g., retrieval is empty or obviously off-topic overall; or metrics show very low context_relevance):
  * **Immediately choose "generate"** and clearly state that relevant information could not be found in the available sources. Do **not** attempt further retrieval.
* If retrieval is empty but there is a strong indication that useful information **should** exist in the given AWMF guideline, weigh cost vs. benefit carefully. However, **avoid reiterations**: at most one retrieval attempt before deciding to generate.
* For low faithfulness (faithfulness < {min_faithfulness}) OR low response_groundedness (response_groundedness < {min_groundedness}) (suffices if one shows low value):
  * If many off-topic items are present **and** filtering is truly necessary, apply **"filter"** (prefer `option="query"`). Otherwise, apply **"retrieve"** once with targeted sub-queries to find missing evidence (respect cost guardrails).
* For low context_relevance (context_relevance < {min_context_relevance}):
  * Apply **one** improved **"retrieve"** pass with cleaned queries/sub-queries/HyDE; escalate K or C moderately within guardrails.
* For low response relevance but high context relevance (response_relevance < {min_response_relevance}, context_relevance >= {min_context_relevance}):
  * **"generate"** with `additional_comment` to be concise and focused on the user question.
* When the question seems answered, both response and context relevance are good, and the response is grounded in the provided context:
  * This shows when question_answered >= {min_question_answered} AND response_relevance >= {min_response_relevance} AND context_relevance >= {min_context_relevance} AND response_groundedness >= {min_groundedness}.
  * Choose **"end"**.
* Safeguards / commonsense:
  * **Avoid reiterations:** At most **one** retrieval pass and **one** optional filter pass per question. If these do not help, **generate** (then likely **end**).
  * If the last action was "retrieve" and there is now non-empty retrieval but no generation yet, prefer **"generate"**.
  * If repeated steps have not improved metrics or added new information, prefer **"generate"** or **"end"** (if acceptable answer exists).
  * **Do NOT return "end"** if no generation result is currently present.

## Scope
Question should be answerable when fitting within this defined scope:
{scope}

## Output format (STRICT)
Return EXACTLY ONE compact JSON object with this schema (no markdown fences, no prose before/after):
{{
  "action_type": "retrieve" | "filter" | "generate" | "end",
  "settings": null | {{
    # If action_type == "retrieve":
    "queries": string[],
    "top_k": int,
    "context_size_c": int
    # If action_type == "filter":
    #   option == "query":
    #     include "option": "query", "query": string, "threshold_query_relevance": float in [0,1]
    #   option == "generation_based":
    #     include "option": "generation_based", "gen_result": string
    # If action_type == "generate":
    #     include "additional_comment": string or null
  }}
  # "score" key MUST NOT be included in your output; it is input-only.
}}

## Formatting constraints (MANDATORY)
* Output ONLY the JSON object (no code fences, no additional text).
* Choose exactly ONE action.
* Ensure the JSON strictly matches the schema above.
* For "filter" choose exactly one valid mode and include only its required fields.
* For "retrieve" provide at least one query, and set both `top_k` and `context_size_c`.
* For "generate" you MAY set `additional_comment` to guide style/faithfulness/focus.

## DECIDE NOW
Think briefly. Then OUTPUT ONLY the JSON object. Be sure it is a VALID JSON object and always return EXACTLY ONE JSON object (not nothing, neither more than one).
"""


# ---------------------------
# Parsing helpers
# ---------------------------

class ActionParseError(ValueError):
    pass


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except Exception as e:
        raise ActionParseError(f"Expected float in [{lo},{hi}], got {x!r}") from e


def _ensure_int(x: Any, name: str) -> int:
    if isinstance(x, bool):
        raise ActionParseError(f"{name} must be int, not bool")
    try:
        xi = int(x)
        if xi < 0:
            raise ActionParseError(f"{name} must be non-negative")
        return xi
    except Exception as e:
        raise ActionParseError(f"{name} must be int, got {x!r}") from e


def _ensure_str(x: Any, name: str) -> str:
    if not isinstance(x, str):
        raise ActionParseError(f"{name} must be string, got {type(x).__name__}")
    s = x.strip()
    if not s:
        raise ActionParseError(f"{name} must be non-empty")
    return s


def _ensure_str_list(x: Any, name: str) -> List[str]:
    if not isinstance(x, list):
        raise ActionParseError(f"{name} must be a list of strings")
    out = []
    for i, v in enumerate(x):
        out.append(_ensure_str(v, f"{name}[{i}]"))
    if not out:
        raise ActionParseError(f"{name} must contain at least one string")
    return out


def _extract_first_json_object(raw_text: str) -> Dict[str, Any]:
    """
    Expect the model to output exactly one JSON object.
    If there's noise, try to salvage the first {...} block.
    """
    text = (raw_text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise ActionParseError("No JSON object found in output")
        try:
            return json.loads(m.group(0))
        except Exception as e:
            raise ActionParseError(f"Failed to parse JSON: {e}") from e


def build_action_from_model_output(raw_text: str) -> Action:
    """
    Parse model JSON and construct an Action dataclass.
    """
    obj = _extract_first_json_object(raw_text)
    action_type = obj.get("action_type")
    if not isinstance(action_type, str):
        raise ActionParseError("action_type must be a string")
    action_type = action_type.strip().lower()
    
    if action_type not in {"retrieve", "filter", "generate", "end"}:
        raise ActionParseError(f"Unsupported action_type: {action_type!r}")
    
    settings = obj.get("settings", None)
    
    if action_type == "retrieve":
        if not isinstance(settings, dict):
            raise ActionParseError("settings must be an object for 'retrieve'")
        queries = _ensure_str_list(settings.get("queries"), "settings.queries")
        top_k = _ensure_int(settings.get("top_k"), "settings.top_k")
        context_size_c = _ensure_int(settings.get("context_size_c"), "settings.context_size_c")
        ds = RetrieveSettings(queries=queries, top_k=top_k, context_size_c=context_size_c)
        return Action(action_type="retrieve", settings=ds, score=None)
    
    elif action_type == "filter":
        if not isinstance(settings, dict):
            raise ActionParseError("settings must be an object for 'filter'")
        option = _ensure_str(settings.get("option"), "settings.option").lower()
        if option == "query":
            query = _ensure_str(settings.get("query"), "settings.query")
            thr = settings.get("threshold_query_relevance")
            thr = _clamp(thr, 0.0, 1.0)
            ds = FilterSettings(option="query", query=query, threshold_query_relevance=thr)
            return Action(action_type="filter", settings=ds, score=None)
        elif option == "generation_based":
            gen_result = _ensure_str(settings.get("gen_result"), "settings.gen_result")
            ds = FilterSettings(option="generation_based", gen_result=gen_result)
            return Action(action_type="filter", settings=ds, score=None)
        else:
            raise ActionParseError(f"Invalid filter option: {option!r}")
    
    elif action_type == "generate":
        # settings MAY be null/None or dict with additional_comment
        addc: Optional[str] = None
        if settings is None:
            pass
        elif isinstance(settings, dict):
            ac = settings.get("additional_comment", None)
            if ac is not None:
                addc = _ensure_str(ac, "settings.additional_comment")
        else:
            raise ActionParseError("settings must be null or object for 'generate'")
        ds = GenerateSettings(additional_comment=addc)
        return Action(action_type="generate", settings=ds, score=None)
    
    elif action_type == "end":
        return Action(action_type="end", settings=None, score=None)
    
    raise ActionParseError("Unhandled action_type")
    
    # ---------------------------
    # Prompt rendering
    # ---------------------------


def _to_jsonable(o):
    # Recursively turn dataclasses into dicts
    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, dict):
        return {k: _to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_to_jsonable(v) for v in o]
    return o


def render_decider_prompt(
        *,
        user_input: str,
        scope: str,
        actions: List[Dict[str, Any]],
        retrieval: List[Dict[str, Any]],
        generation_result: Optional[str],
        metrics: Optional[Dict[str, Optional[float]]],
        # Quality thresholds:
        min_response_relevance: float = 0.9,
        min_context_relevance: float = 0.75,
        min_groundedness: float = 0.75,
        min_question_answered: float = 0.75,
        min_faithfulness: float = 0.75,
        # Cost knobs / guardrails:
        default_top_k_start: int = 20,
        default_context_c_start: int = 3,
        max_top_k: int = 50,
        max_context_c: int = 6,
) -> str:
    """
    Renders the DECIDER prompt with strict output instructions and cost-aware policy.
    """
    
    def _block(title: str, payload: Any) -> str:
        if payload is None or (isinstance(payload, (list, dict)) and not payload):
            return f"{title}:\n(EMPTY)\n"
        # NEW: normalize before dumping
        payload = _to_jsonable(payload)
        if isinstance(payload, (list, dict)):
            pretty = json.dumps(payload, ensure_ascii=False, indent=2)
            return f"{title}:\n{pretty}\n"
        payload_str = str(payload).strip()
        if not payload_str:
            return f"{title}:\n(EMPTY)\n"
        return f"{title}:\n{payload_str}\n"
    
    user_input_block = _block("USER INPUT", user_input)
    actions_block = _block("ACTIONS (history)", actions)
    retrieval_block = _block("RETRIEVAL", retrieval)
    generation_block = _block("GENERATION RESULT", generation_result or "")
    metrics_block = _block("METRICS", metrics or {})
    
    prompt = DECIDER_PROMPT.format(
        user_input_block=user_input_block,
        actions_block=actions_block,
        retrieval_block=retrieval_block,
        generation_block=generation_block,
        metrics_block=metrics_block,
        min_response_relevance=min_response_relevance,
        min_context_relevance=min_context_relevance,
        min_groundedness=min_groundedness,
        min_faithfulness=min_faithfulness,
        min_question_answered=min_question_answered,
        default_top_k_start=default_top_k_start,
        default_context_c_start=default_context_c_start,
        max_top_k=max_top_k,
        max_context_c=max_context_c,
        scope=scope,
    )
    return textwrap.dedent(prompt).strip()


# ---------------------------
# LLM Interactor (same style as your LLMRelevanceFilter)
# ---------------------------

class LLMDecider:
    """
    Thin wrapper over Azure OpenAI chat or Ollama to generate a single JSON decision.
    Mirrors the 'LLMRelevanceFilter' calling pattern.
    """
    
    def __init__(self, model: str, api_key: Optional[str], api_base: Optional[str]):
        self.model = model
        self.temperature = 0.2
        self.max_tokens = 4096
        
        self.chat_history = []
        self.system_prompt = (
            "You are a strict controller that outputs ONLY a single JSON object per request. "
            "Never add code fences. Never add explanations."
        )
        self.chat_history.append({"role": "system", "content": self.system_prompt})
        
        if model in ["gpt-5", "gpt-4.1", "o3"]:
            api_type = os.getenv("OPEN_AI_TYPE", "")
            if api_type == "azure":
                api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
                api_base = api_base or os.getenv("AZURE_OPENAI_API_BASE", "")
                api_version = "2024-08-01-preview" if model in ["gpt-5", "gpt-4.1"] else "2024-02-15-preview"
                self.deployment_name = "azure-gpt-5-mini" if model == "gpt-5" else ("azure-gpt-4.1" if model == "gpt-4.1" else "azure-gpt-o3-mini")
                self.client = OpenAI(api_key=api_key, base_url=api_base)
            else:
                api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
                self.deployment_name = "gpt-5" if model == "gpt-5" else ("gpt-4.1" if model == "gpt-4.1" else "o3")
                self.client = OpenAI(api_key=api_key)
            self.generate_response = self._generate_azure_response  # bind
        elif model == "llama3_3-70b":
            self.api_base = api_base or os.getenv("WARHOL_OLLAMA_API_BASE", "")
            self.deployment_name = "llama3.3:70b"
            self.generate_response = self._generate_ollama_response  # bind
        else:
            raise ValueError(f"Unsupported decider LLM model: {model}")
    
    def _generate_azure_response(self, prompt: str) -> str:
        self.chat_history.append({"role": "user", "content": prompt})
        try:
            if self.deployment_name in ["o3", "gpt-5"]:
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=self.chat_history,
                    max_completion_tokens=self.max_tokens,
                )
            else:
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=self.chat_history,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            response_text = response.choices[0].message.content
        except Exception as e:
            logger.error(f"[AzureOpenAI Decider] Failed to generate response: {e}", exc_info=True)
            raise RuntimeError(f"AzureOpenAI Decider encountered an issue: {e}.")
        logger.debug(f"[AzureOpenAI Decider] Response:\n{response_text}")
        self.chat_history.append({"role": "assistant", "content": response_text})
        return response_text
    
    def _generate_ollama_response(self, prompt: str) -> str:
        self.chat_history.append({"role": "user", "content": prompt})
        payload = {
            "model": self.deployment_name,
            "messages": self.chat_history,
            "temperature": self.temperature,
            "options": {"num_predict": self.max_tokens},
            "stream": False,
            "think": False,
        }
        url = f"{self.api_base}/api/chat"
        try:
            logger.debug(f"[Ollama Decider] POST {url} with payload keys: {list(payload.keys())}")
            response = requests.post(url, json=payload, timeout=120.0)
            logger.debug(f"[Ollama Decider] Status {response.status_code}")
            response.raise_for_status()
            response_json = response.json()
            response_text = response_json["message"]["content"]
        except requests.exceptions.JSONDecodeError as e:
            self.chat_history.pop()
            logger.error(f"[Ollama Decider] JSON decode error: {e}")
            logger.debug(f"[Ollama Decider] Raw response:\n{response.text}")
            raise RuntimeError(f"Ollama Decider encountered invalid JSON: {e}")
        except Exception as e:
            self.chat_history.pop()
            logger.error(f"[Ollama Decider] Failed to generate response: {e}", exc_info=True)
            raise RuntimeError(f"Ollama Decider encountered an issue: {e}.")
        self.chat_history.append({"role": "assistant", "content": response_text})
        logger.debug(f"[Ollama Decider] Response:\n{response_text}")
        return response_text


default_scope = """Question-answering system for expert clinicians on topics of Oral and Maxillofacial Surgery (OMFS/MKG) or similar related topics.
Knowledge base (for retrieval): Official AWMF Oral and Maxillofacial Surgery (OMFS/MKG) guidelines.
"""


# ---------------------------
# Component
# ---------------------------

class AdaptDecisionComponent(AbstractComponent, variant_name="adapt_decision"):
    """
    A self-contained component that:
      1) Renders the DECIDER prompt with cost-aware & quality thresholds.
      2) Calls an internal LLM interactor (same style as LLMRelevanceFilter).
      3) Parses it into an Action dataclass.
      4) Routes to the appropriate next component based on the decided action.
    """
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        # Required wiring
        self.user_input_template = parameters["user_input"]
        self.action_tracker_ID = parameters["action_tracker_ID"]
        self.retrieve_component_ID = parameters["retrieve_component_ID"]
        self.filter_component_ID = parameters["filter_component_ID"]
        self.generator_component_ID = parameters["generator_component_ID"]
        self.end_component_ID = parameters["end_component_ID"]
        
        # LLM options (as requested)
        self.llm_option_model = parameters.get("llm_option_model", "gpt-4.1").strip()
        self.llm_option_api_key = parameters.get("llm_option_api_key", None)
        self.llm_option_api_base = parameters.get("llm_option_api_base", None)
        self.llm_decider = LLMDecider(self.llm_option_model, self.llm_option_api_key, self.llm_option_api_base)
        
        # Limits for prompt size (avoid giant prompts)
        self.scope = parameters.get("scope") or default_scope
        self.max_actions_history = int(parameters.get("max_actions_history", 12))
        self.max_retrieval_text_chars = int(parameters.get("max_retrieval_text_chars", 800))
        
        # Decision policy thresholds (with defaults)
        self.min_response_relevance = float(parameters.get("min_response_relevance", 0.9))
        self.min_context_relevance = float(parameters.get("min_context_relevance", 0.75))
        self.min_groundedness = float(parameters.get("min_groundedness", 0.75))
        self.min_question_answered = float(parameters.get("min_question_answered", 0.75))
        self.min_faithfulness = float(parameters.get("min_faithfulness", 0.75))
        
        # Cost knobs / guardrails
        self.default_top_k_start = int(parameters.get("default_top_k_start", 20))
        self.default_context_c_start = int(parameters.get("default_context_c_start", 3))
        self.max_top_k = int(parameters.get("max_top_k", 50))
        self.max_context_c = int(parameters.get("max_context_c", 6))
        
        self.next_component_id: Optional[str] = None
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    # ---------------------------
    # Utilities
    # ---------------------------
    
    def _truncate_retrieval_for_prompt(self, retrieval: List[WeaviateSearchChunkResult]) -> List[Dict[str, Any]]:
        trimmed: List[Dict[str, Any]] = []
        for item in retrieval:
            rc = item.retrieved_chunk
            text = (rc.get("text") or "")
            if isinstance(text, str) and len(text) > self.max_retrieval_text_chars:
                text = text[: self.max_retrieval_text_chars] + "…"
            trimmed.append(
                {
                    "retrieved_chunk": {
                        "text": text,
                        "headers": rc.get("headers"),
                        "guideline_title": rc.get("guideline_title"),
                        "reference_id": rc.get("reference_id"),
                        "chunk_index": rc.get("chunk_index"),
                    },
                    "score": item.score,
                    "rerank_score": item.rerank_score,
                },
            )
        return trimmed
    
    def _truncate_actions_for_prompt(self, actions: List[Any]) -> List[Dict[str, Any]]:
        pruned = actions[-self.max_actions_history:] if actions else []
        out = []
        
        def _get_field(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)
        
        for a in pruned:
            action_type = _get_field(a, "action_type")
            settings = _get_field(a, "settings")
            score = _get_field(a, "score")
            
            # Normalize dataclasses to dicts
            settings = _to_jsonable(settings)
            score = _to_jsonable(score)
            
            cleaned = {"action_type": action_type, "settings": settings}
            
            if isinstance(score, dict):
                cleaned["score"] = {
                    k: score.get(k)
                    for k in [
                        "question_answered",
                        "response_relevance",
                        "context_relevance",
                        "response_groundedness",
                        "faithfulness",
                    ]
                    if k in score
                }
            
            out.append(cleaned)
        return out
    
    def _choose_next_component(self, decided_action: Action) -> str:
        atype = decided_action.action_type
        if atype == "retrieve":
            return self.retrieve_component_ID
        if atype == "filter":
            return self.filter_component_ID
        if atype == "generate":
            return self.generator_component_ID
        if atype == "end":
            return self.end_component_ID
        
        logger.warning(f"[{self.id}] Unknown action_type '{atype}'.")
        raise ValueError(f"Unknown action_type '{atype}'")
    
    # ---------------------------
    # Execute
    # ---------------------------
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        1) Prepare state (user_input, actions, retrieval, generation, metrics).
        2) Render the DECIDER prompt.
        3) Call the LLMDecider to obtain the JSON decision.
        4) Parse into an Action.
        5) Store & route.
        """
        user_input = render_template(self.user_input_template, data)
        actions_history = data.get(f"{self.action_tracker_ID}.actions", []) or []
        current_retrieval = data.get(f"{self.action_tracker_ID}.retrieval", []) or []
        current_generation = data.get(f"{self.action_tracker_ID}.generation_result", None)
        current_metrics = data.get(f"{self.action_tracker_ID}.metrics", None)
        
        actions_for_prompt = self._truncate_actions_for_prompt(actions_history)
        retrieval_for_prompt = self._truncate_retrieval_for_prompt(current_retrieval)
        
        prompt = render_decider_prompt(
            user_input=user_input,
            scope=self.scope,
            actions=actions_for_prompt,
            retrieval=retrieval_for_prompt,
            generation_result=current_generation,
            metrics=current_metrics,
            min_response_relevance=self.min_response_relevance,
            min_context_relevance=self.min_context_relevance,
            min_groundedness=self.min_groundedness,
            min_faithfulness=self.min_faithfulness,
            min_question_answered=self.min_question_answered,
            default_top_k_start=self.default_top_k_start,
            default_context_c_start=self.default_context_c_start,
            max_top_k=self.max_top_k,
            max_context_c=self.max_context_c,
        )
        
        logger.debug(f"[{self.id}] DECIDER prompt length: {len(prompt)} characters")
        
        # Generate with the configured LLM interactor (same pattern as LLMRelevanceFilter)
        raw_output: str = self.llm_decider.generate_response(prompt)
        if not isinstance(raw_output, str):
            raise RuntimeError(
                f"[{self.id}] Decider generate_response must return str, got {type(raw_output).__name__}",
            )
        
        logger.debug(f"[{self.id}] Raw model output: {raw_output}")
        
        try:
            decided_action: Action = build_action_from_model_output(raw_output)
        except Exception as e:
            logger.exception(f"[{self.id}] Failed to parse model output into Action: {e}")
            decided_action = Action(action_type="end", settings=None, score=None)
        
        data[f"{self.id}.action_output"] = decided_action
        
        next_component_id = self._choose_next_component(decided_action)
        logger.info(f"[{self.id}] Decided action={decided_action.action_type}; routing to '{next_component_id}'")
        return data, next_component_id
    
    # ---------------------------
    # Metadata
    # ---------------------------
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "user_input": {
                "type": "str",
                "description": "Original question to be answered (templated).",
            },
            "action_tracker_ID": {
                "type": "str",
                "description": "ID of action tracker component providing actions/retrieval/generation/metrics.",
            },
            "retrieve_component_ID": {
                "type": "str",
                "description": "ID to route to when the decision is 'retrieve'.",
            },
            "filter_component_ID": {
                "type": "str",
                "description": "ID to route to when the decision is 'filter'.",
            },
            "generator_component_ID": {
                "type": "str",
                "description": "ID to route to when the decision is 'generate'.",
            },
            "end_component_ID": {
                "type": "str",
                "description": "ID to route to when the decision is 'end'.",
            },
            
            # LLM options (match your provided schema)
            "llm_option_model": {
                "type": "string",
                "description": "Model used for the decider; Options: [gpt-5-chat, gpt-4.1, gpt-3.5, llama3_3-70b]",
                "default": "gpt-4.1",
            },
            "llm_option_api_key": {
                "type": "string",
                "description": "API key for the chosen LLM (Azure OpenAI for GPT variants).",
                "default": "",
            },
            "llm_option_api_base": {
                "type": "string",
                "description": "API base URL for the chosen LLM (Azure endpoint for GPT variants, Ollama base for llama).",
                "default": "",
            },
            
            # Decision policy thresholds
            "min_response_relevance": {
                "type": "float",
                "default": 0.9,
                "description": "Minimum Response Relevance to avoid re-generation.",
            },
            "min_context_relevance": {
                "type": "float",
                "default": 0.75,
                "description": "Minimum Context Relevance; below this triggers more retrieval.",
            },
            "min_groundedness": {
                "type": "float",
                "default": 0.75,
                "description": "Minimum Response Groundedness; below this triggers filter/retrieve.",
            },
            "min_faithfulness": {
                "type": "float",
                "default": 0.75,
                "description": "Minimum Faithfulness; below this triggers filter/retrieve.",
            },
            "min_question_answered": {
                "type": "float",
                "default": 0.75,
                "description": "Threshold for 'question adequately answered'.",
            },
            
            # Cost knobs / guardrails
            "default_top_k_start": {
                "type": "int",
                "default": 20,
                "description": "Starting top_k for retrieval (good default ~20).",
            },
            "default_context_c_start": {
                "type": "int",
                "default": 3,
                "description": "Starting context window C (neighbors per side).",
            },
            "max_top_k": {
                "type": "int",
                "default": 50,
                "description": "Hard ceiling for top_k to control cost.",
            },
            "max_context_c": {
                "type": "int",
                "default": 6,
                "description": "Hard ceiling for context_size_c to control cost.",
            },
            
            # Prompt-size controls
            "max_actions_history": {
                "type": "int",
                "default": 12,
                "description": "Max previous actions included in the prompt.",
            },
            "max_retrieval_text_chars": {
                "type": "int",
                "default": 800,
                "description": "Max chars from each retrieval text included in the prompt.",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "adapt_decision.action_output": {
                "type": Action,
                "description": "Chosen action (dataclass) with settings to execute next.",
            },
        }
