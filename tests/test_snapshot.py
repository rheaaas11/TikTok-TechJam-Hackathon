from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path

from experiments.verify_snapshot import REQUIRED, copy_snapshot, offline_guard, verify_evaluation, verify_manifest


class SnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        for name in REQUIRED:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if path.suffix == ".json" else "# fixture\n", encoding="utf-8")
        self.catalog = self.source / "data/catalog.jsonl"
        self.catalog.write_text('{"parent_asin":"A"}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_copy_is_hash_verified_and_omits_credentials_and_prior_results(self) -> None:
        (self.source / ".env").write_text("fixture-secret", encoding="utf-8")
        (self.source / "results_old.json").write_text("{}", encoding="utf-8")
        destination = self.root / "candidate"
        manifest = copy_snapshot(self.source, destination, self.catalog)
        self.assertEqual(verify_manifest(destination), manifest)
        self.assertFalse((destination / ".env").exists())
        self.assertFalse((destination / "results_old.json").exists())
        self.assertEqual((destination / "data/catalog.jsonl").read_bytes(), self.catalog.read_bytes())
        self.assertNotIn("fixture-secret", json.dumps(manifest))

    def test_existing_destination_and_nested_source_destination_are_rejected(self) -> None:
        destination = self.root / "existing"
        destination.mkdir()
        with self.assertRaises(FileExistsError):
            copy_snapshot(self.source, destination, self.catalog)
        with self.assertRaises(ValueError):
            copy_snapshot(self.source, self.source / "nested", self.catalog)
        self.assertEqual(list(destination.iterdir()), [])

    def test_changed_snapshot_and_manifest_escape_are_rejected(self) -> None:
        destination = self.root / "candidate"
        copy_snapshot(self.source, destination, self.catalog)
        (destination / "starter/agent.py").write_text("# changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_manifest(destination)
        manifest = {"file_sha256": {"../outside.py": "ignored"}}
        (destination / "snapshot_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_manifest(destination)

    def test_offline_guard_blocks_and_restores_socket_calls(self) -> None:
        original = socket.create_connection
        with offline_guard() as attempts:
            with self.assertRaises(RuntimeError):
                socket.create_connection(("invalid.example", 443))
            self.assertEqual(len(attempts), 1)
        self.assertIs(socket.create_connection, original)

    def test_evaluation_requires_complete_matching_sessions_and_zero_raw_errors(self) -> None:
        (self.source / "data/public_set.jsonl").write_text('{"sample_id":"s1"}\n', encoding="utf-8")
        result = {"sample_count": 1, "hit_rate_at_10": 0.0, "sessions": [{"sample_id": "s1"}]}
        summary = {
            "metrics": {"sample_count": 1, "hit_rate_at_10": 0.0},
            "agent_exceptions": 0, "reset_exceptions": 0, "timed_turns": 1,
            "raw_response_audit": {"invalid_responses": 0, "violations_by_affected_response": {},
                                   "catalog_membership_checked": True, "responses_audited": 1,
                                   "recommendation_count_distribution": {"10": 1}},
        }
        def save():
            (self.source / "results_snapshot_summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (self.source / "results_snapshot_sessions.json").write_text(json.dumps(result), encoding="utf-8")
        save()
        # A low retrieval score alone is not an integrity failure.
        self.assertEqual(verify_evaluation(self.source)["session_count"], 1)
        for field in ("agent_exceptions", "reset_exceptions"):
            summary[field] = 1
            save()
            with self.assertRaises(ValueError):
                verify_evaluation(self.source)
            summary[field] = 0
        summary["raw_response_audit"]["invalid_responses"] = 1
        save()
        with self.assertRaises(ValueError):
            verify_evaluation(self.source)
        summary["raw_response_audit"]["invalid_responses"] = 0
        summary["metrics"]["hit_rate_at_10"] = 1.0
        save()
        with self.assertRaises(ValueError):
            verify_evaluation(self.source)
        summary["metrics"]["hit_rate_at_10"] = 0.0
        result["sessions"] = [{"sample_id": "other"}]
        save()
        with self.assertRaises(ValueError):
            verify_evaluation(self.source)


if __name__ == "__main__":
    unittest.main()
