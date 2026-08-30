# ShopSense Team Onboarding

Repo: https://github.com/rheaaas11/TikTok-TechJam-Hackathon

This is our TikTok TechJam Shopping Copilot project.

## What We Are Building

We are building one headless Python shopping agent.

The agent receives a shopper conversation, remembers what the shopper wants, searches the fixed product catalog, and returns the best ordered Top 10 product IDs.

The evaluator checks whether the hidden target product appears in the Top 10, how high it appears, and how early in the conversation we find it.

## Important Rule

The official evaluator only cares about the required Python agent interface and the returned `parent_asin` IDs.

Do not build UI features first.
Do not add extra fields to the official response.
Do not edit the evaluator, public labels, or scoring config unless Rhea approves it.

## Correct Folder Structure

Use these files and folders:

```text
starter/agent.py                  official agent entry point
evaluator/local_evaluator.py      local evaluator
data/public_set.jsonl             public development sessions
data/README.md                    catalog download instructions
docs/agent_api_contract.json      official response contract
docs/evaluation_config.json       scoring config
docs/baseline_results.json        baseline score reference
docs/competition_specification.md challenge specification
docs/submission_rules.md          submission rules
tests/test_evaluator.py           evaluator unit tests
```

Ignore any old loose starter files at the repo root if they still appear in an older clone. The folder structure above is the one we use.

## Catalog Setup

The large catalog file is not committed to GitHub on purpose.

Each teammate must download it locally.

Download `catalog.jsonl.gz` from:

```text
https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit
```

Then decompress it and place the final file here:

```text
data/catalog.jsonl
```

Expected row count:

```text
50,000
```

Do not commit:

```text
data/catalog.jsonl
data/catalog.jsonl.gz
results.json
.env
API keys
private data
```

## How To Run The Baseline

From the repo root, run:

```bash
python3 -m evaluator.local_evaluator
```

This writes:

```text
results.json
```

Expected unchanged baseline:

```text
hit_rate_at_10: 0.125
mrr: 0.068034
mttc: 9.81
efficiency: 0.119
recommended_technical_score: 0.10671
```

If your result matches this, your setup is working.

## How To Run Evaluator Tests

From the repo root, run:

```bash
python3 -m unittest tests/test_evaluator.py
```

Expected result:

```text
OK
```

## Official Agent Entry Point

The official agent file is:

```text
starter/agent.py
```

It must export:

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        ...
```

## Required Response Format

`respond(...)` must return exactly this kind of dictionary:

```python
{
    "message": "Here are the closest matches I found.",
    "ask_attribute": None,
    "recommendations": [
        {"parent_asin": "B000..."}
    ],
    "usage": {
        "prompt_tokens": 0,
        "completion_tokens": 0
    }
}
```

Allowed `ask_attribute` values:

```text
category
material
color
size
style
brand
budget
feature
use_case
other
None
```

Recommendation rules:

- Return valid `parent_asin` values from the catalog.
- Return unique IDs only.
- Return best to worst.
- Return at most `top_k`, normally 10.
- Optional numeric `score` is allowed, but official scoring uses list order.

Do not put demo-only fields in the official response.

Do not return:

```text
why_matched
why_not
labels
rejected_products
debug
extra UI fields
```

## Team Ownership

### Shayna

Shayna owns product understanding and conversation state.

Main responsibility:

```text
Product DNA
intent detection
conversation memory
hard constraints
soft preferences
negative preferences
contradiction handling
intent override handling
clarifying question strategy
```

Suggested future files:

```text
src/profile.py
src/dialogue.py
tests/test_profile.py
tests/test_dialogue.py
```

Shayna should not edit:

```text
evaluator/local_evaluator.py
data/public_set.jsonl
docs/evaluation_config.json
docs/agent_api_contract.json
```

### Leon

Leon owns search and ranking.

Main responsibility:

```text
catalog loading
keyword retrieval
filtering
reranking
Top 10 recommendation ordering
ranking experiments
```

Suggested future files:

```text
src/catalog.py
src/retrieval.py
src/ranker.py
src/evidence.py
tests/test_retrieval.py
tests/test_ranker.py
experiments/scoreboard.md
```

Leon should not edit:

```text
evaluator/local_evaluator.py
data/public_set.jsonl
docs/evaluation_config.json
docs/agent_api_contract.json
```

### Rhea

Rhea owns integration and release.

Main responsibility:

```text
starter/agent.py integration
official response format
contract checks
evaluator runs
README
submission docs
final packaging
GitHub merge discipline
```

Suggested future files:

```text
starter/agent.py
src/contracts.py
tests/test_contract.py
README.md
docs/architecture.md
scripts/run_eval.sh
```

Rhea decides when code is ready to merge into `main`.

## GitHub Workflow

Use branches.

Suggested branches:

```text
feature/shayna-profile
feature/leon-ranking
feature/rhea-integration
```

Rules:

- Do not push directly to `main` after setup.
- Each person edits their own files.
- Pull from `main` before starting new work.
- Every pull request should say what changed and what tests were run.
- Rhea runs the evaluator before accepting major integration changes.

## What To Do First

1. Everyone clones the repo.
2. Everyone downloads `catalog.jsonl.gz`.
3. Everyone puts `catalog.jsonl` inside `data/`.
4. Everyone runs:

```bash
python3 -m evaluator.local_evaluator
```

5. Everyone confirms they match the baseline score.
6. Then Shayna, Leon, and Rhea start their own branches.

## Priority Order

If time is short, focus in this order:

1. Keep the official agent contract valid.
2. Make retrieval return valid unique Top 10 IDs.
3. Improve multi-turn state and override handling.
4. Improve clarifying questions.
5. Write README, architecture notes, results table, and demo script.
6. Add optional demo explanations outside the official response.

## Current Baseline Status

The unchanged baseline was run successfully with the official catalog and public set.

Result:

```text
sample_count: 200
hit_rate_at_10: 0.125
mrr: 0.068034
mttc: 9.81
efficiency: 0.119
recommended_technical_score: 0.10671
```

This means the starter setup is correct.
