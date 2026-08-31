"""Small synthetic ZIP tests; never copy or restore the real 80 MB handoff."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

from scripts.restore_shayna_catalog import ARCHIVE_NAME, ArchiveError, load_manifest, restore_catalog, verify_archive


class ShaynaArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.handoff = self.root / "handoffs" / "shayna"
        self.handoff.mkdir(parents=True)
        self.archive = self.handoff / ARCHIVE_NAME
        self.manifest_path = self.handoff / "manifest.json"
        self.contents = {"catalog.jsonl": b'{"parent_asin":"fixture"}\n', "catalog.jsonl.gz": b"gzip fixture bytes", "profile.py": b"# original fixture\n"}
        self.write_fixture()

    def write_fixture(self, *, extra=None, symlink=False):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, contents in self.contents.items():
                    if symlink and name == "profile.py":
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(info, contents)
                    else:
                        archive.writestr(name, contents)
                if extra:
                    archive.writestr(*extra)
        self.manifest = {
            "format_version": 1,
            "archive": ARCHIVE_NAME,
            "archive_size_bytes": self.archive.stat().st_size,
            "archive_sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "entries": [
                {"archive_entry": name, "canonical_path": "../../must-not-be-written", "size_bytes": len(contents), "sha256": hashlib.sha256(contents).hexdigest()}
                for name, contents in self.contents.items()
            ],
        }
        self.save_manifest()

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_verify_only_writes_nothing(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(restore_catalog(self.root, verify_only=True), {"archive": "verified", "entries": "3"})
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / "data").exists())

    def test_restore_fixed_targets_and_reuse_without_touching_other_files(self):
        protected = self.root / "src" / "profile.py"
        protected.parent.mkdir()
        protected.write_bytes(b"existing implementation")
        self.assertEqual(restore_catalog(self.root), {"catalog.jsonl": "restored", "catalog.jsonl.gz": "restored"})
        timestamps = {name: (self.root / "data" / name).stat().st_mtime_ns for name in ("catalog.jsonl", "catalog.jsonl.gz")}
        self.assertEqual(restore_catalog(self.root), {"catalog.jsonl": "reused", "catalog.jsonl.gz": "reused"})
        self.assertEqual(protected.read_bytes(), b"existing implementation")
        self.assertFalse((self.root.parent / "must-not-be-written").exists())
        self.assertEqual({p.name for p in (self.root / "data").iterdir()}, {"catalog.jsonl", "catalog.jsonl.gz"})
        for name in timestamps:
            self.assertEqual((self.root / "data" / name).read_bytes(), self.contents[name])
            self.assertEqual((self.root / "data" / name).stat().st_mtime_ns, timestamps[name])

    def test_archive_bytes_tampered(self):
        content = bytearray(self.archive.read_bytes())
        content[len(content) // 2] ^= 1
        self.archive.write_bytes(content)
        with self.assertRaises(ArchiveError):
            restore_catalog(self.root)
        self.assertFalse((self.root / "data").exists())

    def test_nonzip_with_matching_outer_hash_is_rejected(self):
        self.archive.write_bytes(b"not a ZIP")
        self.manifest["archive_size_bytes"] = self.archive.stat().st_size
        self.manifest["archive_sha256"] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.save_manifest()
        with self.assertRaises(zipfile.BadZipFile):
            restore_catalog(self.root)

    def test_entry_content_hash_and_size_are_verified(self):
        for field, value in (("sha256", "0" * 64), ("size_bytes", 1)):
            with self.subTest(field=field):
                self.write_fixture()
                self.manifest["entries"][-1][field] = value
                self.save_manifest()
                with self.assertRaises(ArchiveError):
                    restore_catalog(self.root)
                self.assertFalse((self.root / "data").exists())

    def test_duplicate_zip_entries_are_rejected(self):
        self.write_fixture(extra=("profile.py", self.contents["profile.py"]))
        with self.assertRaisesRegex(ArchiveError, "Duplicate"):
            verify_archive(self.archive, self.manifest)

    def test_duplicate_manifest_entries_and_keys_are_rejected(self):
        self.manifest["entries"].append(dict(self.manifest["entries"][0]))
        with self.assertRaisesRegex(ArchiveError, "Duplicate"):
            verify_archive(self.archive, self.manifest)
        self.manifest_path.write_text('{"format_version":1,"format_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(ArchiveError, "Duplicate"):
            load_manifest(self.manifest_path)

    def test_extra_or_missing_zip_entries_are_rejected(self):
        self.write_fixture(extra=("extra.txt", b"unexpected"))
        with self.assertRaisesRegex(ArchiveError, "entry set"):
            verify_archive(self.archive, self.manifest)
        self.write_fixture()
        self.manifest["entries"].append({"archive_entry": "missing.txt", "size_bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()})
        with self.assertRaisesRegex(ArchiveError, "entry set"):
            verify_archive(self.archive, self.manifest)

    def test_unsafe_zip_names_rejected_even_if_manifest_does_not_list_them(self):
        for name in ("../escape", "/absolute", "C:\\escape", "data/catalog.jsonl", "CON.txt", "trailing."):
            with self.subTest(name=name):
                self.write_fixture(extra=(name, b"unsafe"))
                with self.assertRaises(ArchiveError):
                    restore_catalog(self.root)
                self.assertFalse((self.root / "data").exists())

    def test_invalid_manifest_metadata_rejected(self):
        for field, value in (("archive", "../../other.zip"), ("archive_size_bytes", True), ("archive_size_bytes", -1), ("archive_sha256", "bad"), ("format_version", True)):
            with self.subTest(field=field, value=value):
                self.write_fixture()
                self.manifest[field] = value
                self.save_manifest()
                with self.assertRaises(ArchiveError):
                    restore_catalog(self.root)
        self.write_fixture()
        self.manifest["entries"][0]["archive_entry"] = "../catalog.jsonl"
        with self.assertRaises(ArchiveError):
            verify_archive(self.archive, self.manifest)

    def test_symlink_zip_metadata_rejected(self):
        self.write_fixture(symlink=True)
        with self.assertRaisesRegex(ArchiveError, "metadata"):
            restore_catalog(self.root)

    def test_existing_mismatch_refuses_before_publishing_other_catalog(self):
        data = self.root / "data"
        data.mkdir()
        target = data / "catalog.jsonl.gz"
        target.write_bytes(b"user data")
        with self.assertRaises(ArchiveError):
            restore_catalog(self.root)
        self.assertEqual(target.read_bytes(), b"user data")
        self.assertFalse((data / "catalog.jsonl").exists())
        self.assertEqual(list(data.iterdir()), [target])

    def test_publication_failure_cleans_only_own_temporary_files(self):
        data = self.root / "data"
        data.mkdir()
        unrelated = data / ".user-file.tmp"
        unrelated.write_bytes(b"keep")
        with mock.patch("scripts.restore_shayna_catalog.os.link", side_effect=OSError("unsupported")):
            with self.assertRaises(OSError):
                restore_catalog(self.root)
        self.assertEqual(list(data.iterdir()), [unrelated])
        self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_concurrent_target_creation_is_not_overwritten(self):
        def collide(source, target):
            Path(target).write_bytes(b"another writer")
            raise FileExistsError("racing target")

        with mock.patch("scripts.restore_shayna_catalog.os.link", side_effect=collide):
            with self.assertRaises(ArchiveError):
                restore_catalog(self.root)
        data = self.root / "data"
        self.assertEqual((data / "catalog.jsonl").read_bytes(), b"another writer")
        self.assertEqual({p.name for p in data.iterdir()}, {"catalog.jsonl"})


if __name__ == "__main__":
    unittest.main()
