# Shayna V2 — Demo, Testing, and Team Handoff Guide

## What Shayna owns

Shayna owns the conversational intelligence between a customer's words and Leon's product ranking:

1. turn each message into a structured **Product DNA** profile;
2. remember constraints, questions, no-preference replies, and overrides across turns;
3. decide whether to ask one useful allowed question or proceed with the current detail.

The code is deliberately independent of the catalog, private labels, and evaluator. That keeps it easy to test and prevents overlap with the rest of the team.

## What V2 adds over V1

- Candidate-aware questions: if Leon supplies the distribution of the current eligible products, Shayna asks the attribute most likely to narrow that set. The score is a bounded Gini-impurity value: `0` means the answer would not separate candidates; a larger value means it would.
- More product language: additional categories, budget ranges and approximate budgets, multi-word use cases, brands, and features such as water resistance.
- Targeted overrides: “Actually, make them white sneakers” replaces category but retains unrelated preferences. A genuinely broad request such as “ignore my earlier preferences” clears earlier soft preferences.
- Confidence-ready constraints: every parsed constraint carries a confidence field, so a later parser can decide whether to filter, boost, or clarify without changing the profile protocol.

## How to run the demo

From the repository root:

```bash
python3 scripts/demo_shayna_v2.py
```

The walkthrough is catalog-free. It demonstrates an initial request, a constrained follow-up, and an override; prints the active Product DNA after each turn; and shows why the first clarification is selected.

## How to test it

Run Shayna's unit tests plus the organizer evaluator:

```bash
python3 -m unittest
python3 -m evaluator.local_evaluator --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output /private/tmp/techjam-results.json
```

The unit suite validates extraction, no-preference handling, targeted and broad overrides, and candidate-aware question selection. The evaluator validates the official response contract once Rhea integrates the modules. Do not commit `data/catalog.jsonl` or `data/catalog.jsonl.gz`.

At this staging point, the evaluator score should remain the official starter baseline because `starter/agent.py` is intentionally not altered. A score change only becomes meaningful once Leon's ranker consumes the profile through Rhea's integration.

## How the three parts connect

| Owner | Input | Output / responsibility |
| --- | --- | --- |
| Shayna | customer message + prior `ShopperProfile` | updated profile, one optional allowed question, and an explanation-ready question value |
| Leon | active Product DNA + catalog | ranked top 10 parent ASINs and candidate attribute counts for useful questions |
| Rhea | evaluator call and the two module outputs | per-session storage, official `Agent.respond()` response, local evaluation, README/demo story |

### Rhea's integration order

Inside the official `starter/agent.py` only, Rhea should use this order:

```python
profile = update_profile(session_profiles[session_id], user_message, turn)
candidate_counts = leon_ranker.attribute_counts(profile)  # public catalog candidates only
decision = decide_next_turn(profile, candidate_counts)
session_profiles[session_id] = decision.updated_profile
ranked = leon_ranker.rank(decision.updated_profile, top_k=10)

return {
    "message": decision.message,
    "ask_attribute": decision.ask_attribute,
    "recommendations": [{"parent_asin": asin} for asin in ranked],
}
```

The final response must contain only contract-approved fields. Any debug information—Product DNA, question values, candidate counts, or profile data—belongs in terminal/demo output, not in `Agent.respond()`.

### Leon's minimal interface

Leon does not need to import Shayna internals. He only needs to read `profile.active_constraints` or `profile.query_terms` and provide:

```python
def rank(profile, top_k: int = 10) -> list[str]: ...
def attribute_counts(profile) -> dict[str, dict[str, int]]: ...
```

`attribute_counts` should use useful, shopper-facing buckets—for example price bands instead of every raw price. It must be based only on the participant catalog and current conversation, never on private labels, hidden targets, or private history.

## What to say during the demo

“ShopSense does not treat every message as a new keyword search. It builds a Product DNA, retains constraints such as budget and exclusions, handles changed intent without forgetting unrelated needs, and asks a question only when it is likely to reduce the current candidate set. Leon then ranks from that state, while Rhea keeps the interaction inside the official evaluator contract.”

## What's next

1. **Leon:** implement hard filters, soft boosts, exclusions, hybrid retrieval, and the candidate-count interface against the official catalog.
2. **Rhea:** wire `new_profile`, `update_profile`, `decide_next_turn`, and Leon's ranker into the canonical `starter/agent.py`; keep state keyed by session and clear it in `reset()`.
3. **Whole team:** evaluate after each integration milestone. Compare Buying, Browsing, Intent Override, and Boundary metrics instead of chasing one aggregate number.
4. **Shayna V3 option:** replace or supplement the deterministic parser with a schema-constrained model parser, keeping the rules as an offline fallback. Add reference resolution for “make it more formal” and calibration for uncertain parses.
5. **Before submission:** run the public evaluator, confirm no catalog/private data is tracked, and rehearse a short live walkthrough that visibly demonstrates clarification, memory, override, and recommendation changes.
