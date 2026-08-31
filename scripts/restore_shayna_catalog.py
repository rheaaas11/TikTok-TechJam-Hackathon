"""Verify Shayna's original ZIP and optionally restore only its two catalogs.

Run ``python scripts/restore_shayna_catalog.py --verify-only`` from the repo.
Only bytes are restored: archive permissions and manifest canonical paths are
never applied. Each new catalog is published atomically without replacing an
existing file. This is integrity checking, not authentication of the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, BinaryIO, Mapping
import zipfile


ARCHIVE_NAME = "original-submission-20260831.zip"
CATALOG_NAMES = ("catalog.jsonl", "catalog.jsonl.gz")
CHUNK_SIZE = 1024 * 1024


class ArchiveError(ValueError):
    """The package cannot be verified or safely restored."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveError(f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def load_manifest(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        manifest = json.load(handle, object_pairs_hook=_unique_object)
    if not isinstance(manifest, dict):
        raise ArchiveError("Manifest must be a JSON object")
    return manifest


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ArchiveError(f"Invalid SHA256 for {label}")
    return value.lower()


def _size(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ArchiveError(f"Invalid byte size for {label}")
    return value


def _safe_member_name(name: Any) -> str:
    # The original archive is flat. Never accept ZIP paths or Windows aliases.
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or any(character in name for character in '/\\:')
        or any(ord(character) < 32 for character in name)
        or name.endswith((".", " "))
        or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name, re.I)
    ):
        raise ArchiveError("Unsafe archive entry name")
    return name


