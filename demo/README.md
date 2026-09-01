# Optional Local Demo UI

This demo is for teammates and judges who want to click through the combined agent locally.
It is not part of the official evaluator and it does not change the scored `starter/agent.py` contract.

From the repository root:

```bash
python3 demo/server.py
```

Then open:

```text
http://127.0.0.1:8000
```

Requirements:

- `data/catalog.jsonl` must exist locally.
- No API keys are needed.
- The demo uses the same `starter.agent.Agent` entry point as the evaluator.
