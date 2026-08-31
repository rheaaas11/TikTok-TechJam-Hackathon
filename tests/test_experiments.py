from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from experiments.make_split import stable_split
from experiments.benchmark_runtime import (
    TimedAgent, collect_provenance, file_sha256, main, output_paths, percentile,
    process_peak_working_set,
    require_brain, runtime_identity,
)


class ExperimentSplitTest(unittest.TestCase):
    def test_nearest_rank_percentile(self) -> None:
        self.assertEqual(percentile([0.3, 0.1, 0.2, 0.4], 0.5), 0.2)
        self.assertEqual(percentile([], 0.95), 0.0)

    def test_timing_wrapper_counts_hidden_agent_exceptions(self) -> None:
        class BrokenAgent:
            def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
                raise RuntimeError("boom")

        timed = TimedAgent(BrokenAgent())  # type: ignore[arg-type]
        with self.assertRaises(RuntimeError):
            timed.respond("s", "x", 1, 10)
        self.assertEqual(timed.exception_count, 1)
        self.assertEqual(len(timed.latencies), 1)

    def test_fixed_split_is_disjoint_deterministic_and_label_free(self) -> None:
        samples = [
            {
                "sample_id": f"s{index:02d}",
                "scenario_type": "buying" if index < 5 else "browsing",
                "difficulty_bucket": "easy" if index % 2 else "hard",
                "category_bucket": "shoes",
                "ground_truth": {"parent_asin": f"secret-{index}"},
            }
            for index in range(10)
        ]
        first = stable_split(samples, validation_size=2, seed="fixed")
        second = stable_split(samples, validation_size=2, seed="fixed")
        self.assertEqual(first, second)
        self.assertEqual(len(first["dev_ids"]), 8)
        self.assertEqual(len(first["validation_ids"]), 2)
        self.assertFalse(set(first["dev_ids"]) & set(first["validation_ids"]))
        self.assertNotIn("ground_truth", str(first))
        self.assertNotIn("secret", str(first))


