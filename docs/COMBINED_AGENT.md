# Combined ShopSense Agent

This integration uses Shayna's actual `src/profile.py` and `src/dialogue.py`,
Leon's catalogue/retrieval/ranker and a small Agent bridge for Rhea's review.
It does not replace Shayna's parser with the historical reference brain.

## One turn

1. Apply the new message to the session's immutable profile.
2. Adapt active constraints through `ShaynaProfileAdapter`; old messages are not
   reinterpreted by the ranker. Category aliases match whole words.
3. Call `rank_with_stats()` once for ordered product dictionaries and statistics.
4. Call `decide_next_turn(profile, candidate_statistics=statistics)`.
5. Compose only official response fields, then commit state and cache the response.

An identical repeated turn returns an independent copy of the cached response.
Replacing a completed turn with different input is rejected; reset starts a new
session. Failed search, question policy or response composition does not commit
the combined profile. These guarantees apply to the new Shayna bridge, not every
third-party or historical conversation implementation injected through the hook.

## Explicit selection and validation

`Agent(..., conversation_mode="auto")` selects Shayna when both local modules are
present, otherwise retains the Leon-only reference fallback. A partial/broken
Shayna installation raises an error. `conversation_mode="shayna"` requires the
real modules; `"reference"` deliberately selects the historical comparison.

For a fresh combined run, require the actual implementation identity:

```powershell
python -B -m experiments.benchmark_runtime --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output results_combined_summary.json --results-output results_combined_sessions.json --conversation-mode shayna --expected-brain starter.shayna_conversation.ShaynaConversationBrain
```

Use fresh output names. `experiments/verify_snapshot.py` additionally copies and
hashes `starter`, `src`, setup scripts, tests and the unchanged evaluator, executes
with Python `-I`, and blocks Python socket/DNS calls. It is not an OS-wide sandbox
or a claim that an isolated source snapshot is a fresh Git clone.

## Compatibility and limits

- `rank()` already returns `[{"parent_asin": "..."}]`; never wrap those again.
- Statistics are `{pool_size, attributes: {name: metrics}}`; `top_values` is a
  truncated display preview, not a complete answer distribution.
- Candidate utility retains unknown metadata; statistics/evidence stay outside
  the response. Legacy complete value-count callers remain supported.
- No preference clears the corresponding active values; no *additional*
  preference retains known values and marks the attribute exhausted. A later
  explicit value can reactivate it. Category supplements cannot preserve cleared
  color/material modifiers. Physical measurements are not monetary limits.
- Catalog diversity estimates usefulness only if the user can answer. After an
  observed unproductive narrow question, the policy can ask broadly; it repeats
  broad clarification only after new active information and stops on exhaustion.
- Negated free-text evidence such as "no ironing" cannot by token presence alone
  prove a violation of an ironing exclusion. Mixed/ambiguous evidence stays unknown.
- Generic profiles retain `DefaultProfileAdapter` semantics.
- All original ZIP bytes stay archived. Fixes are separately reviewable changes.
- Parsing remains rule-based; grammatical category aliases are not a complete
  product ontology. Question utility is approximate; public results do not
  guarantee private-set performance.

See `RHEA_MORNING_HANDOFF.md` and the scoreboard for measured status.
