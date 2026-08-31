# Rhea: morning combination and release handoff

## Read this first

The branches contain complete file handoffs, but **the combined agent is not yet
validated**. Simply merging both PRs does not connect Shayna's modules: Leon's
current `starter/agent.py` still uses its replaceable reference conversation brain.
The 0.888571 public score belongs to that reference-integrated candidate, not to
Shayna plus Leon. Rhea retains integration, review, merge, and final release control.

The team's stated submission cutoff is **1 September, 12:00 pm Singapore time**.
Treat that as the operational deadline; verify the organizer's current submission
page before the final upload. Finish implementation and testing before that cutoff.

## Where everything is

| Branch / PR | Contents |
|---|---|
| `feature/shayna-profile`, PR #2 | Original profile/dialogue code, tests, demo, guides; complete 28-entry ZIP in `handoffs/shayna/`; checksum inventory and safe catalogue setup helper |
| `feature/leon-ranking`, PR #1 | All final catalog/retrieval/ranking/adapter/evidence code and tests; experiment tools; latest and historical raw evaluation artifacts; this integration runbook |

No original evaluator, public labels, API contract, scoring configuration, or
existing evaluator tests are changed by either handoff. The original ZIP includes
exact archived copies of those files, but they are not extracted over the checkout.
Do not replace the integrated Agent with the old baseline `agent.py` in the ZIP.

Shayna's 80 MB archive preserves every supplied byte, including both catalogue
files. Her eight new code/test/demo/guide files are also available in normal paths.
The other shared files were already present on team main. Leon's result artifacts
are in `experiments/evidence/`, with checksums and explicit latest/historical labels.

## 1. Combine reviewed branches in Rhea's integration checkout

Use Rhea's own integration branch, not an assistant push to `main`. Fetch both
feature branches and review their diffs against main. If using Git locally:

```powershell
git fetch origin
# On Rhea's chosen integration branch:
git merge --no-ff origin/feature/shayna-profile
git merge --no-ff origin/feature/leon-ranking
python -B scripts/restore_shayna_catalog.py --verify-only
python -B scripts/restore_shayna_catalog.py
python -B -m unittest discover -s tests -v
python -B scripts/demo_shayna_v2.py
```

The setup helper reuses exact existing catalogue files and refuses to overwrite a
different file. It extracts only the two fixed catalogue filenames. The source
ZIP itself should remain an immutable handoff record.

## 2. Resolve these specific integration blockers

### P1: category normalization (Shayna + Leon)

At original Shayna commit `a6c8f78`, `src/profile.py` uses `dresses?`, which does
not match singular `dress`; plural `dresses` produces category value `dress`.
Leon can treat `dress` as a known mismatch against catalogue category `dresses`.
Shayna also stores category only as an active constraint, whereas Leon's canonical
category field is not derived from it by the current default adapter.

Required: recognize both forms, agree a canonical label, and populate the search
category from active inclusion constraints while retaining strength and polarity.
Validation: both “a dress under 50” and “dresses under 50” select the same category
and do not contradict a catalogue product under “clothing women dresses”.

### P1: no-preference transitions (Shayna)

At original commit `a6c8f78`, the no-preference flag is added but old active values
and query terms are not removed. Later explicit preferences do not clear the flag,
so Leon can suppress the new value too.

Validation sequence: “red shoes” -> “no preference for color” -> “make them blue”.
After turn two, red must not influence the active query; after turn three, blue
must be active and color must no longer be marked no-preference. Preserve inactive
history for explanation, not retrieval. Add coverage for other attribute types.

### P1: real API and question-statistics boundary (Rhea + Leon + Shayna)

The supplied guide's `attribute_counts()` does not exist in Leon's implementation.
His `rank()` already returns `[{"parent_asin": "..."}]`, not a list of strings.
Wrapping these again produces nested objects instead of valid string IDs.

