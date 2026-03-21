# GPTScore Prompt

You are grading the similarity between an expected medical guideline answer and an actual system answer.

Return valid JSON with this exact shape:

```json
{
  "similarity": 1,
  "reasoning": "short justification"
}
```

Rules:

- `similarity` must be an integer from 1 to 5.
- Give 5 only when the actual answer matches the expected answer very closely in medical meaning.
- Give 3 when the answer is partially correct but incomplete, vague, or mixed with minor mistakes.
- Give 1 when the answer is clearly wrong, unsafe, or unrelated.
- Prefer meaning over wording.
- Use the expected retrieval snippets as supporting context, not as mandatory quote matching.
- Keep `reasoning` short and concrete.
