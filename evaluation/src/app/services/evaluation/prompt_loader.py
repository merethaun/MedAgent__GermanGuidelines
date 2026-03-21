from functools import lru_cache
from pathlib import Path


class PromptLoader:
    @staticmethod
    @lru_cache(maxsize=1)
    def load_gptscore_prompt() -> str:
        return PromptLoader._read_file("gptscore_prompt.md")

    @staticmethod
    @lru_cache(maxsize=1)
    def load_gptscore_examples() -> str:
        return PromptLoader._read_file("gptscore_examples.md")

    @staticmethod
    def _read_file(filename: str) -> str:
        base_dir = Path(__file__).resolve().parents[2] / "prompts"
        return (base_dir / filename).read_text(encoding="utf-8")
