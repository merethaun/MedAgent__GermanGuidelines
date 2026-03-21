# GPTScore Examples

## Example 1

Question: When should 3D imaging be used before wisdom tooth extraction?

Expected answer:
Use 3D imaging when standard imaging suggests close proximity to the inferior alveolar nerve or other high-risk anatomy.

Actual answer:
Three-dimensional imaging is recommended when conventional imaging indicates a possible nerve relationship before extraction.

Expected JSON:

```json
{
  "similarity": 5,
  "reasoning": "The answer preserves the key indication and risk context."
}
```

## Example 2

Question: When should 3D imaging be used before wisdom tooth extraction?

Expected answer:
Use 3D imaging when standard imaging suggests close proximity to the inferior alveolar nerve or other high-risk anatomy.

Actual answer:
Three-dimensional imaging should always be performed before every wisdom tooth extraction.

Expected JSON:

```json
{
  "similarity": 1,
  "reasoning": "The answer overstates the indication and changes the recommendation."
}
```
