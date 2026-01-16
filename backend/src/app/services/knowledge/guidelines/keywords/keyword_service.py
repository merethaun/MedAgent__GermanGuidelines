import json
import os
import re
from collections import Counter
from typing import List, Literal, Optional, Dict, Sequence, Tuple

import requests
import yake

from app.utils.llama_index.llm_interaction import OllamaLlamaIndexLLM, AzureOpenAILlamaIndexLLM
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

KEYWORDS_PROMPT = """You extract concise, domain-relevant German keyphrases ({min_range}-{max_range} words preferred) from a clinical guideline passage.

CONTEXT/SCOPE:
{scope_description}

GUIDANCE (very important):
- Extract at most {max_range} distinct keyphrases.
- Ignore generic words, section scaffolding, citation boilerplate, and formatting artifacts.
- Treat hyphens and slashes as spaces (e.g., "MRONJ-Therapie" → "mronj therapie").
- Avoid single-word stopwords.
{guidance_additions}

IGNORE (examples, not exhaustive):
{ignore_terms}

PAY ATTENTION TO (examples of useful term types):
{important_terms}

FORMAT:
Output ONLY a JSON array of strings. Example:
["Symptome", "können", "Weisheitszähne"]

{few_shot_examples}

TEXT:
\"\"\"{text}\"\"\"

OUTPUT:
"""

DEFAULT_KEYWORD_SETTINGS = {
    "ignore_terms": [
        "Tabelle", "Abbildung", "Leitlinie",
    ],
    "important_terms": [
        "kann bestehen", "besteht", "indiziert", "Indikation", "kann", "sollte", "keine", "nicht", "soll", "können", "sollten", "notwendig",
        "empfehlenswert", "empfehlen", "sollten",
    ],
    "examples": [
        {
            "text": "Eine dreidimensionale Bildgebung (beispielsweise DVT/CT) kann indiziert sein, wenn in der konventionellen zweidimensionalen Bildgebung Hinweise auf eine unmittelbare Lagebeziehung zu Risikostrukturen oder pathologischen Veränderungen vorhanden sind und gleichzeitig aus Sicht des Behandlers weitere räumliche Informationen entweder für die Risikoaufklärung des Patienten, Eingriffsplanung oder auch für die intraoperative Orientierung erforderlich sind.",
            "keywords": [
                "retention",
                "position des weisheitszahnes",
                "nach abschluss des wurzelwachstums",
                "okklusionsebene nicht erreicht",
                "partiell retiniert", "anteile der krone mundhöhle erreicht",
                "anteile der krone über parodontalapparat des benachbarten 12 jahr molaren",
                "vollständig retiniert",
                "ohne verbindung zur mundhöhle",
                "impaktiert",
                "vollständige knöcherne einbettung des zahnes",
                "verlagert",
                "achse oder position von regulärer durchbruchsrichtung abweicht",
            ],
        },
        {
            "text": "Der Begriff der Retention bezeichnet eine Position des Weisheitszahnes, bei der nach Abschluss des Wurzelwachstums die Okklusionsebene nicht erreicht wird. Als partiell retiniert gilt hierbei ein Zahn, bei dem Anteile der Krone die Mundhöhle erreichen oder über den Parodontalapparat des benachbarten 12 Jahr Molaren mit der Mundhöhle in Verbindung stehen. Als vollständig retiniert gelten Zähne, die keinerlei Verbindung zur Mundhöhle aufweisen. Der Begriff der Impaktierung bezeichnet die vollständige knöcherne Einbettung des Zahnes. Als verlagert gilt ein Zahn dessen Achse oder Position von der regulären Durchbruchsrichtung abweicht.\nGemäß diesen Definitionen befasst sich die Leitlinie vorwiegend mit Erkrankungsbildern, die durch folgende ICD-Codes beschrieben sind:",
            "keywords": [
                "retention",
                "position des weisheitszahnes",
                "nach abschluss des wurzelwachstums",
                "okklusionsebene nicht erreicht",
                "partiell retiniert",
                "anteile der krone mundhöhle erreicht",
                "anteile der krone über parodontalapparat des benachbarten 12 jahr molaren",
                "vollständig retiniert",
                "ohne verbindung zur mundhöhle",
                "impaktiert",
                "vollständige knöcherne einbettung des zahnes",
                "verlagert",
                "achse oder position von regulärer durchbruchsrichtung abweicht",
            ],
        },
        {
            "text": "Welche Symptome können im Zusammenhang mit Weisheitszähne vorkommen?",
            "keywords": [
                "symptome",
                "können",
                "weisheitszähne",
            ],
        },
        {
            "text": "Welches Material ist für die retrograde Füllung empfehlenswert und welches soll nicht verwendet werden?",
            "keywords": [
                "soll nicht verwendet werden",
                "retrograde füllung",
                "empfehlenswert",
                "material",
            ],
        },
        {
            "text": "Klinische und radiologische Symptome im Zusammenhang mit Weisheitszähnen können typischerweise sein:\n"
                    "• Perikoronare Infektion\n• Erweiterung des radiologischen Perikoronarraumes\n"
                    "• Perikoronare Auftreibung (beispielsweise durch Zystenbildung)\n• Schmerzen/Spannungsgefühl im Kiefer-Gesichtsbereich\n"
                    "• Parodontale Schäden, insbesondere distal an 12-Jahr Molaren\n• Resorptionen an Nachbarzähnen (siehe Hintergrundtext unter 9.2)\n"
                    "• Elongation/Kippung\n• kariöse Zerstörung/Pulpitis",
            "keywords": [
                "klinische symptome",
                "radiologische symptome",
                "weisheitszähne",
                "können",
                "perikoronare infektion",
                "erweiterung radiologischen perikoronarraumes",
                "perikoronare auftreibung",
                "schmerzen im kiefer gesichtsbereich",
                "spannungsgefühlt im kiefer gesichtsbereich",
                "parodontale schäden",
                "distal an 12 jahr molaren",
                "resorptionen an nachbarzähnen",
                "elongation",
                "kippung",
                "kariöse zerstörung",
                "pulpitis",
            ],
        },
    
    ],
    "scope": "German guidelines for Oral and Maxillofacial surgery from the AWMF. ",
    "guidance_additions": [
        "Prefer multi-word medical terms, diagnoses, procedures, imaging, therapies, risk factors, patient groups, and staging systems.",
    ],
    "min_range": 1,
    "max_range": None,  # default to number of words in text
}


