"""Actual combined-component regressions; skip only in Leon-only checkouts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from starter.agent import Agent, OfficialResponseComposer
from starter.conversation import StateUpdate
from tests.test_retrieval import PRODUCTS


HAS_SHAYNA = (Path(__file__).resolve().parents[1] / "src" / "profile.py").is_file()


class ResponseBoundaryTest(unittest.TestCase):
    def test_nested_ids_and_non_objects_are_not_stringified(self):
        response = OfficialResponseComposer().compose(StateUpdate(None, "ok", "not_allowed"), [
            {"parent_asin": {"parent_asin": "A"}}, {"parent_asin": 123}, None,
            {"parent_asin": "A", "evidence": "private sidecar"}, {"parent_asin": "A"},
        ])
        self.assertEqual(response, {"message": "ok", "ask_attribute": None,
                                    "recommendations": [{"parent_asin": "A"}]})

    def test_reference_mode_remains_explicit(self):
        class Backend:
            def rank(self, profile, top_k=10):
                return []
        agent = Agent(None, ranker=Backend(), conversation_mode="reference")
        self.assertEqual(type(agent.brain).__name__, "ReferenceConversationBrain")

    def test_partial_shayna_installation_fails_instead_of_silent_fallback(self):
        with patch("starter.agent.Path.is_file", side_effect=[True, False]):
            with self.assertRaisesRegex(ImportError, "requires both"):
                Agent(None, ranker=object())

    def test_absent_shayna_is_explicitly_selectable_not_mislabeled(self):
        with patch("starter.agent.Path.is_file", return_value=False):
            agent = Agent(None, ranker=object())
            self.assertEqual(type(agent.brain).__name__, "ReferenceConversationBrain")
            with self.assertRaises(ImportError):
                Agent(None, ranker=object(), conversation_mode="shayna")


@unittest.skipUnless(HAS_SHAYNA, "requires Shayna's feature branch")
class ShaynaIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        catalog = Path(self.directory.name) / "catalog.jsonl"
        catalog.write_text("".join(json.dumps(product) + "\n" for product in PRODUCTS), encoding="utf-8")
        self.agent = Agent(catalog, conversation_mode="shayna")
        self.addCleanup(self.agent.close)

    def test_default_in_combined_tree_uses_real_shayna(self):
        automatically_selected = Agent(None, ranker=self.agent.ranker)
        self.assertEqual(type(automatically_selected.brain).__name__, "ShaynaConversationBrain")
        self.assertEqual(type(self.agent.ranker.profile_adapter).__name__, "ShaynaProfileAdapter")

    def test_singular_and_plural_dress_rank_the_same(self):
        responses = []
        for session, phrase in (("one", "a dress"), ("two", "dresses")):
            self.agent.reset(session, {})
            responses.append(self.agent.respond(session, "I need " + phrase + " in red polyester.", 1, 10))
        self.assertEqual(responses[0]["recommendations"], responses[1]["recommendations"])
        self.assertEqual(responses[0]["recommendations"][0]["parent_asin"], "C")

    def test_no_preference_then_new_value_removes_stale_terms(self):
        self.agent.reset("s", {})
        for turn, message in enumerate(("I want red shoes.", "No preference for color.", "Actually make them blue."), 1):
            self.agent.respond("s", message, turn, 10)
            profile = self.agent.brain.sessions["s"]
            if turn == 2:
                self.assertFalse(any(c.attribute == "color" for c in profile.active_constraints))
                self.assertNotIn("red", " ".join(profile.query_terms))
        canonical = self.agent.ranker._adapt(profile)
        self.assertNotIn("color", canonical.no_preference_attributes)
        self.assertTrue(any(c.attribute == "color" and c.value == "blue" for c in canonical.constraints))
        self.assertNotIn("red", " ".join(canonical.query_terms))

    def test_stats_follow_one_ranking_and_never_leak_into_payload(self):
        self.agent.reset("s", {})
        stats = {"pool_size": 100, "attributes": {
            "material": {"coverage": 1, "expected_remaining": 50, "question_value": .5},
            "budget": {"coverage": .1, "expected_remaining": 95, "question_value": .005},
        }}
        with patch.object(self.agent.ranker, "rank_with_stats", return_value=([{"parent_asin": "A"}], stats)) as search:
            response = self.agent.respond("s", "I need shoes.", 1, 10)
        search.assert_called_once()
        self.assertEqual(response["ask_attribute"], "material")
        self.assertEqual(set(response), {"message", "ask_attribute", "recommendations"})
        self.assertEqual(response["recommendations"], [{"parent_asin": "A"}])
        self.assertIn("material", self.agent.brain.sessions["s"].asked_attributes)

    def test_retry_is_idempotent_return_values_are_isolated_and_reset_clears(self):
        self.agent.reset("s", {"preference_tags": ["cotton"]})
        with patch.object(self.agent.ranker, "rank_with_stats", wraps=self.agent.ranker.rank_with_stats) as search:
            first = self.agent.respond("s", "I need shoes.", 1, 10)
            expected = copy.deepcopy(first)
            first["recommendations"].clear()
            second = self.agent.respond("s", "I need shoes.", 1, 10)
            self.assertEqual(second, expected)
            search.assert_called_once()
        self.assertEqual(len(self.agent.brain.sessions["s"].messages), 1)
        with self.assertRaises(ValueError):
            self.agent.respond("s", "Actually dresses", 1, 10)
        self.agent.reset("s", {})
        self.assertEqual(self.agent.brain.sessions["s"].messages, ())
        self.agent.respond("s", "I need dresses.", 1, 10)
        self.assertNotIn("shoes", " ".join(self.agent.brain.sessions["s"].query_terms))

    def test_interleaved_sessions_and_input_profile_do_not_alias(self):
        aggregate = {"preference_tags": ["cotton"]}
        self.agent.reset("a", aggregate)
        self.agent.reset("b", {})
        aggregate["preference_tags"].append("secret mutation")
        self.agent.respond("a", "red shoes", 1, 10)
        self.agent.respond("b", "blue dress", 1, 10)
        self.assertNotIn("dress", " ".join(self.agent.brain.sessions["a"].query_terms))
        self.assertNotIn("secret mutation", self.agent.brain.sessions["a"].user_profile["preference_tags"])
        self.assertNotIn("red", " ".join(self.agent.brain.sessions["b"].query_terms))

    def test_failed_search_does_not_commit_profile_or_asked_question(self):
        self.agent.reset("s", {})
        with patch.object(self.agent.ranker, "rank_with_stats", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError):
                self.agent.respond("s", "red shoes", 1, 10)
        self.assertEqual(self.agent.brain.sessions["s"].messages, ())
        self.assertEqual(self.agent.brain.sessions["s"].asked_attributes, frozenset())
        self.agent.respond("s", "red shoes", 1, 10)
        self.assertEqual(len(self.agent.brain.sessions["s"].messages), 1)

    def test_failed_composition_does_not_commit_question_or_profile(self):
        self.agent.reset("s", {})
        with patch.object(self.agent.composer, "compose", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError):
                self.agent.respond("s", "red shoes", 1, 10)
        self.assertEqual(self.agent.brain.sessions["s"].messages, ())
        self.assertEqual(self.agent.brain.sessions["s"].asked_attributes, frozenset())
        self.agent.respond("s", "red shoes", 1, 10)
        self.assertEqual(len(self.agent.brain.sessions["s"].messages), 1)


if __name__ == "__main__":
    unittest.main()
