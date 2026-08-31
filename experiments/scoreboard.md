# ShopSense Retrieval and Ranking Scoreboard

Only evaluator-backed changes belong here. Runtime code never imports this folder,
reads `data/public_set.jsonl`, or accesses `ground_truth`.

`experiments/public_split.json` fixes a 160-session development / 40-session
validation split, stratified by scenario, difficulty, and category. Rebuild it with
`python experiments/make_split.py`; the manifest contains sample IDs only.

The historical candidates use base commit
`34078351e1c3615e5505a2e829600b56a542e462`. Upstream was rechecked on 31 August:
`origin/main` is `9c9e7c9ff6705142d6ab386dc1c432fc529df893`, with documentation
clarifications and no changes to the evaluator, public labels, API contract, or
scoring configuration. A working-tree diff against those protected upstream files
was empty during this audit. The latest candidate contains staged and unstaged
local work, not a submitted solution commit; the pre-existing index was preserved.

| Variant | Revision | HR@10 | MRR | MTTC | Efficiency | TechnicalScore | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| Official BM25 baseline | `3407835` | 0.125 | 0.068034 | 9.81 | 0.119 | 0.106710 | Reference |
| Earlier stateful lexical implementation | staged pre-audit | 0.9100 | 0.641752 | 3.24 | 0.7760 | 0.802726 | Superseded |
| Ultra audit: expanded exact/structured routes | working tree v1 | 0.9800 | 0.760851 | 2.335 | 0.8665 | 0.891555 | Quality ablation; p95 too slow |
| Ultra audit: consolidated exact routes | working tree v2 | 0.9800 | 0.747905 | 2.290 | 0.8710 | 0.888571 | Previous promoted baseline |
| Missing-safe constraints, budget routing, adapter and evidence corrections | working tree v3, source fingerprint below | 0.9800 | 0.747905 | 2.290 | 0.8710 | 0.888571 | Correctness fixes retained; startup target still open |
| Material-scan fast path and isolated source validation | working tree v4, source fingerprint below | 0.9800 | 0.747905 | 2.290 | 0.8710 | 0.888571 | Identical session outcomes; 98 tests; startup target still open |

The v2 score is 0.002984 below the slower v1 candidate, inside the plan's 0.005
correctness/performance promotion allowance. It preserves HR@10, improves MTTC, and
returns representative p95 latency below one second.

## Shared v2/v3/v4 public scenario metrics

| Scenario | Sessions | HR@10 | MRR | MTTC |
|---|---:|---:|---:|---:|
| Buying | 80 | 0.9625 | 0.637684 | 1.7875 |
| Browsing | 80 | 1.0000 | 0.816939 | 2.1000 |
| Intent Override | 30 | 0.966667 | 0.823704 | 3.866667 |
| Boundary | 10 | 1.0000 | 0.850000 | 3.1000 |

Fixed-manifest readout for v2: development (160) TechnicalScore **0.890184**,
HR@10 **0.98125**; validation (40) TechnicalScore **0.882122**, HR@10 **0.975**.
V3 and V4 reproduce every official per-session record exactly, so these readouts and all
four scenario metrics are unchanged, not newly improved.
The manifest was created after earlier public-set iteration, so this first readout is a
reproducible stability slice, not a claim of a previously untouched holdout. Future
weight changes should protect it before inspecting per-session outcomes.

## Correctness and architecture ablation

| Change | Result | Kept? |
|---|---|---|
| Canonical adapter for dict/dataclass/object/nested profiles | Alternate shapes produce the same ranked target; stale root state loses to nested active state | Yes |
| Three-valued constraint relations | Missing/unstructured absence is unknown; verified structured mismatch remains a penalty/filter | Yes |
| Correct negative fallback and evidence polarity | Explicit exclusions are not silently restored; demo conflict means the excluded value is actually present | Yes |
| Exact clause + per-constraint structured routes | Public TechnicalScore increased from 0.802726 to 0.891555 before optimization | Yes |
| Separate hard and soft exact FTS calls | Representative p95 was 1172.739 ms and cold init was 30.056 s | No |
| One consolidated exact-clause call | TechnicalScore 0.888571; representative p95 801.239 ms; cold init 23.027 s | Yes |
| Unicode NFKC/casefold plus Python lexical fallback | `café`, smart apostrophe, and non-Latin token tests pass with FTS-independent search | Yes |

## 31 August isolated source candidate (v4)

The copied candidate passed **98 tests** and the full unmodified official evaluator
on all **200 public sessions**, using the local reference conversation module, not
Shayna's or Rhea's actual custom implementation. Every session record matches V3
exactly: **196/200 hits**, TechnicalScore **0.888571**. No score gain is claimed.

