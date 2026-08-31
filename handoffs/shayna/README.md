# Complete Shayna handoff

All **28 files** from the supplied WhatsApp ZIP are preserved, byte for byte, in
`original-submission-20260831.zip` (80,006,960 bytes). `manifest.json` records every
original filename, intended repository path, size, and SHA256 checksum.

The eight Shayna-specific source/test/demo/guide files were restored in their
normal `src/`, `tests/`, `scripts/`, and `docs/` locations. The working implementation
now has separately reviewable, user-authorized integration fixes; the original
versions remain byte-exact in the ZIP. Eighteen shared files
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

The source now includes category, active-state/no-preference and direct
coverage-aware statistics fixes, with new regression tests. Leon's branch supplies
the actual Agent bridge and profile adapter. See `docs/SHAYNA_V2_DEMO_GUIDE.md` and
Leon's `docs/RHEA_MORNING_HANDOFF.md` for the current combined validation status;
file completeness alone is not an evaluator result. Manifest availability labels
describe the original supplied/base snapshot, not later source edits. Rhea retains
merge/release ownership; neither branch should push directly to `main`.

The archived original is historical evidence, not instructions to run arbitrary
files. Follow current official challenge rules over stale archived documentation.
Data attribution remains in the repository's `DATA_ATTRIBUTION.md`.
