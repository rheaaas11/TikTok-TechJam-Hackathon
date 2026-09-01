# Shayna V1 — Product DNA and Conversation State

> This is the original handoff. The implementation has progressed to V2; use [the V2 demo and handoff guide](SHAYNA_V2_DEMO_GUIDE.md) for current operation, integration, and next steps.

## What is built

Shayna's V1 is now isolated from the official evaluator and catalog logic:

- `src/profile.py` creates and updates an immutable per-session `ShopperProfile`.
- `src/dialogue.py` turns the profile into one allowed clarification question, or decides the agent has enough detail to stop asking.
- `tests/test_profile.py` and `tests/test_dialogue.py` cover the core multi-turn behaviours.

Rhea can later call this handoff from `starter/agent.py` without changing the evaluator:

```python
from src.dialogue import process_message

decision = process_message(session_profile, user_message, turn)
# decision.updated_profile -> Leon's ranker
# decision.message / decision.ask_attribute -> official response
```

## How it works

1. `reset(...)` will create a clean profile through `new_profile(session_id, user_profile)`.
2. `process_message(...)` extracts a deterministic Product DNA from the latest customer message.
3. The profile records active and superseded constraints, so it preserves a useful audit trail while giving retrieval only the active values.
4. The question policy asks at most one allowed attribute. It avoids an already known value and avoids a question that received a no-preference answer.

### Product DNA fields

- `category`: boots, sneakers, shoes, dresses, jackets, and other common clothing types.
- `hard constraints`: category, size, price cap, explicit requirements, and exclusions.
- `soft preferences`: style and other non-mandatory signals, including common features such as water resistance.
- `negative preferences`: for example, `no heels` becomes an active hard exclusion.
- `intent mode`: buying, browsing, or unclear.
- conversation metadata: turn, asked attributes, no-preference attributes, source messages, and a change log.

### Override handling

An override marker such as “actually” or “ignore my earlier preference” deactivates previous soft preferences and conflicts on one-value fields such as color, material, size, budget, and category. The old value stays in `constraints` with `active=False`, so ranking uses the new request while a demo can show the decision change.

## Deliberate V1 boundaries

This branch does **not** edit `starter/agent.py`, `evaluator/local_evaluator.py`, public labels, or catalog files. It also does not rank products; Leon owns that layer. This avoids three people editing the same critical entry point.

V1 uses rules rather than an LLM. It is fast, deterministic, offline, and easy to test, but its vocabulary is intentionally narrow.

## V2 improvements to add after integration

1. **Catalog-aware question value.** Leon should expose candidate counts or attribute entropy; Shayna should then ask the question expected to reduce the candidate pool most, rather than use the static priority order.
2. **Richer constraint parser.** Expand category, brand, fit, gender/audience, multi-word use case, and comparative-budget parsing. A small local parser or an optional LLM parser can sit behind `extract_constraints(...)`, with the V1 rules as offline fallback.
3. **Targeted overrides.** Replace the broad “deactivate all soft preferences” rule with reference resolution: identify exactly which earlier preference “instead” or “ignore that” refers to.
4. **Confidence and conflict policy.** Use confidence to decide whether a parsed detail is a hard filter, soft boost, or a clarification target. Detect contradictory messages even when they lack explicit override words.
5. **Safe profile use.** Use the anonymized profile only as a low-weight tie-breaker after explicit current-session constraints, and record its contribution for the demo.
6. **Scenario-led tuning.** Run the evaluator and inspect Buying, Browsing, Intent Override, and Boundary metrics separately. Keep only changes that improve a named scenario without unacceptable regression.

## Integration checklist for Rhea

- Store `ShopperProfile` per `session_id` in `Agent.reset(...)`.
- In `Agent.respond(...)`, call `process_message(...)`, save `decision.updated_profile`, and give that profile to Leon's `rank(profile, top_k)` function.
- Return only `message`, `ask_attribute`, ordered recommendation objects, and optional valid `usage` fields.
- Run `python3 -m unittest` and `python3 -m evaluator.local_evaluator` after integration.
