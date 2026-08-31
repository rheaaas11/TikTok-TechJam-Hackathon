# Leon's integration handoff

Status: Leon's feature-branch review candidate, prepared from team `main` at
`261eb05a47342cf77ecdc7e918c6b67c8b7a6a3a`. This is not a submitted or merged
solution. Shayna's and Rhea's actual custom implementations were not present in
that inspected team revision. The reference conversation module is a test harness,
not proof of team integration. Rhea decides whether and when to merge this PR.
See `scoreboard.md` for measured results and their exact limitations.

## Search boundary

```python
from starter.ranker import Ranker

ranker = Ranker("data/catalog.jsonl", profile_adapter=team_adapter)  # optional adapter
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

## What Shayna and Leon should agree

Priority P1, integration contract, not a defect claim about unseen teammate code:

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

Validation: send representative real profile objects from Buying, Browsing,
Override, and Boundary sessions, including an empty replacement state. Add
golden adapter expectations and show that stale terms cannot affect retrieval.
Existing synthetic coverage is in `tests/test_profile_regressions.py` and
`tests/test_profile_adapter.py`.

## What Rhea and Leon should connect

Priority P1, integration/test gap:

1. Update the active profile through Shayna's module.
2. Call `rank_with_stats()` once if the question policy needs candidate statistics.
3. Pass the statistics to Shayna's question policy, which chooses the question.
4. Validate/compose only the official response fields. Do not serialize the
   profile, statistics, route diagnostics, or demo evidence into the response.

The bundled reference brain currently selects a question during its state update;
the optional two-stage integration above is not automatically wired into `Agent`.
Rhea owns that wiring and any model-usage accounting. A future model client must
report actual usage; this non-LLM implementation requires no credentials.

Validation: one real multi-turn session end-to-end, then all four scenarios,
repeat/reset/interleaved-session cases, valid unique ordered Top 10, and the full
unmodified public evaluator with raw-response validation. Do not claim integration
is complete just because fixture-based injection tests pass.

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

This is a local source-package validation, not a claim that the uncommitted work
exists on a remote branch or has passed a fresh-clone test of the final team commit.

Latest completed run: `shopsense-validation/candidate-20260831-v4`, started
31 August 2026 at 22:07 SGT. All **98 tests** passed inside the copied package;
all **200 evaluator sessions** completed with zero Agent/reset exceptions,
**454/454 valid ten-product responses**, and zero socket/DNS attempts. The
**196/200 hits** and TechnicalScore **0.888571** exactly reproduce V3 session
outcomes. Response p95 was **802.844 ms**; whole-process peak memory **602.793 MiB**.
Initialization was **31.356 seconds**, so the team's sub-30-second startup goal
remains open. The material-scan fast path is semantics-preserving on all 50,000
catalog products; no end-to-end startup speedup or score gain is claimed.

The validated starter-source fingerprint is
`f43694ddd2f409e6708c34d0c113dbbf1478de57c8d91cbf5808f58a8724291c`.
See `scoreboard.md` for exact artifact paths, input hashes, scenario results, and
isolation limits. Actual teammate wiring and final-commit validation remain pending.

## Rhea's submission evidence checklist

Priority P1, submission reproducibility:

- Follow the official final FAQ at upstream commit `9c9e7c9`, not stale team docs.
- Freeze a runnable, reviewed Git commit before the submission deadline. The
  current local working tree is not yet that submitted commit.
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
existing evaluator-test files. It proposes the replaceable Agent/reference-brain
scaffold for Rhea's explicit review; actual teammate integration remains pending.
Do not push directly to `main`, merge this PR, or enable automatic merging.
