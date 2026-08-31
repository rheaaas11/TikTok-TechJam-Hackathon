from __future__ import annotations

import unittest

from starter.budget import budget_relation, parse_budget
from starter.profile_adapter import DefaultProfileAdapter


class ProfileRegressionTest(unittest.TestCase):
    def test_mapped_unordered_constraint_values_have_canonical_order(self) -> None:
        for values in ({"silk", "cotton", "linen"}, frozenset({"silk", "cotton", "linen"})):
            with self.subTest(container=type(values).__name__):
                profile = self.adapter.adapt({"hard_constraints": {"material": values}})
                self.assertEqual([constraint.value for constraint in profile.constraints],
                                 ["cotton", "linen", "silk"])

    def setUp(self) -> None:
        self.adapter = DefaultProfileAdapter()

    def test_single_constraint_mapping_is_one_record(self) -> None:
        profile = self.adapter.adapt({
            "hard_constraints": {"attribute": "material", "value": "cotton"},
        })
        self.assertEqual([(c.attribute, c.value, c.strength) for c in profile.constraints],
                         [("material", "cotton", "hard")])

    def test_active_snapshot_does_not_merge_legacy_intent(self) -> None:
        profile = self.adapter.adapt({
            "category": "shoes", "mission": "old cotton shoes", "query_terms": ["red cotton"],
            "constraints": [{"attribute": "color", "value": "red"}],
            "active_state": {"category": "dresses", "constraints": [
                {"attribute": "color", "value": "blue"},
            ]},
        })
        self.assertEqual(profile.category, "dresses")
        self.assertEqual(profile.mission, "")
        self.assertEqual(profile.query_terms, ())
        self.assertEqual([(c.attribute, c.value) for c in profile.constraints], [("color", "blue")])

    def test_empty_active_constraints_clear_legacy_collections(self) -> None:
        profile = self.adapter.adapt({
            "active_constraints": [],
            "constraints": [{"attribute": "material", "value": "cotton"}],
            "hard_constraints": {"color": "red"},
        })
        self.assertEqual(profile.constraints, ())

    def test_numeric_budget_operator_is_not_polarity(self) -> None:
        profile = self.adapter.adapt({"constraints": [
            {"attribute": "budget", "value": 60, "operator": "<=", "strength": "hard"},
        ]})
        self.assertEqual(profile.constraints[0].value, "<= 60")
        self.assertEqual(profile.constraints[0].polarity, "include")

    def test_complete_compatible_budget_expression_is_not_double_prefixed(self) -> None:
        cases = (
            ("<=", "<= 60"),
            ("lte", "under 60"),
            (">=", "over 60"),
            ("gt", "> 60"),
            ("eq", "exactly 60"),
            ("range", "between 20 and 60"),
            ("\u2264", "at most 60"),
        )
        for operator, value in cases:
            with self.subTest(operator=operator, value=value):
                profile = self.adapter.adapt({"hard_constraints": [
                    {"attribute": "budget", "value": value, "operator": operator},
                ]})
                self.assertEqual(profile.constraints[0].value, value)
                self.assertIsNotNone(parse_budget(profile.constraints[0].value))
                self.assertEqual(parse_budget(profile.constraints[0].value), parse_budget(value))

    def test_conflicting_budget_operator_and_expression_remain_unknown(self) -> None:
        cases = (
            ("<=", ">= 60"),
            (">=", "under 60"),
            ("<", "at most 60"),
            (">", "at least 60"),
            ("=", "under 60"),
            ("between", "60"),
        )
        for operator, value in cases:
            with self.subTest(operator=operator, value=value):
                profile = self.adapter.adapt({"hard_constraints": [
                    {"attribute": "budget", "value": value, "operator": operator},
                ]})
                constraint = profile.constraints[0]
                self.assertIsNone(parse_budget(constraint.value))
                self.assertEqual([budget_relation(price, constraint.value) for price in (20, 60, 100)], [0, 0, 0])

    def test_nested_budget_expression_preserves_strict_endpoint(self) -> None:
        profile = self.adapter.adapt({"hard_constraints": [
            {"attribute": "budget", "value": {"amount": "under 60", "operator": "lte"}},
        ]})
        self.assertEqual(profile.constraints[0].value, "under 60")
        self.assertEqual(budget_relation(59, profile.constraints[0].value), 1)
        self.assertEqual(budget_relation(60, profile.constraints[0].value), -1)

    def test_budget_dictionary_preserves_range(self) -> None:
        profile = self.adapter.adapt({"hard_constraints": {"budget": {"min": 20, "max": 60}}})
        self.assertEqual(profile.constraints[0].value, ">= 20 and <= 60")

    def test_budget_bounds_with_same_number_do_not_deduplicate(self) -> None:
        profile = self.adapter.adapt({"constraints": [
            {"attribute": "budget", "value": 60, "operator": ">="},
            {"attribute": "budget", "value": 60, "operator": "<="},
        ]})
        self.assertEqual(len(profile.constraints), 2)

    def test_legacy_exclusion_operator_still_works(self) -> None:
        profile = self.adapter.adapt({"constraints": [
            {"attribute": "material", "value": "cotton", "operator": "exclude"},
        ]})
        self.assertEqual(profile.constraints[0].polarity, "exclude")

    def test_invalid_confidence_cannot_become_high_confidence(self) -> None:
        for confidence in ("unknown", float("nan"), float("inf")):
            with self.subTest(confidence=confidence):
                profile = self.adapter.adapt({"constraints": [
                    {"attribute": "material", "value": "cotton", "confidence": confidence},
                ]})
                self.assertEqual(profile.constraints[0].confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
