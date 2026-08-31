# Leon's integration handoff

Status: feature-branch integration candidate based on team `main` at
`261eb05a47342cf77ecdc7e918c6b67c8b7a6a3a`, not a submitted or merged solution.
The actual Shayna modules are now connected through `ShaynaConversationBrain` and
`ShaynaProfileAdapter`; auto mode selects them when both modules are present.
Shayna's branch holds the profile/question fixes, Leon's holds the adapter, search
and Agent bridge. Rhea retains review, merge, integration and release authority.
See `../docs/RHEA_MORNING_HANDOFF.md` and `scoreboard.md` for measured status.
Historical reference-brain evidence stays labelled separately under `evidence/`.

## Search boundary

```python
from starter.ranker import Ranker
from starter.shayna_adapter import ShaynaProfileAdapter

ranker = Ranker("data/catalog.jsonl", profile_adapter=ShaynaProfileAdapter())
recommendations, statistics = ranker.rank_with_stats(active_profile)
```

Omit `profile_adapter` for the documented default mapping/object/dataclass schema.
`rank()` and `attribute_stats()` remain available separately. The combined method
performs one retrieval/reranking pass and maintains no per-session mutable cache.
All evidence and statistics stay outside the official response payload.

For a different schema, implement only `team_adapter.adapt(profile)` returning
`starter.profile_adapter.NormalizedShopperProfile`; do not rewrite catalog/search.
Known aliases can instead be added through `DefaultProfileAdapter(field_aliases=...,
constraint_aliases=...)`. New aliases must have the same semantics, not merely
similar field names.

## Frozen Shayna-to-Leon boundary

The actual immutable `src.profile.ShopperProfile` is a complete snapshot:

- Whether state is a complete snapshot or a partial update. The default adapter
  treats nested active/current state as complete; missing fields do not inherit
  old root intent. Partial-update schemas need their own adapter.
- Whether `active_constraints` is authoritative. It is in the default adapter,
  including an empty list; typed legacy collections are not merged back into it.
- Constraint attribute, value, hard/soft strength, include/exclude polarity,
  confidence, source turn, and active/replaced status.
- Active category, use case, and uncommon query phrases. Rebuild query terms on
  overrides and no-preference updates; Leon does not infer which old words to erase.
- Asked, no-preference, and exhausted attributes. They are excluded from question
  statistics. Aggregate preferences remain weak priors, never hard constraints.
- Budget units and operators. Prefer explicit USD bounds or min/max; unsupported
  currencies and contradictory syntax remain unknown, with no inferred conversion.

`ShaynaProfileAdapter` derives the category and query phrases only from current
active constraints, without importing `src` or re-parsing message history. Tests
cover the real dataclass, dictionary snapshots, category aliases, inactive intent,
no-preference transitions and the generic adapter fallback. See
`tests/test_shayna_adapter.py` and `tests/test_shayna_integration.py` as well as
the existing generic adapter/profile regressions.

## Implemented Agent sequence for Rhea's review

1. Update the active profile through Shayna's module.
2. Call `rank_with_stats()` once if the question policy needs candidate statistics.
3. Call `decide_next_turn(profile, candidate_statistics=statistics)`. The additive
   interface consumes coverage/expected-remaining utility directly; it never
   mistakes the truncated `top_values` preview for a complete distribution.
4. Validate/compose only the official response fields. Do not serialize the
   profile, statistics, route diagnostics, or demo evidence into the response.
5. Commit the immutable profile and cache a defensive response copy only after
   success. Repeated identical calls reuse the cached result; reset clears it.

The bridge is implemented, not pseudocode. Failed ranking, policy or composition
leaves the Shayna state unchanged. Partial or broken teammate imports fail loudly;
they do not silently evaluate the reference system. A future model client must
report actual usage; this standard-library implementation makes no model calls.

Regression coverage includes real multi-turn flows, repeat/reset/interleaved
sessions, failed-response retries and valid unique Top 10. Full runs additionally
record the actual selected brain/adapter and hash both `starter` and `src`; require
`--expected-brain starter.shayna_conversation.ShaynaConversationBrain` when
evaluating the combined system. Check the scoreboard for results, not test counts alone.

## Question statistics limitations

Priority P2, optimization hypothesis rather than measured policy improvement:

