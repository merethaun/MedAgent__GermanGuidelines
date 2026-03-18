from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from app.models.system import PromptDefinition

_PROMPT_ROOT = Path(__file__).resolve().parent / "prompts"


def _read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_prompt_definitions() -> Dict[str, PromptDefinition]:
    prompt_definitions: Dict[str, PromptDefinition] = {}
    prompt_directories: Dict[str, Path] = {}

    for prompt_file in sorted(_PROMPT_ROOT.glob("**/prompt.md")):
        prompt_dir = prompt_file.parent
        prompt_key = prompt_dir.name

        if prompt_key in prompt_definitions:
            raise ValueError(
                f"Duplicate prompt_key '{prompt_key}' found in '{prompt_dir}' and "
                f"'{prompt_directories[prompt_key]}'. Prompt directory names must be unique.",
            )

        system_prompt_file = prompt_dir / "system_prompt.md"
        prompt_definitions[prompt_key] = PromptDefinition(
            system_prompt=_read_markdown(system_prompt_file) if system_prompt_file.exists() else None,
            prompt=_read_markdown(prompt_file),
        )
        prompt_directories[prompt_key] = prompt_dir

    return prompt_definitions


def get_prompt_definition(prompt_key: str) -> PromptDefinition:
    prompt_definitions = _load_prompt_definitions()

    try:
        return prompt_definitions[prompt_key].model_copy(deep=True)
    except KeyError as exc:
        available = ", ".join(sorted(prompt_definitions))
        raise ValueError(f"Unknown prompt_key '{prompt_key}'. Available: {available}") from exc


def list_prompt_templates() -> List[str]:
    return sorted(_load_prompt_definitions())
