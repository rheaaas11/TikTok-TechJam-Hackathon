# Devpost Submission Draft

## Project Name

ShopSense Shopping Copilot

## Short Description

ShopSense is an offline conversational shopping agent that asks targeted follow-up questions and ranks catalog products to find a hidden target item as early as possible.

## Problem Statement Fit

The challenge asks teams to build a multi-turn shopping agent for conversational e-commerce search. Our solution addresses this by combining:

- conversation-state tracking, so earlier preferences are remembered;
- intent override handling, so the user can change their mind mid-session;
- clarification strategy, so the agent asks for useful missing attributes;
- deterministic catalog retrieval and reranking, so the returned `parent_asin` list is valid and ordered.

The official evaluator imports `starter.agent.Agent`, calls `reset(...)`, then calls `respond(...)` for up to 10 turns. ShopSense returns a natural message, one structured `ask_attribute`, and up to 10 ranked product IDs.

## What The Solution Does

1. Reads the anonymized user profile provided by the evaluator.
2. Parses each user message into shopping preferences such as category, material, color, size, style, brand, budget, and free-text needs.
3. Maintains active constraints across turns.
4. Detects no-preference answers and intent overrides.
5. Searches the frozen catalog with multiple lexical and structured routes.
6. Reranks candidates using constraint matches, rating signals, price/budget fit, and missing-information handling.
7. Asks the next best clarification question while still returning product recommendations.

## Development Tools Used

- VSCode / local Python development
- GitHub and GitHub Desktop for version control and integration
- Local command line for testing and evaluator runs
- Codex for integration support, release checks, documentation, and demo UI preparation

## APIs Used

No external runtime APIs are required for the final agent.

The submitted system is offline and deterministic. It does not require OpenAI, Google, TikTok, or any paid model API key during official evaluation.

## Libraries And Frameworks Used

Official agent:

- Python standard library
- `sqlite3` full-text search through the Python standard library
- `unittest` for tests

Optional demo UI:

- Python standard library `http.server`
- HTML, CSS, and browser JavaScript

No heavy ML framework is required for final scoring.

## Datasets And Assets Used

- Official frozen 50,000-product `Clothing_Shoes_and_Jewelry` catalog derived from Amazon Reviews 2023.
- Official 200-session public development set.
- Organizer-held 800-session private set is not included or accessed.
- No third-party images, logos, trademarks, or copyrighted media are used in the demo UI.

## Reproducible Results

Commands:

```bash
python3 -m unittest
python3 -m evaluator.local_evaluator
```

Public-set result:

```text
Hit Rate@10: 0.98
MRR: 0.690403
MTTC: 2.96
TechnicalScore: 0.857921
Prompt tokens: 0
Completion tokens: 0
```

## Optional Demo UI

Run:

```bash
python3 demo/server.py
```

Open:

```text
http://127.0.0.1:8000
```

The UI demonstrates an end-to-end shopping session, shows the agent's follow-up message, shows the official response JSON, and displays the current Top 10 recommendations.

## Limitations

- The system is optimized for the provided public evaluator and frozen catalog; private-set performance may differ.
- It uses deterministic lexical and structured retrieval rather than a trained semantic embedding model.
- Product explanations in the UI are based on catalog metadata, not generated natural-language reasoning.
- The full `data/catalog.jsonl` file is required locally but is not committed to GitHub because it is large.

## What We Would Improve With More Time

- Add a learned semantic reranker or lightweight embedding search.
- Add richer explanations for why each product was recommended.
- Tune question selection on a larger validation split.
- Add more robust category normalization and synonym handling.
- Package the demo UI as a hosted app if the track allowed front-end deployment as part of evaluation.

## Team Contributions

- Shayna: profile extraction, conversation-state design, and follow-up question strategy.
- Leon: offline catalog search, retrieval routes, ranking, scoring improvements, and validation.
- Rhea: GitHub/release ownership, official `starter.agent.Agent` integration, evaluator verification, submission documentation, contract checks, and final demo packaging.

## GitHub Repository

https://github.com/rheaaas11/TikTok-TechJam-Hackathon