Measured run started 31 August 2026 at 22:07 SGT on the V3 host described below:

| Observation | V4 result |
|---|---:|
| Tests / failures / errors / skipped | 98 / 0 / 0 / 0 |
| Official sessions retained / responses audited | 200 / 454 |
| Agent / reset exceptions | 0 / 0 |
| Invalid raw responses, invalid or duplicate IDs | 0 |
| Responses with exactly ten recommendations | 454 / 454 |
| Initialization | 31.355664 s |
| Evaluator wall time | 170.561473 s |
| Response p50 / p95 / maximum | 365.7995 / 802.8437 / 983.6616 ms |
| Whole-process peak working set | 602.793 MiB |
| Socket/DNS attempts during tests / evaluation | 0 / 0 |

The material-scan fast path skips a regular-expression search only when its
required first literal word is absent from the identical normalized field text.
An old-versus-new extraction comparison over all **50,000 products** found zero
material or uncertainty differences. Profiling showed **200,849 fewer regex
search calls**, but did not establish an end-to-end startup speedup. Initialization
remains **31.36 seconds**, above the team's 30-second goal; p95 and memory goals pass.
Whole-process memory includes tests and evaluator/catalog setup, not only the agent.

The separate category/budget proposal is **test-only**, not production behavior.
A broad non-adjacent reordering was rejected after an interleaving counterexample;
the narrowed contiguous-run prototype has no demonstrated public-score benefit.

Validation used `experiments/verify_snapshot.py` with a fresh retained source copy:

```powershell
python -B -m experiments.verify_snapshot `
  --destination ..\shopsense-validation\candidate-20260831-v4 `
  --evaluate
```

The copy's **39 manifest files** were hash-checked before and after execution.
Python `-I` was enabled, starter/evaluator import origins were inside the copied
tree, and a Python socket/DNS guard observed zero network attempts. This is not an
OS-wide network sandbox or a clean system Python installation. All runtime, test,
and experiment Python source in the worktree matched the validated copy after the
run; this reporting documentation was updated afterward.

Retained directory (about **58.125 MiB** including catalog and results):
`C:\Users\user\Documents\shopsense-validation\candidate-20260831-v4`.

- `snapshot_manifest.json`: copied paths and individual hashes.
- `snapshot_validation.json`: test counts, isolation, import origins, and integrity checks.
- `results_snapshot_summary.json`: timings, raw-response audit, memory, source/input hashes.
- `results_snapshot_sessions.json`: full official result, including all 200 sessions.
- Starter source SHA256 fingerprint:
  `f43694ddd2f409e6708c34d0c113dbbf1478de57c8d91cbf5808f58a8724291c`.
- Catalog SHA256:
  `da979b05a68af864cb0dcf9ee6a81c010c7e66a57978ad286c7a2e005fc69a67`.
- Public dataset SHA256:
  `571359a8a69014c43fc30d39c996c4a28e875dccc249dffc707358757beb16c0`.

The snapshot intentionally contains no `.git`, so its Git provenance is null:
hashes identify this uncommitted development candidate. Independent source-package
validation is complete; a fresh clone of the final reviewed team commit and actual
teammate integration remain separate gates. Preserve these artifacts for comparison.

## Historical 31 August correctness candidate (v3)

Full run used the unmodified official `evaluate()` with the local reference brain
and independent timing/raw-response checks. It is not an integrated Shayna/Rhea
run. All **81 unit tests pass**, including the 50,000-ID integrity test and added
regressions for:

- Complete active snapshots and authoritative empty active-constraint collections.
- Canonical ordering for mapped set/frozenset constraints, additionally checked
  in separate Python processes with hash seeds 1, 17, and 99.
- Single-record mapping constraints, nonfinite confidence, and preserved numeric
  operators, min/max ranges, redundant compatible expressions, and ambiguous syntax.
- A numeric budget route retrieving a qualifying product beyond the lexical top-200
  cutoff, while avoiding off-category candidates from that new route.
- Soft exclusions penalizing without eliminating, and local material negation /
  ambiguity remaining distinct from verified positive metadata.
- Unknown/ambiguous survivors in question statistics and one-pass `rank_with_stats()`.
- Verbatim, locally relevant evidence snippets, including late and Unicode matches.
- Complete result retention, non-mutating raw-output auditing, and no-overwrite paths.

Final measured run (31 August 2026, 20:22 SGT start):

| Observation | V3 result |
|---|---:|
| Official sessions retained | 200 |
| Responses audited | 454 |
| Agent/reset exceptions | 0 / 0 |
| Invalid raw responses / invalid or duplicate IDs | 0 |
| Responses with exactly ten recommendations | 454 / 454 |
| Initialization | 30.012815 s |
| Evaluator wall time | 175.310096 s |
| Response p50 / p95 / maximum | 385.95645 / 820.7497 / 1024.5477 ms |
| Whole-process peak working set | 604.645 MiB |

