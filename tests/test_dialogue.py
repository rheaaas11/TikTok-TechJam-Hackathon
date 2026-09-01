from __future__ import annotations

import unittest

from src.dialogue import process_message
from src.profile import ALLOWED_ASK_ATTRIBUTES, new_profile


class DialogueTest(unittest.TestCase):
    def test_vague_browsing_request_asks_a_useful_allowed_question(self) -> None:
        decision = process_message(new_profile("session", {}), "I'm looking for something nice but still exploring.", 1)
        self.assertTrue(decision.should_ask)
        self.assertIn(decision.ask_attribute, ALLOWED_ASK_ATTRIBUTES)
        self.assertEqual(decision.ask_attribute, "category")

    def test_detailed_request_stops_asking(self) -> None:
        decision = process_message(
            new_profile("session", {}),
            "I need white leather ankle boots, size 8, under $80 for winter.",
            1,
        )
        self.assertFalse(decision.should_ask)
        self.assertIsNone(decision.ask_attribute)

    def test_boundary_reply_prevents_repeated_question(self) -> None:
        profile = new_profile("session", {})
        first = process_message(profile, "I need shoes.", 1)
        second = process_message(first.updated_profile, "I don't have a preference for budget.", 2)
        self.assertNotEqual(second.ask_attribute, "budget")
        self.assertIn("budget", second.updated_profile.no_preference_attributes)

    def test_v2_uses_leon_candidate_evidence_to_choose_a_question(self) -> None:
        decision = process_message(
            new_profile("session", {}),
            "I need shoes.",
            1,
            candidate_attribute_counts={
                "budget": {"under 50": 90, "50 to 100": 10},
                "color": {"black": 50, "white": 50},
            },
        )
        self.assertEqual(decision.ask_attribute, "color")
        self.assertEqual(decision.question_value, 0.5)


if __name__ == "__main__":
    unittest.main()
