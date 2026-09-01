from __future__ import annotations

import copy
import unittest

from starter.agent import Agent, OfficialResponseComposer
from starter.conversation import StateUpdate


class ContractTest(unittest.TestCase):
    def test_official_response_contains_only_allowed_fields(self) -> None:
        response = OfficialResponseComposer().compose(
            StateUpdate(profile={}, message="Any color preference?", ask_attribute="color"),
            [
                {"parent_asin": "A", "score": 2.5, "debug": "do not expose"},
                {"parent_asin": "A"},
                {"parent_asin": "B", "score": 1.0},
                {"parent_asin": ""},
                {"not_parent_asin": "C"},
            ],
        )

        self.assertEqual(set(response), {"message", "ask_attribute", "recommendations"})
        self.assertEqual(response["message"], "Any color preference?")
        self.assertEqual(response["ask_attribute"], "color")
        self.assertEqual(response["recommendations"], [{"parent_asin": "A"}, {"parent_asin": "B"}])
        self.assertNotIn("debug", repr(response))
        self.assertNotIn("score", repr(response))

    def test_invalid_ask_attribute_is_normalized_to_null(self) -> None:
        response = OfficialResponseComposer().compose(
            StateUpdate(profile={}, message="Tell me more.", ask_attribute="private_debug_field"),
            [{"parent_asin": "A"}],
        )

        self.assertIsNone(response["ask_attribute"])

    def test_agent_requires_reset_and_monotonic_turns(self) -> None:
        class Brain:
            def reset(self, session_id: str, user_profile: dict) -> None:
                self.profile = copy.deepcopy(user_profile)

            def update(self, session_id: str, user_message: str, turn: int) -> StateUpdate:
                return StateUpdate(profile={"query_terms": [user_message]}, message="Question?", ask_attribute=None)

        class Ranker:
            def rank(self, profile: object, top_k: int = 10) -> list[dict[str, str]]:
                return [{"parent_asin": f"P{i}"} for i in range(top_k + 2)]

        agent = Agent(None, brain=Brain(), ranker=Ranker())

        with self.assertRaisesRegex(RuntimeError, "reset"):
            agent.respond("s", "shoes", 1, 10)

        agent.reset("s", {"summary": "likes practical shoes"})
        first = agent.respond("s", "shoes", 1, 10)
        duplicate = agent.respond("s", "shoes", 1, 10)
        self.assertEqual(first, duplicate)
        self.assertEqual(len(first["recommendations"]), 10)

        with self.assertRaisesRegex(ValueError, "cannot be replaced"):
            agent.respond("s", "different", 1, 10)
        with self.assertRaisesRegex(ValueError, "between 1 and 10"):
            agent.respond("s", "next", 11, 10)


if __name__ == "__main__":
    unittest.main()