class KeywordService:
    def __init__(self):
        self.translate_cache: Dict[Tuple[str, str, str], str] = {}
        self.session = requests.Session()
    
    @staticmethod
    def _normalize(s: str) -> str:
        s = s.lower()
        s = re.sub(r"[\u2010-\u2015\-_/]", " ", s)
        return s
    
    @staticmethod
    def _is_noise(term: str, ignore_terms: Optional[List[str]] = None) -> bool:
        generic = ignore_terms if ignore_terms is not None else DEFAULT_KEYWORD_SETTINGS["ignore_terms"]
        return term in generic
    
    @staticmethod
    def _suppress_subphrases(phrases: List[str]) -> List[str]:
        """
        Keep longer/more specific phrases; drop terms that occur as whole-word substrings
        of any kept phrase. Example:
          ["zusammenhang mit weisheitszähne", "weisheitszähne vorkommen", "weisheitszähne",
           "zusammenhang", "vorkommen", "symptome"]
        -> ["zusammenhang mit weisheitszähne", "weisheitszähne vorkommen", "symptome"]
        """
        if not phrases:
            return []
        
        # Stable order reference for restoring later
        original_index = {p: i for i, p in enumerate(phrases)}
        
        def token_count(s: str) -> int:
            return len(s.split())
        
        # Prefer longer phrases first; ties by char length, then original order
        by_size = sorted(
            phrases,
            key=lambda s: (-token_count(s), -len(s), original_index[s]),
        )
        
        kept: List[str] = []
        for p in by_size:
            # whole-word containment check; \b works with Unicode letters
            pat = re.compile(rf'\b{re.escape(p)}\b')
            if any(pat.search(k) for k in kept):
                continue
            kept.append(p)
        
        # Restore original ranking order
        kept.sort(key=lambda s: original_index[s])
        return kept
    
    def extract_yake(
            self, text: str, language: str, min_keywords: Optional[int] = None, max_keywords: Optional[int] = None,
            max_n_gram_size: Optional[int] = 3, deduplication_threshold: Optional[float] = 0.9,
            ignore_terms: Optional[List[str]] = None, suppress_subphrases: bool = True,
            headroom: int = 5,
    ) -> List[str]:
        """
        Extract normalized keyword candidates from `text` using YAKE and return a ranked list.

        Controls:
          - min_keywords: desired minimum number of results (best-effort).
          - max_keywords: hard cap on number of results returned.
          - ignore_terms: additional terms to filter out (case-insensitive match against normalized terms).
          - important_terms: terms to prioritize in ranking if they appear as substrings of a candidate.
          - headroom: extra candidates to request from YAKE to offset filtering losses.

        Pipeline:
          1) YAKE extraction with a dynamic `top` to satisfy min/max targets.
          2) Sort candidates by ascending YAKE score to prefer stronger phrases first.
          3) Normalize each phrase and drop obvious noise.
          4) Count duplicates (useful if multiple extractors are merged upstream).
          5) Rank unique phrases by: important-hit ↓, frequency ↓, length ↓, then alphabetical ↑.
        """
        # --- 1) Decide how many candidates to request from YAKE ---
        min_keywords = min_keywords or DEFAULT_KEYWORD_SETTINGS["min_range"]
        min_keywords = min_keywords or DEFAULT_KEYWORD_SETTINGS["min_range"]
        ignore_terms = ignore_terms if ignore_terms is not None else DEFAULT_KEYWORD_SETTINGS["ignore_terms"]
        
        desired = 10
        if min_keywords is not None:
            desired = max(desired, int(min_keywords))
        if max_keywords is not None:
            desired = max(desired, int(max_keywords))
        desired = min(200, max(10, desired + int(headroom)))  # modest cap & headroom
        
        kw_extractor = yake.KeywordExtractor(
            lan=language, n=max_n_gram_size, top=desired, dedupLim=deduplication_threshold, dedupFunc="seqm", windowsSize=1, features=None,
        )
        
        # 1–2) YAKE extraction → sort by score (lower is better)
        keyword_candidates = kw_extractor.extract_keywords(text)  # List[Tuple[str, float]]
        ranked_keyphrases = [phrase for phrase, score in sorted(keyword_candidates, key=lambda pair: pair[1])]
        
        # 3) Normalize & filter (strip trailing periods common in PDF spans)
        normalized_candidates: List[str] = []
        for phrase in ranked_keyphrases:
            normalized_phrase = self._normalize(phrase).rstrip(".")
            if normalized_phrase and not self._is_noise(normalized_phrase, ignore_terms):
                normalized_candidates.append(normalized_phrase)
        
        # 4) Count occurrences across candidates
        frequency_by_phrase = Counter(normalized_candidates)
        
        # 5) Final ranking: frequency ↓, length ↓, lexicographic ↑
        ranked_unique_phrases = sorted(
            frequency_by_phrase,
            key=lambda term: (-frequency_by_phrase[term], -len(term), term),
        )
        if suppress_subphrases:
            ranked_unique_phrases = self._suppress_subphrases(ranked_unique_phrases)
        
        return ranked_unique_phrases
    
    @staticmethod
    def _select_llm(
            *, model: Literal["gpt-5", "gpt-4.1", "o3", "llama3_3-70b"], api_key: Optional[str] = None,
            api_base: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 512, **kwargs,
    ):
        """Create a LlamaIndex LLM instance per your setup snippet."""
        if model in ("gpt-4.1", "o3", "gpt-5"):
            api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
            api_base = api_base or os.getenv("AZURE_OPENAI_API_BASE", "")
            
            api_version = "2024-08-01-preview" if model == "gpt-4.1" else "2024-02-15-preview"
            
            api_type = os.getenv("OPEN_AI_TYPE", "")
            if api_type == "azure":
                deployment_name = "azure-gpt-5-mini" if model == "gpt-5" else ("azure-gpt-4.1" if model == "gpt-4.1" else "azure-gpt-o3-mini")
            else:
                deployment_name = "gpt-5" if model == "gpt-5" else ("gpt-4.1" if model == "gpt-4.1" else "o3")
            
            logger.info(f"[Keywords] Using Azure model: {deployment_name}")
            return AzureOpenAILlamaIndexLLM(
                deployment_name=deployment_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                api_base=api_base,
                api_version=api_version,
            )
        elif model == "llama3_3-70b":
            logger.info("[Keywords] Using Ollama model: llama3.3:70b (requested 'llama3_3-70b')")
            api_base = kwargs.get("api_base", None) or os.getenv("WARHOL_OLLAMA_API_BASE", "")
            return OllamaLlamaIndexLLM(
                model="llama3.3:70b",
                api_base=api_base,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unsupported LLM model: {model}")
    
    @staticmethod
    def _call_llm(llm, prompt: str):
        try:
            llm_response = llm.complete(prompt)  # returns a string
        except AttributeError:
            llm_response = llm.predict(prompt)
        
        if not isinstance(llm_response, str):
            llm_text = getattr(llm_response, "text", "")
        else:
            llm_text = llm_response
        return llm_text
    
    @staticmethod
    def _extract_json_array(text: str) -> List[str]:
        """
        Robustly find and parse the first JSON array in the LLM output.
        Accepts answers that might contain extra prose around the array.
        """
        # Fast path: direct parse
        try:
            data = json.loads(text)
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return data
        except Exception:
            pass
        
        # Fallback: locate first [...] block
        m = re.search(r"\[[\s\S]*\]", text)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, list) and all(isinstance(x, str) for x in data):
                    return data
            except Exception:
                pass
        
        logger.warning("[Keywords] Could not parse JSON array from LLM output.")
        return []
    
    @staticmethod
    def _format_prompt(
            text: str, min_range: int, max_range: int, scope_description: str, guidance_additions: List[str], ignore_terms: List[str],
            important_terms: List[str], examples: List[Dict] = None,
    ) -> str:
        def _bullets(items) -> str:
            if items is None:
                return ""
            if isinstance(items, str):
                items = [items]
            items = [str(x).strip() for x in items if str(x).strip()]
            return ("- " + "\n- ".join(items)) if items else ""
        
        def _render_few_shots(ex_list: List[Dict]) -> str:
            rendered = []
            for i, ex in enumerate(ex_list or []):
                t = str(ex.get("text", "")).strip()
                kws = ex.get("keywords", [])
                if isinstance(kws, str):
                    kws = [kws]
                kws = [k for k in kws if str(k).strip()]
                if not t or not kws:
                    continue
                rendered.append(
                    f"Example {i + 1} (format is mandatory):\n"
                    f"TEXT:\n"
                    f"\"\"\"{t}\"\"\"\n\n"
                    f"OUTPUT:\n"
                    f"{json.dumps(kws, ensure_ascii=False)}",
                )
            if not rendered:
                return ""
            return "\n---\nFEW-SHOT EXAMPLES:\n" + "\n\n".join(rendered) + "\n---\n"
        
        if max_range < min_range:
            max_range = min_range
        
        guidance_block = _bullets(guidance_additions)
        ignore_block = _bullets(ignore_terms)
        attention_block = _bullets(important_terms)
        few_shot_block = _render_few_shots(examples or [])
        
        return KEYWORDS_PROMPT.format(
            min_range=int(min_range), max_range=int(max_range),
            scope_description=str(scope_description or "").strip(), guidance_additions=guidance_block,
            ignore_terms=ignore_block, important_terms=attention_block,
            few_shot_examples=few_shot_block,
            text=text,
        )
    
    @staticmethod
    def _final_rank(phrases: Sequence[str]) -> List[str]:
        freq = Counter(phrases)
        return sorted(freq, key=lambda t: (-freq[t], -len(t), t))
    
    def extract_llm(
            self, text: str, *, model: Literal["gpt-5", "gpt-4.1", "o3", "llama3_3-70b"] = "gpt-4.1", api_key: Optional[str] = None,
            api_base: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 512, scope_description: Optional[str] = None,
            guidance_additions: Optional[list] = None, ignore_terms: Optional[list] = None, important_terms: Optional[list] = None,
            examples: Optional[list] = None, min_keywords: Optional[int] = None, max_keywords: Optional[int] = None, **kwargs,
    ) -> List[str]:
        """
        Extract keywords using an LLM via LlamaIndex.

        Returns:
            List[str]: normalized, deduplicated, ranked phrases.
        """
        llm = self._select_llm(
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        params = DEFAULT_KEYWORD_SETTINGS
        if ignore_terms is not None:
            params["ignore_terms"] = ignore_terms
        if important_terms is not None:
            params["important_terms"] = important_terms
        if examples is not None:
            params["examples"] = examples
        if min_keywords is not None:
            params["min_range"] = min_keywords
        if max_keywords is not None:
            params["max_range"] = max_keywords
        if params["max_range"] is None:
            params["max_range"] = len(text.split())
        if scope_description is not None:
            params["scope"] = scope_description
        if guidance_additions is not None:
            params["guidance_additions"] = guidance_additions
        
        prompt = self._format_prompt(
            text=text, min_range=params["min_range"], max_range=params["max_range"], scope_description=params["scope"],
            guidance_additions=params["guidance_additions"], important_terms=params["important_terms"], ignore_terms=params["ignore_terms"],
            examples=params["examples"],
        )
        
        logger.debug("[Keywords] Sending prompt to LLM for keyword extraction.")
        
        llm_text = self._call_llm(llm, prompt)
        
        raw_list = self._extract_json_array(llm_text)
        
        normalized: List[str] = []
        for phrase in raw_list:
            norm = self._normalize(phrase).rstrip(".")
            if norm and not self._is_noise(norm):
                normalized.append(norm)
        
        ranked = self._final_rank(normalized)
        if max_keywords is not None:
            ranked = ranked[:max_keywords]
        return ranked
