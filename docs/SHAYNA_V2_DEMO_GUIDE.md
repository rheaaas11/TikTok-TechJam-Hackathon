# Shayna V2 — Integrated Profile and Dialogue Handoff

The supplied original remains unchanged in `handoffs/shayna/original-submission-20260831.zip`.
This guide now describes the corrected integration. Combine both reviewed feature
branches; the Agent bridge and ranker live on Leon's branch. Rhea retains release ownership.

## What Shayna owns

Shayna owns the conversational intelligence between a customer's words and Leon's product ranking:

1. turn each message into a structured **Product DNA** profile;
2. remember constraints, questions, no-preference replies, and overrides across turns;
3. decide whether to ask one useful allowed question or proceed with the current detail.

The code is deliberately independent of the catalog, private labels, and evaluator. That keeps it easy to test and prevents overlap with the rest of the team.

## What V2 adds over V1

- Candidate-aware questions: the integrated path consumes coverage and expected remaining pool through `candidate_statistics`, retaining unknown metadata. The original complete-count/Gini interface remains supported for existing callers; truncated `top_values` are never treated as a complete distribution.
- More product language: additional categories, budget ranges and approximate budgets, multi-word use cases, brands, and features such as water resistance.
- Targeted overrides: “Actually, make them white sneakers” replaces category but retains unrelated preferences. “Ignore my earlier preferences” clears earlier non-category soft preferences while retaining category context; “start over” clears the whole active intent.
- Confidence-ready constraints: every parsed constraint carries a confidence field, so a later parser can decide whether to filter, boost, or clarify without changing the profile protocol.

## How to run the demo

From the repository root:

```bash
python -B scripts/demo_shayna_v2.py
```

The walkthrough is catalog-free. It demonstrates an initial request, a constrained follow-up, and an override; prints the active Product DNA after each turn; and shows why the first clarification is selected.

## How to test it

Run component tests on this branch. For the combined evaluator command below,
first combine **both reviewed branches** and restore the catalogue; this branch
alone still contains the original starter Agent, not the combined implementation.

```powershell
python -B -m unittest discover -s tests -v
python -B -m experiments.benchmark_runtime --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output results_combined_summary.json --results-output results_combined_sessions.json --conversation-mode auto --expected-brain starter.shayna_conversation.ShaynaConversationBrain
```

The unit suite validates extraction, no-preference handling, targeted and broad overrides, and candidate-aware question selection. Leon's branch now supplies the real combined bridge for Rhea's review; its benchmark audits raw responses as well as running the unchanged evaluator. Do not commit `data/catalog.jsonl` or `data/catalog.jsonl.gz`.

Shayna's branch alone leaves the starter unchanged. The combined branches select
the real `ShaynaConversationBrain` and `ShaynaProfileAdapter`. Use the commands in
Leon's `docs/RHEA_MORNING_HANDOFF.md` to require that actual implementation and
retain its measured results. Historical reference scores are not combined scores.

## How the three parts connect

| Owner | Input | Output / responsibility |
| --- | --- | --- |
| Shayna | customer message + prior `ShopperProfile` | updated profile, one optional allowed question, and an explanation-ready question value |
| Leon | active Product DNA + catalog | ranked recommendation dictionaries and coverage-aware candidate statistics |
| Rhea | evaluator call and the two module outputs | per-session storage, official `Agent.respond()` response, local evaluation, README/demo story |

### Rhea's integration order

The implemented bridge follows this order (locking, retries and validation are
handled in the actual Agent, not this simplified outline):

```python
profile = update_profile(session_profiles[session_id], user_message, turn)
ranked, statistics = leon_ranker.rank_with_stats(profile, top_k=10)
decision = decide_next_turn(profile, candidate_statistics=statistics)

response = {
    "message": decision.message,
    "ask_attribute": decision.ask_attribute,
    "recommendations": ranked,  # Already [{"parent_asin": "..."}].
}
session_profiles[session_id] = decision.updated_profile  # After composition succeeds.
return response
```

The final response must contain only contract-approved fields. Any debug information—Product DNA, question values, candidate counts, or profile data—belongs in terminal/demo output, not in `Agent.respond()`.

### Leon's minimal interface

Leon does not need to import Shayna internals. He only needs to read `profile.active_constraints` or `profile.query_terms` and provide:

```python
def rank(profile, top_k: int = 10) -> list[dict[str, str]]: ...
def attribute_stats(profile, candidate_limit: int = 100) -> dict: ...
def rank_with_stats(profile, top_k: int = 10, candidate_limit: int = 100) -> tuple[list[dict[str, str]], dict]: ...
```

Statistics use `{pool_size, attributes: {attribute: metrics}}`, including coverage,
expected remaining pool, question value and display-only top values. The policy
consumes this directly; ranking and statistics share one search. Everything is
based only on the participant catalogue and active conversation, never labels.

## What to say during the demo

“ShopSense does not treat every message as a new keyword search. It builds a Product DNA, retains constraints such as budget and exclusions, handles changed intent without forgetting unrelated needs, and asks a question only when it is likely to reduce the current candidate set. Leon then ranks from that state, while Rhea keeps the interaction inside the official evaluator contract.”

## What's next

1. **Leon:** maintain the implemented ranking and profile-adapter boundary; no dense-model requirement is introduced.
2. **Rhea:** review the implemented bridge, combine both branches, and verify the actual frozen commit before merging and releasing.
3. **Whole team:** evaluate after each integration milestone. Compare Buying, Browsing, Intent Override, and Boundary metrics instead of chasing one aggregate number.
4. **Shayna V3 option:** replace or supplement the deterministic parser with a schema-constrained model parser, keeping the rules as an offline fallback. Add reference resolution for “make it more formal” and calibration for uncertain parses.
5. **Before submission:** run the evaluator, confirm protected tracked data is unchanged (the archived original separately preserves the supplied catalogues), and rehearse the actual frozen implementation.
