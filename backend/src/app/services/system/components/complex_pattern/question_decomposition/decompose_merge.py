import re
from abc import abstractmethod
from typing import Dict, Any, Tuple, Union, List

from app.services.system.components import render_template
from app.services.system.components.complex_pattern.question_decomposition.abstract_decompose_component import AbstractDecomposeComponent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_COMPOSE_PROMPT = """You will produce a single, focused final answer to the ORIGINAL QUERY using only the provided SUBQUERIES with EVIDENCE.
- Subqueries with evidence and optional response to the subquery are presented as:
  <subquery>
    <query>...</query>
    Optional: <response>...</response>
    <evidence index=...>...</evidence>... (more evidence) ...
  </subquery>

{scope_block}

Requirements:
- Use ONLY the supplied evidence; do not introduce facts, sources, or numbers that are not present.
- Prefer precise, guideline-style wording and avoid repetition.
- Reconcile overlaps consistently; if uncertainty remains, acknowledge it briefly.

Think briefly, then present the FINAL answer inside a single <answer> section.
Include EXACTLY ONE <answer> section.

STRICT OUTPUT FORMAT (mandatory):
...
<answer>
...concise paragraph answer...
</answer>

ORIGINAL QUERY:
\"\"\"{query}\"\"\"

SUBQUERIES with EVIDENCE:
{rendered_subqueries}

OUTPUT:
- Write the answer in the same language as the original query.
- Return ONLY the blocks specified above; no additional commentary.
"""


class MergeComponent(AbstractDecomposeComponent, variant_name="merge"):
    """
    !!Only makes sense with decompose_split!!
    """
    default_parameters: Dict[str, Any] = {
        # domain/scope control
        "knowledge_scope": "Question-answering system based on German AWMF guidelines for Oral and Maxillofacial Surgery. Prefer definitions, indications/contraindications, diagnostics, and first-line therapy when applicable.",
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.query_template = self.parameters["query"]
        self.subqueries_template = self.parameters["subqueries"]
        self.knowledge_scope = self.parameters.get("knowledge_scope") or self.default_parameters["knowledge_scope"]
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "query": {
                    "type": "string",
                    "description": "The original query that was split into subproblems",
                },
                "subqueries": {
                    "type": "list",
                    "description": "The subqueries extracted from the original query WITH their assigned retrieval. Presented as [{subquery: ..., subresponse: OPTIONAL..., retrieval: [...]}, ...]",
                },
                "knowledge_scope": {
                    "type": "string",
                    "description": "Domain scope instructions for answerability constraints",
                    "default": "German AWMF OMS guidelines ...",
                },
            },
        )
        return base_params
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "merge.compose_prompt": {
                "type": "string",
                "description": "Entire prompt send to generator.",
            },
            "merge.full_response": {
                "type": "string",
                "description": "Entire return by generator.",
            },
            "merge.final_answer": {
                "type": "string",
                "description": "Extracted answer",
            },
        }
    
    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        """Implement with your model backend (same as HyDE)."""
        pass
    
    @staticmethod
    def _render_prompt(
            query: str,
            subqueries: List[Dict[str, Union[str, List[str]]]],
            knowledge_scope: str,
    ) -> str:
        scope_block = ""
        if knowledge_scope:
            scope_block = f"DOMAIN SCOPE:\n{knowledge_scope}\n"
        
        rendered_subqueries = []
        for i, sqd in enumerate(subqueries):
            subquery, response, retrieval = sqd["subquery"], sqd.get("response"), sqd["retrieval"]
            rendered = "\n".join(f"<evidence index={i}>\n{r.strip()}\n</evidence>" for i, r in enumerate(retrieval))
            rendered_response = f"<response>\n{response.strip()}\n</response>" if response else ""
            rendered_subqueries.append(f"<subquery>\n<query>{subquery}</query>{rendered_response}{rendered}</subquery>\n")
        subqueries_rendered = "\n\n".join(rendered_subqueries)
        
        query = query.strip()
        
        prompt = _COMPOSE_PROMPT.format(
            query=query,
            rendered_subqueries=subqueries_rendered,
            scope_block=scope_block,
        )
        
        return prompt
    
    @staticmethod
    def _extract_answer(raw_text: str) -> List[str]:
        """Parse <subquery>...</subquery> blocks; gracefully fall back to JSON array if present."""
        if not raw_text:
            return []
        
        # Default: strict block parsing (case-insensitive, dotall)
        blocks = re.findall(r"<answer>\s*(.*?)\s*</answer>", raw_text, flags=re.IGNORECASE | re.DOTALL)
        if len(blocks) != 1:
            raise ValueError(f"Expected exactly one <answer> block, but found {len(blocks)}")
        return blocks[0].strip()
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            query = render_template(self.query_template, data)
            subqueries = []
            if isinstance(self.subqueries_template, str):
                subqueries = render_template(self.subqueries_template, data)
            elif isinstance(self.subqueries_template, list):
                for subquery_template in self.subqueries_template:
                    if isinstance(subquery_template, str):
                        subqueries.append(render_template(subquery_template, data))
                    else:
                        subqueries.append(subquery_template)
            
            compose_prompt = self._render_prompt(query, subqueries, self.knowledge_scope)
            data[f"{self.id}.compose_prompt"] = compose_prompt
            
            response = self.generate_response(compose_prompt)
            data[f"{self.id}.full_response"] = response
            
            answer = self._extract_answer(response)
            data[f"{self.id}.final_answer"] = answer
            
            return data, self.next_component_id
        
        except Exception as e:
            logger.exception(f"[MergeComponent] Failed to split for {self.__class__.__name__} (ID: {self.id}):")
            logger.error(f"[MergeComponent] Error details: {str(e)}", exc_info=True)
            raise RuntimeError(f"MergeComponent execution failed: {e}")
