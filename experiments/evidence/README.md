# Complete Leon development evidence

This folder preserves all 16 original result/audit artifacts plus the new actual
integration checkpoints, same-source reference comparison and source provenance.
`index.json` records artifact byte sizes and SHA256 checksums. These are
public-set development outputs; runtime code must never import or read this folder.

## Current combined and comparison runs

- `candidate-20260901-integrated-4/`: actual Shayna + Leon, default auto selection;
  211 tests pass; 196/200 hits; TechnicalScore **0.857921**; p95 314.99 ms;
  zero invalid outputs, exceptions or observed network attempts.
- `candidate-20260901-reference-comparison/`: same exact solution files with the
  explicit reference brain/adapter selected; TechnicalScore **0.888571**.
- `candidate-20260901-integrated-1/`: rejected initial wiring, score 0.471163.
- `candidate-20260901-integrated-2/` and `-3/`: superseded development checkpoints.

The final combined and reference runs share the source commits/tree identified
in `source_commits.json`; the original summary and manifest preserve their actual
execution hashes and local paths. The combined candidate is **not promoted as a
score improvement over the reference**. Rhea retains the explicit release choice.
Both source branches must be combined to get the actual teammate implementation.

## Historical reference candidate

`candidate-20260831-v4/` contains the complete official 200-session result,
timing/provenance summary, isolated-source manifest, and validation report:

- 98 tests passed; all 200 sessions completed; 196 target hits.
- HR@10 0.980; MRR 0.747905; MTTC 2.290; TechnicalScore 0.888571.
- Zero Agent/reset exceptions or invalid raw responses; every audited turn had ten
  valid unique recommendations. No Python socket/DNS attempt was observed.
- Startup 31.356 s; response p95 802.844 ms; whole-process peak 602.793 MiB.

The measured source uses Leon's replaceable **reference conversation brain**, not
Shayna's implementation. These numbers are not a combined-agent score, not a
private-set guarantee, and not proof of an optimal design.

Files retain their original metadata, including historical local paths and null
Git fields for the no-`.git` validation snapshot. Do not rewrite those fields to
pretend this was a later integrated or submitted-commit run. Raw-file checksums may
depend on Windows line endings; the evidence files are binary-preserved on purpose.

## Historical results

`historical/` retains earlier baseline, implementation, correctness, and timing
outputs. Some older artifacts contain only summary metrics. They are superseded,
not additional validation of the latest candidate. Consult `../scoreboard.md` for
the progression and limits; do not choose whichever old score looks best.

No full 60 MB catalogue/snapshot copy, Python caches, credentials, or temporary
authentication helpers are included in this evidence folder. Shayna's complete
original archive separately supplies the frozen catalogue for local setup.

Before submission, Rhea must evaluate the actual combined/frozen commit with the
unmodified official evaluator and retain its complete new results separately.
