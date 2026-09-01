# Final Release Candidate Results

This branch combines all three team areas:

- Shayna: profile extraction and follow-up question policy in `src/profile.py` and `src/dialogue.py`.
- Leon: deterministic catalog retrieval, filtering, and ranking in `starter/ranker.py`, `starter/retrieval.py`, and supporting modules.
- Rhea: official integration surface in `starter/agent.py`, evaluator checks, release docs, and submission hygiene.

## Official Entry Point

The official evaluator imports:

```python
from starter.agent import Agent
```

The agent methods are:

```python
Agent.reset(session_id: str, user_profile: dict) -> None
Agent.respond(session_id: str, user_message: str, turn: int, top_k: int) -> dict
```

## Verified Public-Set Result

Command:

```bash
python3 -m evaluator.local_evaluator
```

Measured on the 200 released public sessions with the local `data/catalog.jsonl` file:

```text
sample_count: 200
hit_rate_at_10: 0.98
mrr: 0.690403
mttc: 2.96
efficiency: 0.804
recommended_technical_score: 0.857921
```

Scenario hit rates:

```text
boundary: 1.0
browsing: 1.0
buying: 0.975
intent_override: 0.933333
```

## Contract

Each `respond` call returns exactly:

```json
{
  "message": "string",
  "ask_attribute": "category | material | color | size | style | brand | budget | feature | use_case | other | null",
  "recommendations": [
    {"parent_asin": "catalog id"}
  ]
}
```

`usage` is allowed by the official schema but this implementation does not call an LLM API, so it intentionally does not report token usage.

## Notes

- The implementation is offline and deterministic.
- No API keys are required.
- The full catalog file is required locally at `data/catalog.jsonl`, but it is intentionally ignored by git because it is large.
- The optional demo UI under `demo/` is not used by the official evaluator.
