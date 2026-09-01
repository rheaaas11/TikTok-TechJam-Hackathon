from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from starter.agent import Agent, OfficialResponseComposer
from starter.conversation import ReferenceConversationBrain, StateUpdate
from tests.test_retrieval import PRODUCTS


class IntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.catalog_path = Path(self.directory.name) / "catalog.jsonl"
        self.catalog_path.write_text(
            "".join(json.dumps(product) + "\n" for product in PRODUCTS),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_paraphrased_override_supersedes_closed_slot(self) -> None:
        brain = ReferenceConversationBrain()
        brain.reset("s", {})
        brain.update("s", "I'm looking for winter boots.", 1)
        brain.update("s", "For that, what matters is: cotton.", 2)
        update = brain.update("s", "Actually, switch the material from cotton to leather.", 3)
        active = [item for item in update.profile["constraints"] if item["active"]]
        self.assertEqual([(item["attribute"], item["value"]) for item in active], [("material", "leather")])
        self.assertNotIn("cotton", " ".join(update.profile["query_terms"]).lower())
        self.assertIn("leather", " ".join(update.profile["query_terms"]).lower())

    def test_no_preference_differs_from_no_additional_preference(self) -> None:
        brain = ReferenceConversationBrain()
        brain.reset("plain", {})
        brain.update("plain", "For that, what matters is: color: red.", 1)
        plain = brain.update("plain", "I don't have a preference for color; use your judgment.", 2)
        self.assertIn("color", plain.profile["no_preference_attributes"])
        self.assertFalse(plain.profile["constraints"][0]["active"])

        brain.reset("additional", {})
        brain.update("additional", "For that, what matters is: color: red.", 1)
        additional = brain.update("additional", "I don't have an additional preference for color.", 2)
        self.assertNotIn("color", additional.profile["no_preference_attributes"])
        self.assertIn("color", additional.profile["exhausted_attributes"])
        self.assertTrue(additional.profile["constraints"][0]["active"])

    def test_repeated_turn_is_idempotent_and_sessions_are_isolated(self) -> None:
        brain = ReferenceConversationBrain()
        brain.reset("a", {})
        brain.reset("b", {})
        first = brain.update("a", "I'm looking for shoes.", 1)
        duplicate = brain.update("a", "I'm looking for shoes.", 1)
        brain.update("b", "I'm looking for dresses.", 1)
        self.assertEqual(first.profile["query_terms"], duplicate.profile["query_terms"])
        self.assertEqual(len(duplicate.profile["free_terms"]), 1)
        self.assertEqual(brain.sessions["a"]["category"], "shoes")
        self.assertEqual(brain.sessions["b"]["category"], "dresses")

    def test_agent_dependencies_are_injectable_and_payload_is_allowlisted(self) -> None:
        class Brain:
            def reset(self, session_id: str, user_profile: dict) -> None:
                self.was_reset = (session_id, user_profile)

            def update(self, session_id: str, user_message: str, turn: int) -> StateUpdate:
                return StateUpdate(object(), "question", "material")

        class Backend:
            def rank(self, profile: object, top_k: int = 10) -> list[dict[str, str]]:
                self.received = (profile, top_k)
                return [
                    {"parent_asin": "A", "score": 99, "evidence": "must not leak"},
                    {"parent_asin": "A"},
                    {"parent_asin": "B"},
                ]

        brain = Brain()
        backend = Backend()
        agent = Agent(None, brain=brain, ranker=backend, composer=OfficialResponseComposer())
        agent.reset("s", {"summary": "x"})
        response = agent.respond("s", "hello", 1, 10)
        self.assertEqual(set(response), {"message", "ask_attribute", "recommendations"})
        self.assertEqual(response["recommendations"], [{"parent_asin": "A"}, {"parent_asin": "B"}])
        self.assertNotIn("evidence", str(response))

    def test_two_interleaved_agent_sessions_rank_independently(self) -> None:
        agent = Agent(self.catalog_path)
        agent.reset("shoe", {})
        agent.reset("dress", {})
        shoe = agent.respond("shoe", "I'm looking for shoes. A key requirement is: cotton.", 1, 10)
        dress = agent.respond("dress", "I'm looking for dresses. A key requirement is: polyester.", 1, 10)
        self.assertEqual(shoe["recommendations"][0]["parent_asin"], "A")
        self.assertEqual(dress["recommendations"][0]["parent_asin"], "C")
        agent.close()

    def test_shared_ranker_serializes_sqlite_across_threads(self) -> None:
        agent = Agent(self.catalog_path)
        profiles = [
            {"query_terms": ["cotton running shoe"]},
            {"query_terms": ["leather winter boot"]},
            {"query_terms": ["red polyester dress"]},
        ]
        with ThreadPoolExecutor(max_workers=3) as executor:
            outputs = list(executor.map(agent.ranker.rank, profiles * 4))
        self.assertEqual(len(outputs), 12)
        self.assertTrue(all(output and output[0]["parent_asin"] in {"A", "B", "C"} for output in outputs))
        agent.close()


if __name__ == "__main__":
    unittest.main()
