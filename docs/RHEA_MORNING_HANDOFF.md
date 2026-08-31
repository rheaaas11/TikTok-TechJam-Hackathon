# Rhea: combined Agent and morning release handoff

## Current status

The three original blockers are implemented: category handling, no-preference
transitions, and the statistics/response interface. The combined default Agent
now uses **Shayna's actual parser and dialogue policy**, not Leon's reference brain.

Final combined check: **211 tests pass; 196/200 public hits; TechnicalScore
0.857921; p95 314.99 ms; startup 9.66 s; process peak 608.77 MiB**. All 588
responses contain ten valid unique IDs; no Agent/reset exceptions or observed
network attempts. The runtime source commits are Leon `666f6d8` and Shayna
`db55586`; later evidence/documentation commits do not change that implementation.

The final measured candidate, exact source commits, scenarios and limitations are
recorded in `experiments/scoreboard.md` and `experiments/evidence/index.json`.
Do not substitute the older reference score for the combined score. Passing tests
alone is not the release gate; compare the complete evaluation artifacts.

Rhea retains review, merge, final model/policy selection and submission authority.
Neither feature branch pushes directly to main. The team's operational cutoff is
1 September at 12:00 pm Singapore time; verify the organizer page before uploading.

## 1. Review and combine the two feature branches

- **PR #2 / feature/shayna-profile:** original 28-entry ZIP preserved byte-for-byte;
  working profile/dialogue fixes and regression tests; safe catalogue setup helper.
- **PR #1 / feature/leon-ranking:** catalogue/retrieval/ranking; actual-profile
  adapter; transactional Agent bridge; one-pass ranking/statistics; tests and raw
  evaluation evidence.

Only the working copies are fixed. The original ZIP is an immutable audit record,
including its original baseline files. Never copy its old `starter/agent.py` over
the combined Agent. No protected evaluator, labels, scoring files, API contract or
original evaluator tests are changed.

On Rhea's chosen integration branch, after reviewing both PRs:

```powershell
git fetch origin
git merge --no-ff origin/feature/shayna-profile
git merge --no-ff origin/feature/leon-ranking
python -B scripts/restore_shayna_catalog.py --verify-only
python -B scripts/restore_shayna_catalog.py
python -B -m unittest discover -s tests -v
```

The restore helper verifies every original ZIP entry, restores only the two fixed
catalogue filenames, reuses exact existing inputs, and refuses conflicting files.
Python 3.10+ and SQLite FTS5 are expected; no third-party runtime packages or model
credentials are required.

## 2. What is now connected

```text
reset -> fresh isolated session
message -> Shayna update_profile
        -> ShaynaProfileAdapter (active state only)
        -> Leon rank_with_stats once
        -> Shayna decide_next_turn(candidate_statistics=...)
        -> official response composition
        -> commit state + cache response
```

- Singular/plural category matching is whole-word, with full useful category
  context retained without carrying cleared colors/materials into later turns.
- No preference removes old slot values; a later explicit value reactivates it.
  No *additional* preference preserves known values but marks the slot exhausted.
- Start-over clears active intent; targeted replacements retain unrelated intent.
- Rich requirement phrases and measurements survive parsing. Conversational
  framing is not converted into shopping requirements.
- Candidate utility consumes coverage and expected remaining pool directly.
  `top_values` is only a preview, never a complete distribution.
- An observed unproductive narrow question can trigger broad clarification.
  Broad clarification repeats only after meaningful new information, not refusal.
- `rank()` returns product dictionaries already. Do not double-wrap IDs.
- The response contains only `message`, `ask_attribute`, `recommendations`
  (and actual `usage` only if a future model client is introduced). No diagnostics,
  profiles, evidence, `should_ask`, or `question_value` leak into it.
- Failed search/policy/composition does not commit Shayna state. Exact duplicate
  turns return independent cached copies; changed duplicate requests are rejected.
  Reset and interleaved sessions are tested.

See `docs/COMBINED_AGENT.md` for interfaces and intentional compatibility limits.

## 3. Evaluate the actual combined implementation

The evaluator's normal `Agent()` uses auto mode: both `src` modules present means
Shayna. Both absent means Leon-only reference fallback; partial/broken imports
raise instead of silently changing systems.

Use fresh output filenames and require the runtime identity:

```powershell
python -B -m experiments.benchmark_runtime --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output results_rhea_combined_summary.json --results-output results_rhea_combined_sessions.json --conversation-mode auto --expected-brain starter.shayna_conversation.ShaynaConversationBrain
git rev-parse HEAD
git status --short
```

The benchmark calls the unchanged official evaluator and additionally records
raw response validity, all 200 sessions, actual brain/adapter identities, both
implementation packages' hashes, input checksums, latency, process memory and
environment. It refuses an existing output filename.

For an isolated source-copy check, use a new directory outside the checkout:

```powershell
python -B experiments/verify_snapshot.py --destination D:\ShopSense-validation-final --evaluate --conversation-mode auto --expected-brain starter.shayna_conversation.ShaynaConversationBrain
```

This uses Python isolated mode, verifies import origins and source hashes before
and after, and blocks Python socket/DNS calls. It is not an OS-wide network sandbox
or a claim that a source export is a fresh Git clone.

## 4. Score interpretation and fallback decision

The first wired candidate was rejected after scoring 0.471163. Generic parser,
question-policy and negated-evidence corrections recovered the second candidate to
0.853396 (195/200 hits). Final-source reruns are recorded separately in the
scoreboard; intermediate evidence is retained, not overwritten.

A same-source rerun of the explicit reference system reproduced **0.888571**,
versus the combined default's **0.857921**. Both find 196/200 targets, but the
combined system has lower reciprocal rank and takes more turns. Buying hits
improve by one; Override hits fall by one. The combined candidate therefore is
**not promoted as a score improvement** under the earlier regression rule merely
because integration and contract gates pass. Rhea should make the release-policy
choice explicitly; the comparison and complete results are in the scoreboard.

For a reproducible comparison, the benchmark accepts
`--conversation-mode reference --expected-brain starter.conversation.ReferenceConversationBrain`.
This flag changes the benchmark's construction, **not** the official evaluator's
default Agent. If Rhea deliberately selects reference for submission, she must
make that explicit in her reviewed integration change, rerun the official entrypoint
and describe the actual contribution accurately. Do not claim Shayna's parser
was evaluated when it was bypassed.

Remaining limits: rule-based parsing and finite category aliases; heuristic
question answerability; non-exhaustive free-text negation; incomplete catalogue
metadata; no private-set guarantee. The 30-second startup, 1-second p95 and 2-GB
memory thresholds are team targets, not official organizer limits.

## 5. Freeze and submit

1. Review both diffs and ensure no protected paths changed.
2. Run tests and the full evaluator against the actual combined/release Agent.
3. Check every scenario and raw-output audit; keep complete per-session results.
4. Record the merged commit, source/input hashes, environment and exact commands.
5. Verify the README, catalogue setup and demo against that commit.
6. Freeze the chosen runnable commit before the Devpost submission deadline; do
   not modify the solution after the final evaluation package is released.
7. Rhea performs the reviewed merge and final submission; no automatic merging.

Source of truth: [official final-evaluation FAQ](https://github.com/TechJam2026/techjam-conversational-search/blob/9c9e7c9ff6705142d6ab386dc1c432fc529df893/docs/final_evaluation_faq.md).
