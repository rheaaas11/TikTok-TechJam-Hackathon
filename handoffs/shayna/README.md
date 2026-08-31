# Complete Shayna handoff

All **28 files** from the supplied WhatsApp ZIP are preserved, byte for byte, in
`original-submission-20260831.zip` (80,006,960 bytes). `manifest.json` records every
original filename, intended repository path, size, and SHA256 checksum.

The eight Shayna-specific source/test/demo/guide files are also restored in their
normal `src/`, `tests/`, `scripts/`, and `docs/` locations. Eighteen shared files
already match the team repository (some have Windows-versus-Unix line endings).
Those existing official files were not overwritten. The archive also contains
both original frozen catalogue files; nothing from the supplied ZIP was omitted.

## Setup from the repository root

```powershell
python -B scripts/restore_shayna_catalog.py --verify-only
python -B scripts/restore_shayna_catalog.py
python -B -m unittest discover -s tests -v
python -B scripts/demo_shayna_v2.py
```

The setup helper verifies the whole archive and every entry, then restores only
`data/catalog.jsonl` and `data/catalog.jsonl.gz`. These are ignored local inputs.
An existing exact-match file is reused; an existing different file is never
overwritten. No evaluator, labels, contract, source, or scoring files are extracted
over the checkout. Allow roughly 80 MB free for the two restored catalogue inputs.

## Integration status

This is a complete **file handoff**, not proof of a working combined agent.
Shayna's supplied parsing and dialogue logic is preserved unchanged. The known
category, no-preference, and statistics/response-interface issues require explicit
review and fixes before final integration. See Leon's `docs/RHEA_MORNING_HANDOFF.md`
after combining the two reviewed feature branches. Rhea retains merge and release
ownership; neither branch should push directly to `main`.

The archived original is historical evidence, not instructions to run arbitrary
files. Follow current official challenge rules over stale archived documentation.
Data attribution remains in the repository's `DATA_ATTRIBUTION.md`.