The answer distribution is approximated by catalog value frequency. Unknown
metadata survives each answer; material ambiguity survives relevant answers too.
Coverage-adjusted utility is a heuristic, not the probability of finding the target.
Use it only after excluding answered/no-preference/exhausted attributes. Feature
and use-case statistics are not yet exposed because reliable normalized value
distributions are not implemented for them. Compare the real question policy
against the reference on the same fixed split before promoting it.

## Remaining ranking policy limitation

Priority P2, Leon/assistant; confirmed synthetic behavior, unmeasured public impact:

An off-category product already retrieved through shared lexical terms can outrank
an on-category unknown-price product when it confirms a hard budget and category
is supplied only as a profile preference, not a hard constraint. Numeric price
retrieval is category-scoped, but that does not remove candidates from other routes.
Do not silently turn every category hint into a hard filter. Agree category
confidence/strength with Shayna, then test category-first reranking as a controlled
ablation before changing the current hard-match priority.

Validation fixture: a cheap boot and an unknown-price dress both titled with the
same generic phrase, active category dresses, and hard budget under 100. Compare
results with category as a hint versus an explicit hard category constraint; then
check Buying/Browsing HR and overall score for regression.

The test-only prototype in `tests/test_category_policy.py` now includes an
interleaving counterexample: swapping non-adjacent candidates with the same hard
evidence can still move weaker evidence across an intervening stronger candidate.
That broad permutation was rejected. The corrected prototype only reorders
contiguous equal-evidence runs; it is **not enabled or implemented in production**,
and no public-score benefit is claimed. This preserves the existing validated
ranking policy until a deliberate, measured ablation is approved for integration.

## Independent-source verification

`experiments/verify_snapshot.py` copies an explicit allow-list into a fresh,
retained directory, hashes it, then runs the test suite and optionally the official
evaluator with Python `-I` and a socket/DNS guard. It checks runtime import origins
and preserves full session results. It never overwrites an existing directory,
deletes snapshots, copies credentials, or relies on `.git`/cached results.

This is source-package validation, not a fresh-clone test or proof that Rhea's
eventual merged release commit has been evaluated. The current combined evidence
records both source commits and their conflict-free combined tree in addition to
the exact executed file hashes.

Historical reference-only run: `shopsense-validation/candidate-20260831-v4`, started
31 August 2026 at 22:07 SGT. All **98 tests** passed inside the copied package;
all **200 evaluator sessions** completed with zero Agent/reset exceptions,
**454/454 valid ten-product responses**, and zero socket/DNS attempts. The
**196/200 hits** and TechnicalScore **0.888571** exactly reproduce V3 session
outcomes. Response p95 was **802.844 ms**; whole-process peak memory **602.793 MiB**.
Initialization was **31.356 seconds**, so that historical run missed the team's
sub-30-second startup goal. The material-scan fast path is semantics-preserving on all 50,000
catalog products; no end-to-end startup speedup or score gain is claimed.

The validated starter-source fingerprint is
`f43694ddd2f409e6708c34d0c113dbbf1478de57c8d91cbf5808f58a8724291c`.
See `scoreboard.md` for exact artifact paths, input hashes, scenario results, and
isolation limits. Actual teammate wiring is now implemented; the current combined
measurements are a separate scoreboard entry. Rhea's final merged release still
needs her review and verification.

## Rhea's submission evidence checklist

Priority P1, submission reproducibility:

- Follow the official final FAQ at upstream commit `9c9e7c9`, not stale team docs.
- Freeze a runnable, reviewed Git commit before the submission deadline. Feature
  branch source commits are not Rhea's final submitted/merged commit.
- After final-session release, do not change the agent, prompts, indexes, models,
  or other solution components. Run the unmodified official evaluator.
- Retain complete `results.json` including sessions, the submitted SHA, and
  hardware/Python/dependencies/runtime/model cost details. Summary metrics alone
  are insufficient. The benchmark audit supports this retention using fresh
  summary and session-output paths.
- Offline execution and team latency/memory targets are engineering choices, not
  organizer-mandated environment limits. Disclose actual dependencies honestly.

The original development audit changed no team source or remote state. Leon has
now authorized publishing this candidate on `feature/leon-ranking` and opening a
PR into `main`. The PR preserves protected evaluator, data, contract, scoring, and
existing evaluator-test files. It includes the actual teammate integration for
Rhea's explicit review, with the reference brain retained as a labelled comparison.
Do not push directly to `main`, merge this PR, or enable automatic merging.
