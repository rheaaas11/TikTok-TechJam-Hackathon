# Rhea Submission Checklist

Use this checklist before sending the repo to TikTok TechJam or teammates.

## Keep

- `starter/agent.py`
- `starter/` support modules
- `src/profile.py`
- `src/dialogue.py`
- `evaluator/local_evaluator.py`
- `data/public_set.jsonl`
- `docs/agent_api_contract.json`
- `docs/competition_specification.md`
- `docs/evaluation_config.json`
- `docs/submission_rules.md`
- `docs/FINAL_RESULTS.md`
- `tests/`
- `demo/` optional local UI

## Do Not Commit

- `data/catalog.jsonl`
- `data/catalog.jsonl.gz`
- `results.json`
- `__pycache__/`
- `.env`
- API keys or tokens
- handoff `.zip` files

These are covered by `.gitignore`.

## Final Commands

From the repo root:

```bash
python3 -m unittest
python3 -m evaluator.local_evaluator
```

Optional UI demo:

```bash
python3 demo/server.py
```

Then open:

```text
http://127.0.0.1:8000
```

## What To Submit

Submit the GitHub repository URL after the integrated branch is merged to `main`:

```text
https://github.com/rheaaas11/TikTok-TechJam-Hackathon
```

If the form asks for notes, use:

```text
Offline deterministic shopping copilot. Official entry point is starter.agent.Agent.
No LLM API keys required. Public evaluator score: HR@10 0.98, MRR 0.690403,
MTTC 2.96, TechnicalScore 0.857921 on 200 public sessions.
```

## GitHub Desktop Steps

1. Open GitHub Desktop.
2. Choose `File > Add Local Repository`.
3. Select `/Users/rhea/Documents/Codex/ShopSense-integration-check`.
4. Confirm the current branch is `codex/integration-check`.
5. Click `Publish branch`.
6. On GitHub, open a pull request from `codex/integration-check` into `main`.
7. If tests above passed and time is short, merge the pull request.
8. Send teammates the main repo link after merge.
