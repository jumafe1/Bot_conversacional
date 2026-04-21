# Cost Estimation

## Assumptions

| Parameter | Value |
|---|---|
| Model | gpt-5.2 |
| Average system prompt tokens | ~800 |
| Average user message tokens | ~50 |
| Average conversation history tokens | ~500 (grows per turn) |
| Average tool result tokens | ~300 per tool call |
| Average tool calls per query | 1–2 |
| Average output tokens | ~400 |

## Per-Query Estimate

| Component | Tokens (input) | Tokens (output) |
|---|---|---|
| System prompt | 800 | — |
| Conversation history | 500 | — |
| User message | 50 | — |
| Tool results (×2) | 600 | — |
| Final LLM response | — | 400 |
| **Total** | **1,950** | **400** |

## Monthly Cost Projection

> Prices are illustrative. Update with actual gpt-5.2 pricing when available.

| Sessions/day | Turns/session | Monthly input tokens | Monthly output tokens | Est. cost |
|---|---|---|---|---|
| 10 | 5 | ~2.9M | ~600K | TBD |
| 50 | 5 | ~14.6M | ~3M | TBD |
| 200 | 5 | ~58.5M | ~12M | TBD |

## Optimization Levers

- Cache system prompt with provider prompt caching (reduces per-turn cost ~40%).
- Truncate conversation history beyond N turns to cap context growth.
- Use a cheaper model for simple factual queries; route complex ones to the full model.
