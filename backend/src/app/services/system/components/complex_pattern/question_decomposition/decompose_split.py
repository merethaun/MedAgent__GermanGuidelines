import re
from abc import abstractmethod
from typing import Dict, Any, Tuple, List, Union

from app.services.system.components import render_template
from app.services.system.components.complex_pattern.question_decomposition.abstract_decompose_component import AbstractDecomposeComponent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DECOMPOSE_MULTI_PROMPT = """You decompose a complex query into focused, retrieval-ready subqueries.

{scope_block}
{strategy_block}

Each subquery MUST be:
- self-contained (no pronouns like "it/they/this question")
- specific (include key entities, conditions, and constraints)
- answerable independently from the given scope/index summary
- not a yes/no question
- mutually non-overlapping yet collectively covering the original question

Think briefly, but present the FINAL subqueries inside concise <subquery> section.
STRICT OUTPUT FORMAT (mandatory):
<subquery>
...one subquery...
</subquery>
(repeat for each subquery; do NOT nest blocks)

{few_shot_examples}

ORIGINAL QUERY:
\"\"\"{query}\"\"\"

{retrieval_block}

OUTPUT:
Write the sub-queries in the same language as the original query.
"""


class SplitComponent(AbstractDecomposeComponent, variant_name="split"):
    """
    !!Only makes sense with decompose_merge later on!!
    """
    default_parameters: Dict[str, Any] = {
        # domain/scope control
        "knowledge_scope": "Question-answering system based on German AWMF guidelines for Oral and Maxillofacial Surgery. Prefer definitions, indications/contraindications, diagnostics, and first-line therapy when applicable.",
        "strategy_hint": "Perform a minimal-sufficient decomposition. Split only when the query clearly spans distinct targets or evidence. "
                         "Optionally align splits with guideline structure (diagnosis, treatment, follow-up) IF AND ONLY IF the original query touches more than one of these. "
                         "For diagnosis, focus on standardized criteria and essential differentials only when asked; "
                         "for treatment, focus on recommended therapies and key contraindications when decision-relevant; "
                         "for follow-up, focus on monitoring and major complications only if explicitly queried. "
                         "Avoid phase-by-phase faceting, exhaustive enumerations, or micro-questions.",
        # examples
        "examples": [
            {
                "query": "In welchen Kompartimenten werden odontogene Infektionen mit Ausbreitungstendenz am häufigsten beschrieben und was sind mögliche Komplikationen bei der Ausbreitung in weitere Kompartimente?",
                "subqueries": [
                    "In welchen anatomischen Kompartimenten werden odontogene Infektionen mit Ausbreitungstendenz am häufigsten beschrieben?",
                    "Welche Komplikationen treten bei fortschreitender Ausbreitung von odontogene Infektionen auf?",
                ],
            },
            {
                "query": "Welche möglichen Indikationen können zur Entfernung von Weisheitszähnen bestehen?",
                "subqueries": [
                    "Welche Indikationen zur Entfernung von Weisheitszähnen können bestehen?",
                ],
            },
        ],
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.query_template = self.parameters["query"]
        self.retrieval_template = self.parameters.get("retrieval") or []
        self.knowledge_scope = self.parameters.get("knowledge_scope") or self.default_parameters["knowledge_scope"]
        self.strategy_hint = self.parameters.get("strategy_hint") or self.default_parameters["strategy_hint"]
        self.examples = self.parameters.get("examples") or self.default_parameters["examples"]
        
        self.next_component_id = None
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "query": {
                    "type": "string",
                    "description": "The question to be split into subproblems",
                },
                "retrieval": {
                    "type": "list",
                    "description": "List of current context (ideally, include as list of strings, similar to as generator would receive)",
                    "default": [],
                },
                "knowledge_scope": {
                    "type": "string",
                    "description": "Domain scope instructions for answerability constraints",
                    "default": "German AWMF OMS guidelines ...",
                },
                "strategy_hint": {
                    "type": "string",
                    "description": "Suggestions to split query",
                    "default": "Faceted + multi-hop breakdown focused on entities ...",
                },
                "examples": {
                    "type": "list",
                    "description": "List of examples to be used for splitting (with dict: {query: ..., subqueries: [...]})",
                    "default": "Some examples derived from question dataset",
                },
            },
        )
        return base_params
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "splitter.decompose_prompt": {
                "type": "string",
                "description": "The FULL prompt sent to the model",
            },
            "query_splitter.full_response": {
                "type": "string",
                "description": "The FULL response from the model",
            },
            "query_splitter.subqueries": {
                "type": "list",
                "description": "List[str]: parsed subqueries from <subquery> blocks (after filtering)",
            },
        }
    
    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        """Implement with your model backend (same as HyDE)."""
        pass
    
    @staticmethod
    def _render_prompt(
            query: str,
            retrieval: List[str],
            knowledge_scope: str,
            strategy_hint: str,
            examples: List[Dict[str, Union[str, List[str]]]],
    ) -> str:
        scope_block = ""
        if knowledge_scope:
            scope_block = f"DOMAIN SCOPE:\n{knowledge_scope}\n"
        
        strategy_block = ""
        if strategy_hint:
            strategy_block = f"DECOMPOSE STRATEGY:\n{strategy_hint}\n"
        
        rendered_examples = []
        for i, example in enumerate(examples):
            example_query, example_subqueries = example["query"].strip(), example["subqueries"]
            rendered = "\n".join(f"<subquery>\n{s.strip()}\n</subquery>" for s in example_subqueries)
            rendered_examples.append(f"EXAMPLE {i + 1}:\nQuery: {example_query}\nOutput: {rendered}\n")
        few_shot_examples = (
            "\n---\nFEW-SHOT EXAMPLES (format is mandatory):\n" + "\n\n".join(rendered_examples) + "\n---\n"
            if rendered_examples else ""
        )
        
        query = query.strip()
        retrieval_block = (
                "The query has the following current retrieval context:\n" + "\n".join(f"- {r}" for r in retrieval) + "\n"
        )
        
        prompt = _DECOMPOSE_MULTI_PROMPT.format(
            scope_block=scope_block,
            strategy_block=strategy_block,
            few_shot_examples=few_shot_examples,
            query=query,
            retrieval_block=retrieval_block,
        )
        return prompt
    
    @staticmethod
    def _extract_subqueries(raw_text: str) -> List[str]:
        """Parse <subquery>...</subquery> blocks; gracefully fall back to JSON array if present."""
        if not raw_text:
            return []
        
        # Default: strict block parsing (case-insensitive, dotall)
        blocks = re.findall(r"<subquery>\s*(.*?)\s*</subquery>", raw_text, flags=re.IGNORECASE | re.DOTALL)
        return [(b or "").strip() for b in blocks if (b or "").strip()]
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            query = render_template(self.query_template, data)
            retrieval = render_template(self.retrieval_template, data) if isinstance(self.retrieval_template, str) else self.retrieval_template
            
            decompose_prompt = self._render_prompt(query, retrieval, self.knowledge_scope, self.strategy_hint, self.examples)
            data[f"{self.id}.decompose_prompt"] = decompose_prompt
            
            response = self.generate_response(decompose_prompt)
            data[f"{self.id}.full_response"] = response
            
            subqueries = self._extract_subqueries(response)
            data[f"{self.id}.subqueries"] = subqueries
            
            return data, self.next_component_id
        
        except Exception as e:
            logger.exception(f"[SplitComponent] Failed to split for {self.__class__.__name__} (ID: {self.id}):")
            logger.error(f"[SplitComponent] Error details: {str(e)}", exc_info=True)
            raise RuntimeError(f"SplitComponent execution failed: {e}")