def _manifest_entries(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if type(manifest.get("format_version")) is not int or manifest["format_version"] != 1:
        raise ArchiveError("Unsupported manifest format")
    if manifest.get("archive") != ARCHIVE_NAME:
        raise ArchiveError("Manifest archive must be the fixed original ZIP filename")
    _size(manifest.get("archive_size_bytes"), "archive")
    _digest(manifest.get("archive_sha256"), "archive")
    records = manifest.get("entries")
    if not isinstance(records, list) or not records:
        raise ArchiveError("Manifest entries must be a nonempty list")
    entries: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ArchiveError("Invalid manifest entry")
        name = _safe_member_name(record.get("archive_entry"))
        if name.casefold() in seen:
            raise ArchiveError(f"Duplicate manifest entry: {name}")
        seen.add(name.casefold())
        entries[name] = {
            "size_bytes": _size(record.get("size_bytes"), name),
            "sha256": _digest(record.get("sha256"), name),
        }
    if not all(name in entries for name in CATALOG_NAMES):
        raise ArchiveError("Both original catalog entries are required")
    return entries


def _stream_digest(stream: BinaryIO, expected_size: int) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    while chunk := stream.read(CHUNK_SIZE):
        count += len(chunk)
        if count > expected_size:
            raise ArchiveError("Stream exceeds declared byte size")
        digest.update(chunk)
    return count, digest.hexdigest()


def _require_digest(actual: tuple[int, str], expected: Mapping[str, Any], label: str) -> None:
    if actual != (expected["size_bytes"], expected["sha256"]):
        raise ArchiveError(f"Size or SHA256 mismatch: {label}")


def _verify_open_archive(
    stream: BinaryIO, manifest: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    entries = _manifest_entries(manifest)
    stream.seek(0)
    archive_expected = {
        "size_bytes": manifest["archive_size_bytes"],
        "sha256": manifest["archive_sha256"].lower(),
    }
    _require_digest(_stream_digest(stream, archive_expected["size_bytes"]), archive_expected, "archive")
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        seen: set[str] = set()
        for info in infos:
            name = _safe_member_name(info.orig_filename)
            if info.filename != name or name.casefold() in seen:
                raise ArchiveError(f"Duplicate or ambiguous ZIP entry: {name}")
            seen.add(name.casefold())
            file_type = stat.S_IFMT(info.external_attr >> 16)
            if (
                info.is_dir()
                or file_type not in (0, stat.S_IFREG)
                or info.external_attr & (0x10 | 0x400)
                or info.flag_bits & 1
            ):
                raise ArchiveError(f"Unsupported ZIP entry metadata: {name}")
        if {info.filename for info in infos} != set(entries):
            raise ArchiveError("ZIP entry set differs from the manifest")
        for info in infos:
            expected = entries[info.filename]
            if info.file_size != expected["size_bytes"]:
                raise ArchiveError(f"ZIP entry size mismatch: {info.filename}")
            with archive.open(info) as member:
                _require_digest(_stream_digest(member, expected["size_bytes"]), expected, info.filename)
    return entries


def verify_archive(archive_path: str | Path, manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Verify complete archive and every member without writing any files."""
    path = Path(archive_path)
    if path.name != ARCHIVE_NAME:
        raise ArchiveError("Unexpected archive filename")
    with path.open("rb") as stream:
        return _verify_open_archive(stream, manifest)


def _existing_matches(path: Path, expected: Mapping[str, Any]) -> bool:
    if path.is_symlink() or path.resolve() != path:
        raise ArchiveError(f"Refusing linked catalog target: {path.name}")
    if not path.exists():
        return False
    if not path.is_file():
        raise ArchiveError(f"Catalog target is not a regular file: {path.name}")
    with path.open("rb") as handle:
        _require_digest(_stream_digest(handle, expected["size_bytes"]), expected, path.name)
    return True


def restore_catalog(repo_root: str | Path, *, verify_only: bool = False) -> dict[str, str]:
    """Verify the handoff; restore/reuse only fixed ``data/catalog*`` targets.

    All existing targets are checked before any file is staged. Publication is
    per-file atomic, not a two-file transaction: a concurrent target collision
    can leave the other newly restored, complete catalog in place.
    """
    root = Path(repo_root).resolve(strict=True)
    manifest_path = root / "handoffs" / "shayna" / "manifest.json"
    manifest = load_manifest(manifest_path)
    archive_path = manifest_path.parent / ARCHIVE_NAME
    with archive_path.open("rb") as stream:
        entries = _verify_open_archive(stream, manifest)
        if verify_only:
            return {"archive": "verified", "entries": str(len(entries))}
        data_dir = root / "data"
        if data_dir.is_symlink() or data_dir.resolve() != data_dir:
            raise ArchiveError("Refusing linked data directory")
        if data_dir.exists() and not data_dir.is_dir():
            raise ArchiveError("Data path is not a directory")
        status: dict[str, str] = {}
        for name in CATALOG_NAMES:
            if _existing_matches(data_dir / name, entries[name]):
                status[name] = "reused"
        data_dir.mkdir(exist_ok=True)
        temporary: dict[str, Path] = {}
        try:
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                for name in CATALOG_NAMES:
                    if name in status:
                        continue
                    descriptor, temp_name = tempfile.mkstemp(prefix=f".{name}.restore-", suffix=".tmp", dir=data_dir)
                    temporary[name] = Path(temp_name)
                    with os.fdopen(descriptor, "wb") as output, archive.open(name) as member:
                        digest = hashlib.sha256()
                        count = 0
                        while chunk := member.read(CHUNK_SIZE):
                            count += len(chunk)
                            if count > entries[name]["size_bytes"]:
                                raise ArchiveError(f"Catalog exceeds declared size: {name}")
                            digest.update(chunk)
                            output.write(chunk)
                        _require_digest((count, digest.hexdigest()), entries[name], name)
                        output.flush()
                        os.fsync(output.fileno())
            for name, temporary_path in temporary.items():
                target = data_dir / name
                try:
                    # Unlike POSIX rename/replace, hard linking never clobbers.
                    # Fail safely if this filesystem lacks hard-link support.
                    os.link(temporary_path, target)
                    status[name] = "restored"
                except FileExistsError:
                    if not _existing_matches(target, entries[name]):
                        raise ArchiveError(f"Catalog target changed during restore: {name}")
                    status[name] = "reused"
        finally:
            for temporary_path in temporary.values():
                temporary_path.unlink(missing_ok=True)
        return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="verify every archive byte without restoring catalogs")
    args = parser.parse_args()
    try:
        result = restore_catalog(Path(__file__).resolve().parents[1], verify_only=args.verify_only)
    except (ArchiveError, OSError, zipfile.BadZipFile, RuntimeError) as error:
        parser.exit(1, f"Archive verification/restoration failed: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
