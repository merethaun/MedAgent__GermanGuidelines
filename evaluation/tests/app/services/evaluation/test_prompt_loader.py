from app.services.evaluation.prompt_loader import PromptLoader


def test_prompt_loader_reads_markdown_files():
    prompt = PromptLoader.load_gptscore_prompt()
    examples = PromptLoader.load_gptscore_examples()

    assert "similarity" in prompt
    assert "Example 1" in examples