Leon provides `rank_with_stats()` / `attribute_stats()`, with a structure like
`{pool_size, attributes: {attribute: metrics}}`. Shayna's dialogue expects
`{attribute: {value: integer_count}}`. Passing the metrics directly can raise a
`TypeError`. `top_values` contains only the five most frequent values; it is not a
complete distribution and must not be presented as one. Missing/ambiguous metadata
must remain possible after answers instead of being dropped from the pool.

Agree a complete-count/coverage contract or deliberately consume Leon's supplied
question utility. Until then, `decide_next_turn(profile, None)` is an available
fixed-priority fallback, **not candidate-aware question selection**.

These are confirmed interface/state issues, not claims that either whole system
is otherwise optimal. They remain pending unless separately fixed and tested.

## 3. Wire the actual call order

Instantiate one `Ranker(catalog_path, profile_adapter=approved_adapter)` for the
catalogue. There is not yet an approved `ShaynaProfileAdapter` class to import;
implement and test the agreed adapter rather than using an invented name.

The intended flow inside Rhea's Agent is:

```python
# reset(session_id, user_profile)
session_profiles[session_id] = new_profile(session_id, user_profile)

# respond(session_id, user_message, turn, top_k)
profile = update_profile(session_profiles[session_id], user_message, turn)
recommendations, stats = ranker.rank_with_stats(profile, top_k=top_k)

# Temporary honest fallback until the statistics contract is resolved:
decision = decide_next_turn(profile, candidate_attribute_counts=None)
session_profiles[session_id] = decision.updated_profile
return {
    "message": decision.message,
    "ask_attribute": decision.ask_attribute,
    "recommendations": recommendations,  # Already correctly shaped dictionaries.
}
```

This is a wiring outline, not an already implemented or score-qualified Agent.
Shayna chooses the question; Leon ranks; Rhea owns storage, reset/idempotence,
response validation, integration and any real model-usage accounting. Do not put
profiles, statistics, evidence, `should_ask`, or `question_value` in the response.
The existing brain injection hook alone does not implement post-ranking question
selection; wire that sequence deliberately.

## 4. Validate the combined implementation, not just the components

Add combined tests for the three blockers above, two interleaved sessions, reset
clearing old state, repeated calls, no stale override terms, and valid unique Top 10.
Then run the unmodified official evaluator with fresh output filenames:

```powershell
python -B -m unittest discover -s tests -v
python -B -m evaluator.local_evaluator --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output results_rhea_combined.json
python -B -m experiments.benchmark_runtime --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output results_rhea_summary.json --results-output results_rhea_sessions.json
git rev-parse HEAD
git status --short
```

The benchmark separately audits raw outputs, latency and provenance and retains
complete sessions. Its output files must not already exist. Compare HR/MRR/MTTC
and all four scenario slices, not just aggregate score. A no-LLM implementation
reports zero/omitted model usage; a later model client must report its actual usage.

Reference evidence: `experiments/evidence/candidate-20260831-v4/` recorded 98 tests,
196/200 public hits, TechnicalScore 0.888571, p95 802.844 ms and startup 31.356 s.
That startup still exceeds the team's 30-second goal. It is a reference fallback,
not permission to claim the same result for different conversation logic.

## 5. Freeze and submit

- Rhea reviews and merges; no direct assistant push to main or automatic merging.
- Freeze the reviewed runnable commit and record its SHA plus actual environment.
- Keep the full evaluator result, not only summary metrics or screenshots.
- Verify README setup and actual demo against that frozen commit.
- Retain original handoffs and known limitations; do not relabel historical runs.
- Follow the official final-evaluation FAQ at upstream `9c9e7c9`: once final sessions
  are released, do not change the frozen solution before its official evaluation.

Source of truth: [official final-evaluation FAQ](https://github.com/TechJam2026/techjam-conversational-search/blob/9c9e7c9ff6705142d6ab386dc1c432fc529df893/docs/final_evaluation_faq.md).
