from abc import abstractmethod
from typing import Dict, Type, Any, Optional, Tuple, List

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ADJUST_QUERY_PROMPT = """{prompt}

{few_shot_examples}

QUESTION:
<question>{question}</question>

OUTPUT:
"""


class AbstractQueryAdjuster(AbstractComponent, variant_name="query_adjuster"):
    variants: Dict[str, Type['AbstractQueryAdjuster']] = {}
    
    default_parameters: Dict[str, Any] = {
        "question": "f'{start.current_user_input}'",
        "prompt_instructions": """Clean up the following question provided inside the <question> tags, by correcting misspellings, typos, and formatting issues.
Do not change the language, meaning, terminology, or phrasing style.
Keep the exact content and wording wherever possible, only fixing clear errors.
Do not include any additional characters like \".
Output only the cleaned query.""",
        "examples": [],
    }
    
    def __init__(self, component_id, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractQueryAdjuster.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    @abstractmethod
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "examples": {
                "type": "list",
                "description": "Few-shot examples as [{'question': str, 'output': str}]",
                "default": [],
            },
            "prompt_instructions": {
                "type": "string",
                "description": "Instructions -> default: clean up query",
            },
            "question": {
                "type": "string",
                "description": "Question template to render (with start.current_user_input)",
                "default": "f'{start.current_user_input}'",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "query_adjuster.prompt": {
                "type": "string",
                "description": "The FULL prompt send to model",
            },
            "query_adjuster.query_adjust": {
                "type": "string",
                "description": "Cleaned up question (output)",
            },
        }
    
    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        pass
    
    @staticmethod
    def _render_prompt(
            prompt: str, question: str, examples: List[Dict[str, str]],
    ) -> str:
        rendered_examples = []
        for i, example in enumerate(examples):
            q = example.get("question", "").strip()
            out = example.get("output", [])
            rendered_examples.append(
                f"""Example {i + 1}:
    Question: {q}
    Output: {out}""",
            )
        
        prompt = _ADJUST_QUERY_PROMPT.format(
            prompt=prompt,
            question=question,
            few_shot_examples=(
                    "\n---\nFEW-SHOT EXAMPLES (format is mandatory):\n" + "\n".join(rendered_examples) + "\n---\n"
            ) if rendered_examples else "",
        )
        return prompt
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        question_template = self.parameters.get("question") or self.default_parameters.get("question")
        examples = self.parameters.get("examples") or self.default_parameters.get("examples")
        prompt_instructions_template = self.parameters.get("prompt_instructions") or self.default_parameters.get("prompt_instructions")
        
        question = render_template(question_template, data)
        prompt_instructions = render_template(prompt_instructions_template, data)
        
        prompt = self._render_prompt(prompt_instructions, question, examples)
        data[f"{self.id}.prompt"] = prompt
        
        full_response = self.generate_response(prompt)
        data[f"{self.id}.query_adjust"] = full_response
        
        return data, self.next_component_id
