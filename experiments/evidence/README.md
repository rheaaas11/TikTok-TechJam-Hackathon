# Complete Leon development evidence

This folder preserves all 16 identified result/audit artifacts from Leon's work.
`index.json` records their original byte sizes and SHA256 checksums. These are
public-set development outputs; runtime code must never import or read this folder.

## Latest reference candidate

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