class BenchmarkAuditTest(unittest.TestCase):
    @staticmethod
    def response() -> dict:
        return {"message": "ok", "ask_attribute": None,
                "recommendations": [{"parent_asin": "A", "score": 1.0}]}

    def test_valid_raw_response_is_audited_without_mutation(self) -> None:
        response = self.response()
        response["usage"] = {"prompt_tokens": 0, "completion_tokens": 2}
        agent = Mock()
        agent.respond.return_value = response
        timed = TimedAgent(agent, valid_ids={"A"})
        self.assertIs(timed.respond("s", "x", 1, 10), response)
        self.assertEqual(timed.audit_summary()["invalid_responses"], 0)
        self.assertEqual(timed.audit_summary()["recommendation_count_distribution"], {"1": 1})
        self.assertEqual(len(timed.latencies), 1)

    def test_duplicate_invalid_ids_and_team_limit_are_independent_of_evaluator_normalization(self) -> None:
        response = self.response()
        response["recommendations"] = [{"parent_asin": "A"}] * 10 + [{"parent_asin": "unknown"}]
        agent = Mock()
        agent.respond.return_value = response
        timed = TimedAgent(agent, valid_ids={"A"})
        self.assertIs(timed.respond("s", "x", 1, 10), response)
        errors = timed.audit_summary()["violations_by_affected_response"]
        self.assertEqual(errors, {"duplicate_parent_asin": 1, "team_recommendation_limit_exceeded": 1,
                                  "unknown_parent_asin": 1})
        self.assertEqual(timed.invalid_responses, 1)

    def test_malformed_fields_usage_and_items_are_reported_without_raising(self) -> None:
        cases = [
            (None, "response_not_dict"),
            ({}, "required_fields_missing"),
            ({**self.response(), "debug": "do not retain this"}, "extra_response_fields"),
            ({**self.response(), "message": 5}, "invalid_message"),
            ({**self.response(), "ask_attribute": []}, "invalid_ask_attribute"),
            ({**self.response(), "recommendations": "A"}, "recommendations_not_list"),
            ({**self.response(), "recommendations": ["A"]}, "recommendation_not_dict"),
            ({**self.response(), "recommendations": [{"parent_asin": None}]}, "invalid_parent_asin"),
            ({**self.response(), "recommendations": [{"parent_asin": "A", "why": "x"}]},
             "extra_recommendation_fields"),
            ({**self.response(), "recommendations": [{"parent_asin": "A", "score": float("nan")}]},
             "invalid_recommendation_score"),
        ]
        for response, expected in cases:
            with self.subTest(expected=expected):
                agent = Mock()
                agent.respond.return_value = response
                timed = TimedAgent(agent)
                self.assertIs(timed.respond("s", "x", 1, 10), response)
                self.assertIn(expected, timed.audit_violations)
                self.assertNotIn("do not retain", str(timed.audit_summary()))
        for usage in (None, {}, {"prompt_tokens": True, "completion_tokens": 0},
                      {"prompt_tokens": -1, "completion_tokens": 0},
                      {"prompt_tokens": 0, "completion_tokens": 0, "secret": "x"}):
            agent = Mock()
            agent.respond.return_value = {**self.response(), "usage": usage}
            timed = TimedAgent(agent)
            timed.respond("s", "x", 1, 10)
            self.assertIn("invalid_usage", timed.audit_violations)

    def test_reset_exceptions_are_counted_and_preserved(self) -> None:
        agent = Mock()
        agent.reset.side_effect = RuntimeError("not retained")
        timed = TimedAgent(agent)
        with self.assertRaises(RuntimeError):
            timed.reset("s", {})
        self.assertEqual(timed.reset_exception_count, 1)

    def test_output_paths_reject_aliasing_and_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            with self.assertRaises(ValueError):
                output_paths(path, path.parent / "." / path.name)
            path.write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                output_paths(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "preserve")

    def test_main_retains_full_official_sessions_and_separate_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.json"
            results = Path(directory) / "results.json"
            official = {"sample_count": 1, "hit_rate_at_10": 1.0,
                        "sessions": [{"sample_id": "s", "hit": True, "first_hit_turn": 1}]}
            with patch("experiments.benchmark_runtime.collect_provenance", return_value={"git_head": "abc"}), \
                 patch("experiments.benchmark_runtime.load_jsonl", return_value=[]), \
                 patch("experiments.benchmark_runtime.catalog_index", return_value=({"A"}, {}, {})), \
                 patch("experiments.benchmark_runtime.Agent") as agent, \
                 patch("experiments.benchmark_runtime.evaluate", return_value=official), \
                 patch("experiments.benchmark_runtime.process_peak_working_set", return_value={"available": False}), \
                 patch("sys.stdout", new_callable=io.StringIO):
                main(["--output", str(summary), "--results-output", str(results)])
                agent.assert_called_once_with("data/catalog.jsonl", conversation_mode="auto")
                agent.return_value.close.assert_called_once()
            self.assertEqual(json.loads(results.read_text(encoding="utf-8")), official)
            saved = json.loads(summary.read_text(encoding="utf-8"))
            self.assertNotIn("sessions", saved["metrics"])
            self.assertEqual(saved["official_results_path"], str(results.resolve()))
            self.assertEqual(saved["turn_latency_ms"]["p50"], 0.0)
            self.assertIn("brain", saved["runtime_identity"])
            self.assertEqual(saved["requested_conversation_mode"], "auto")
            with patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    main(["--output", str(summary), "--results-output", str(results)])
            self.assertEqual(json.loads(results.read_text(encoding="utf-8")), official)

    def test_runtime_identity_and_expected_brain_reject_silent_fallback(self) -> None:
        class FixtureBrain:
            pass

        brain = FixtureBrain()
        agent = SimpleNamespace(brain=brain, ranker=SimpleNamespace(profile_adapter=None), composer=None)
        identity = runtime_identity(agent)
        self.assertTrue(identity["brain"].endswith(".FixtureBrain"))
        self.assertIsNone(identity["profile_adapter"])
        require_brain(identity, identity["brain"])
        require_brain(identity, None)
        with self.assertRaises(ValueError):
            require_brain(identity, "starter.shayna_conversation.ShaynaConversationBrain")

    def test_wrong_expected_brain_stops_before_evaluation_and_closes_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("experiments.benchmark_runtime.collect_provenance", return_value={}), \
                 patch("experiments.benchmark_runtime.load_jsonl", return_value=[]), \
                 patch("experiments.benchmark_runtime.catalog_index", return_value=({"A"}, {}, {})), \
                 patch("experiments.benchmark_runtime.Agent") as agent, \
                 patch("experiments.benchmark_runtime.evaluate") as evaluate:
                with self.assertRaisesRegex(ValueError, "Refusing to evaluate"):
                    main(["--output", str(Path(directory) / "summary.json"),
                          "--conversation-mode", "shayna",
                          "--expected-brain", "starter.shayna_conversation.ShaynaConversationBrain"])
                agent.assert_called_once_with("data/catalog.jsonl", conversation_mode="shayna")
                evaluate.assert_not_called()
                agent.return_value.close.assert_called_once()

    def test_provenance_fingerprints_sources_and_data_without_environment_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "starter").mkdir()
            source = root / "starter" / "agent.py"
            source.write_text("version = 1\n", encoding="utf-8")
            data = root / "catalog.jsonl"
            data.write_text("{}\n", encoding="utf-8")
            head = Mock(returncode=0, stdout="abc\n")
            status = Mock(returncode=0, stdout=" M starter/agent.py\n")
            with patch("experiments.benchmark_runtime.subprocess.run", side_effect=[head, status, head, status]), \
                 patch("experiments.benchmark_runtime.platform.platform", return_value="test-platform"), \
                 patch("experiments.benchmark_runtime.platform.machine", return_value="test-machine"):
                first = collect_provenance(data, data, root)
                source.write_text("version = 2\n", encoding="utf-8")
                second = collect_provenance(data, data, root)
            self.assertEqual(first["git_head"], "abc")
            self.assertTrue(first["git_dirty"])
            self.assertNotEqual(first["starter_source_sha256"], second["starter_source_sha256"])
            self.assertEqual(first["data"]["catalog"]["sha256"], file_sha256(data))
            self.assertEqual(set(first["starter_file_sha256"]), {"starter/agent.py"})

    def test_solution_provenance_includes_nested_teammate_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("starter/agent.py", "src/__init__.py", "src/profile.py", "src/nested/helper.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("version = 1\n", encoding="utf-8")
            data = root / "catalog.jsonl"
            data.write_text("{}\n", encoding="utf-8")
            with patch("experiments.benchmark_runtime.subprocess.run", side_effect=OSError):
                first = collect_provenance(data, data, root)
                (root / "src/profile.py").write_text("version = 2\n", encoding="utf-8")
                second = collect_provenance(data, data, root)
            self.assertEqual(first["starter_source_sha256"], second["starter_source_sha256"])
            self.assertNotEqual(first["solution_source_sha256"], second["solution_source_sha256"])
            self.assertEqual(set(first["solution_file_sha256"]),
                             {"starter/agent.py", "src/__init__.py", "src/profile.py", "src/nested/helper.py"})

    def test_non_windows_memory_measurement_is_explicitly_unavailable(self) -> None:
        with patch("experiments.benchmark_runtime.sys.platform", "linux"):
            memory = process_peak_working_set()
        self.assertFalse(memory["available"])
        self.assertIn("process lifetime", memory["scope"])


if __name__ == "__main__":
    unittest.main()
