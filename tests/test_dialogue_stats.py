from __future__ import annotations

from dataclasses import replace
import unittest

from src.dialogue import choose_ask_attribute, decide_next_turn, process_message
from src.profile import Constraint, new_profile, update_profile


def metrics(coverage=1.0, remaining=50.0, value=0.5):
    return {"coverage": coverage, "expected_remaining": remaining,
            "question_value": value, "top_values": [["not a complete distribution", 1]]}


class DialogueStatisticsTest(unittest.TestCase):
    def test_direct_leon_statistics_selects_useful_attribute(self):
        profile = update_profile(new_profile("s", {}), "I need shoes", 1)
        decision = decide_next_turn(profile, candidate_statistics={"pool_size": 100, "attributes": {
            "color": metrics(), "material": metrics(0.1, 95, 0.005),
        }})
        self.assertEqual(decision.ask_attribute, "color")
        self.assertEqual(decision.question_value, 0.5)

    def test_statistics_can_ask_after_three_details(self):
        profile = update_profile(new_profile("s", {}), "White leather boots under 80", 1)
        self.assertIsNone(decide_next_turn(profile).ask_attribute)
        decision = decide_next_turn(profile, candidate_statistics={"pool_size": 100, "attributes": {"size": metrics()}})
        self.assertEqual(decision.ask_attribute, "size")

    def test_no_covered_question_can_fall_back_to_other_once(self):
        profile = update_profile(new_profile("s", {}), "White leather boots under 80", 1)
        decision = decide_next_turn(profile, candidate_statistics={"pool_size": 100, "attributes": {}})
        self.assertEqual(decision.ask_attribute, "other")
        self.assertIsNone(decide_next_turn(decision.updated_profile, candidate_statistics={"pool_size": 100, "attributes": {}}).ask_attribute)

    def test_missing_products_survive_even_an_overoptimistic_summary(self):
        profile = update_profile(new_profile("s", {}), "Shoes", 1)
        decision = decide_next_turn(profile, candidate_statistics={"pool_size": 100, "attributes": {
            "color": metrics(0.1, 0, 1), "material": metrics(1, 80, 0.2),
        }})
        self.assertEqual(decision.ask_attribute, "material")
        self.assertAlmostEqual(decision.question_value, 0.2)

    def test_all_unavailable_slots_are_excluded(self):
        profile = replace(new_profile("s", {}), asked_attributes=frozenset({"category", "color"}),
                          no_preference_attributes=frozenset({"budget"}), exhausted_attributes=frozenset({"material"}))
        statistics = {"pool_size": 100, "attributes": {attribute: metrics() for attribute in ("category", "color", "budget", "material", "size")}}
        self.assertEqual(choose_ask_attribute(profile, candidate_statistics=statistics)[0], "size")

    def test_invalid_count_shapes_never_raise_or_gain_utility(self):
        for counts in ([], {"a": True, "b": 1}, {"a": -1, "b": 1}, {"a": float("nan")}, {"top_values": [["x", 1]]}):
            with self.subTest(counts=counts):
                decision = decide_next_turn(new_profile("s", {}), {"color": counts})
                self.assertIsNone(decision.question_value)

    def test_invalid_statistics_never_raise(self):
        for statistics in ([], {"pool_size": True}, {"pool_size": float("inf"), "attributes": {}},
                           {"pool_size": 100, "attributes": {"color": metrics(value=float("nan"))}},
                           {"pool_size": 100, "attributes": {"color": metrics(coverage=-1)}}):
            with self.subTest(statistics=statistics):
                self.assertIsNone(decide_next_turn(new_profile("s", {}), candidate_statistics=statistics).question_value)

    def test_statistics_take_precedence_over_legacy_counts(self):
        decision = process_message(new_profile("s", {}), "Shoes", 1,
            {"color": {"red": 50, "blue": 50}},
            candidate_statistics={"pool_size": 100, "attributes": {"material": metrics()}})
        self.assertEqual(decision.ask_attribute, "material")

    def test_fixed_priority_never_cycles_back_to_asked_slots(self):
        profile = new_profile("s", {})
        seen = set()
        for _ in range(12):
            decision = decide_next_turn(profile)
            if decision.ask_attribute is not None:
                self.assertNotIn(decision.ask_attribute, seen)
                seen.add(decision.ask_attribute)
            profile = decision.updated_profile
        self.assertIsNone(decision.ask_attribute)

    def test_unproductive_narrow_answer_broadens_before_more_diversity_questions(self):
        statistics = {"pool_size": 100, "attributes": {
            "brand": metrics(1, 10, .9), "material": metrics(), "color": metrics(),
        }}
        first = process_message(new_profile("s", {}), "Shoes", 1, candidate_statistics=statistics)
        self.assertEqual(first.ask_attribute, "brand")
        second = process_message(first.updated_profile,
                                 "I don't have an additional preference for brand.", 2,
                                 candidate_statistics=statistics)
        self.assertEqual(second.ask_attribute, "other")
        self.assertIn("brand", second.updated_profile.exhausted_attributes)

    def test_productive_other_answer_can_request_more_than_one_batch(self):
        statistics = {"pool_size": 100, "attributes": {}}
        profile = update_profile(new_profile("s", {}), "White leather boots under 80", 1)
        first = decide_next_turn(profile, candidate_statistics=statistics)
        self.assertEqual(first.ask_attribute, "other")
        answered = replace(first.updated_profile, turn=2, constraints=first.updated_profile.constraints + (
            Constraint("other", "pearlescent asymmetric lunar applique", "soft", "include", 2),
        ))
        second = decide_next_turn(answered, candidate_statistics=statistics)
        self.assertEqual(second.ask_attribute, "other")
        # A second call is not a second answer, even when `other` has content.
        self.assertIsNone(decide_next_turn(second.updated_profile, candidate_statistics=statistics).ask_attribute)

    def test_reworded_or_deactivated_information_does_not_unlock_repeat_other(self):
        statistics = {"pool_size": 100, "attributes": {}}
        first = decide_next_turn(update_profile(new_profile("s", {}), "White leather boots under 80", 1),
                                 candidate_statistics=statistics)
        unchanged = replace(first.updated_profile, turn=2,
                            constraints=tuple(replace(c, source_turn=2) for c in first.updated_profile.constraints))
        self.assertNotEqual(decide_next_turn(unchanged, candidate_statistics=statistics).ask_attribute, "other")
        removed = replace(first.updated_profile, turn=2,
                          constraints=tuple(replace(c, active=False) for c in first.updated_profile.constraints))
        self.assertNotEqual(decide_next_turn(removed, candidate_statistics=statistics).ask_attribute, "other")

    def test_explicit_other_exhaustion_or_no_preference_beats_new_information(self):
        statistics = {"pool_size": 100, "attributes": {"size": metrics()}}
        first = decide_next_turn(update_profile(new_profile("s", {}), "White leather boots under 80", 1),
                                 candidate_statistics={"pool_size": 100, "attributes": {}})
        for flag in ("exhausted_attributes", "no_preference_attributes"):
            with self.subTest(flag=flag):
                answered = replace(first.updated_profile, turn=2,
                                   constraints=first.updated_profile.constraints + (
                                       Constraint("feature", "rare trim", "soft", "include", 2),
                                   ), **{flag: frozenset({"other"})})
                self.assertEqual(decide_next_turn(answered, candidate_statistics=statistics).ask_attribute, "size")

    def test_existing_other_constraint_does_not_hide_first_broad_clarification(self):
        profile = replace(update_profile(new_profile("s", {}), "White leather boots under 80", 1),
                          constraints=(Constraint("color", "white", "soft", "include", 1),
                                       Constraint("material", "leather", "soft", "include", 1),
                                       Constraint("other", "rare trim", "soft", "include", 1)))
        self.assertEqual(decide_next_turn(profile, candidate_statistics={"pool_size": 100, "attributes": {}}).ask_attribute,
                         "other")

    def test_unproductive_broad_reply_falls_back_without_repeating_specific_questions(self):
        statistics = {"pool_size": 100, "attributes": {}}
        first = decide_next_turn(update_profile(new_profile("s", {}), "White leather boots under 80", 1),
                                 candidate_statistics=statistics)
        answered = update_profile(first.updated_profile, "I don't have an additional preference for other.", 2)
        next_question = decide_next_turn(answered, candidate_statistics=statistics)
        self.assertIsNotNone(next_question.ask_attribute)
        self.assertNotEqual(next_question.ask_attribute, "other")
        third = update_profile(next_question.updated_profile,
                               "I don't have an additional preference for " + next_question.ask_attribute + ".", 3)
        later = decide_next_turn(third, candidate_statistics=statistics)
        self.assertNotIn(later.ask_attribute, {"other", next_question.ask_attribute})


if __name__ == "__main__":
    unittest.main()