The process-memory observation includes evaluator/catalog setup and is **not**
comparable to the older agent-only resident-memory observation below. Host:
Intel Core i7-1165G7 (4 cores / 8 logical processors), approximately 15.8 GiB physical
RAM, CPython 3.10.6, Windows build 22631. Timings vary with host load.

Outbound Python socket connection/send and DNS resolution functions were blocked
for the complete run; the guard observed **zero attempts**. This is a runtime
offline check in the existing checkout, not an OS-wide network sandbox or a
completed fresh-clone setup test. A separate clean-snapshot smoke attempt was
blocked before execution by the tool policy; no fresh-clone gate is claimed.

The p95 and memory team targets pass. Initialization is **30.013 seconds**, marginally
over the team's 30-second target; the prior run before the final unordered-container
fix took 32.904 seconds, so a robust sub-30-second startup gate is not claimed.
Further startup profiling is pending. These are team
engineering targets, not official limits. No numerical score improvement is
claimed for these corrections: the public run does not exercise every synthetic
edge case, which is why the regression tests are retained.

Artifacts (ignored local result files; do not discard them):

- `results_correctness_20260831_final_summary.json`: timing, raw-output audit, memory,
  Python/platform, Git HEAD/dirty state, source hashes, and input checksums.
- `results_correctness_20260831_final_sessions.json`: complete official evaluator result,
  including all 200 per-session records, verified equal to the v2 records.
- Starter source SHA256 fingerprint:
  `3cef1c1f2ae531f400f2599e444195649338e9d8457a58099e1b175c5c7182f1`.
  It hashes each sorted `starter/*.py` path plus that file's SHA256. Current source
  was rehashed after evaluation and matched. Git HEAD alone does not identify this
  uncommitted candidate.

Remaining limitations and integration actions are in `TEAM_HANDOFF.md`. In
particular, a hard budget can outrank a category hint if an off-category product
enters another route. Strong category semantics need agreement and a controlled
ablation; the numeric-route correction does not claim to solve that broader policy.

## Historical v2 local performance observations

- Cold load of 50,000 products plus in-memory FTS5 index: **23.027 s**.
- Representative ranking, 30 repeated calls: p50 **744.612 ms**, p95
  **801.239 ms**, maximum **829.851 ms**.
- Full public workload, all **454** `respond()` calls: p50 **381.251 ms**, p95
  **876.280 ms**, maximum **1130.388 ms**.
- Explicit crash-audit count across those 454 calls: **0 agent exceptions**.
- Ranker resident memory immediately after initialization: **332.9 MiB**.
- Full 200-session evaluator: **194.983 s** on this Windows development host, with
  zero caught agent exceptions.
- Runtime dependencies: Python standard library only; fully offline.

Timings are hardware-dependent development observations, not organizer guarantees.
The pure-Python no-FTS fallback is correctness-tested on fixtures but has not been
performance-qualified on the full 50,000-product catalog.

## Reproducibility and interpretation

```powershell
python -m unittest discover -s tests -v
python -m evaluator.local_evaluator `
  --catalog data/catalog.jsonl `
  --dataset data/public_set.jsonl `
  --output results.json
python -m experiments.benchmark_runtime `
  --catalog data/catalog.jsonl `
  --dataset data/public_set.jsonl `
  --output results_fresh_audit_summary.json `
  --results-output results_fresh_audit_sessions.json
```

Use fresh output names; the benchmark refuses to overwrite an existing artifact.
For final submission, the official FAQ at `9c9e7c9` requires the submitted frozen
commit and complete per-session results from the unmodified official evaluator,
with environment/execution details. A dirty working-tree fingerprint is development
evidence, not a substitute for the submitted commit. Network APIs are allowed and
there are no standardized organizer CPU/RAM/startup/per-response limits.

The public score is development evidence, not a private-set guarantee. In particular,
the bundled reference brain asks the broad allowed `other` attribute, and the released
customer policy can disclose any remaining constraint for that request. The ranker,
adapter, missing-data behavior, override tests, and offline fallback are independent of
that policy, but the exact public MTTC is evaluator-sensitive. The latest FAQ confirms
the same deterministic templates and `ask_attribute` policy for final evaluation;
this does not guarantee equal outcomes on different products/sessions.

## Promotion rules

- Prefer a validation TechnicalScore gain of at least 0.005.
- A correctness or performance fix may be retained with less gain when regression is
  no more than 0.005.
- Reject a change if Buying or Browsing HR@10 falls by more than 0.03 without a larger
  justified benefit.
- Always record all four scenarios, startup, p50/p95 latency, and known limitations.
