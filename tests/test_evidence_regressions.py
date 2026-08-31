from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from starter.profile_adapter import ConstraintView
from starter.ranker import Ranker, constraint_relation


class EvidenceRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"parent_asin": "HYPHEN", "title": "Cotton-free polyester shoe"},
            {"parent_asin": "UNICODE_HYPHEN", "title": "Cotton\u2011free polyester shoe"},
            {"parent_asin": "SPACED", "title": "Cotton free polyester shoe"},
            {"parent_asin": "NO", "title": "Shoe", "features": ["No cotton", "100% polyester"]},
            {"parent_asin": "FULLWIDTH_NO", "title": "\uff2e\uff2f cotton; polyester shoe"},
            {"parent_asin": "WITHOUT", "title": "Shoe without cotton", "details": {"Material": "Polyester"}},
            {"parent_asin": "NOT", "title": "Not made with cotton; polyester shoe"},
            {"parent_asin": "NEGATED_ONLY", "title": "Cotton-free shoe"},
            {"parent_asin": "POSITIVE", "title": "Cotton running shoe"},
            {"parent_asin": "SHIPPING", "title": "Cotton free shipping"},
            {"parent_asin": "MIXED", "title": "Cotton shoe", "features": ["Cotton-free upper", "Polyester lining"]},
            {
                "parent_asin": "LATE",
                "title": "Running shoe",
                "features": ["Warranty information. " * 30 + "Soft cotton lining for comfort."],
            },
            {
                "parent_asin": "LATE_UNICODE",
                "title": "Running shoe",
                "description": ["Packaging information. " * 30 + "Caf\u00e9 d\u2019Or breathable COTTON lining."],
            },
            {
                "parent_asin": "LATE_CONFLICT",
                "title": "Running shoe",
                "details": {"Notes": "Warranty information. " * 30 + "100% polyester upper."},
            },
            {
                "parent_asin": "WIDE_SPAN",
                "title": "Running shoe",
                "description": ["Machine washable. " + "Packaging information. " * 30 + "Waterproof."],
            },
        ]
        serialized = "".join(json.dumps(row) + "\n" for row in self.rows)
        # All catalog data stays in memory; these regressions do not depend on
        # the downloaded official catalog or modify any evaluator artifacts.
        with patch.object(Path, "open", return_value=io.StringIO(serialized)):
            self.ranker = Ranker("in_memory_catalog.jsonl")

    def tearDown(self) -> None:
        self.ranker.close()

    def test_explicit_material_negations_are_not_affirmative_materials(self) -> None:
        exclusion = ConstraintView("material", "cotton", strength="hard", polarity="exclude")
        for parent_asin in ("HYPHEN", "UNICODE_HYPHEN", "SPACED", "NO", "FULLWIDTH_NO", "WITHOUT", "NOT"):
            with self.subTest(parent_asin=parent_asin):
                product = self.ranker.catalog.products[parent_asin]
                self.assertNotIn("cotton", product.materials)
                self.assertIn("polyester", product.materials)
                self.assertNotEqual(constraint_relation(product, exclusion), 1)
                self.assertNotIn(parent_asin, self.ranker.catalog.structured_ids["material"].get("cotton", []))

    def test_negated_only_metadata_remains_unknown(self) -> None:
        product = self.ranker.catalog.products["NEGATED_ONLY"]
        self.assertFalse(product.materials)
        self.assertEqual(constraint_relation(product, ConstraintView("material", "cotton")), 0)

    def test_actual_material_and_free_shipping_remain_positive(self) -> None:
        for parent_asin in ("POSITIVE", "SHIPPING"):
            with self.subTest(parent_asin=parent_asin):
                product = self.ranker.catalog.products[parent_asin]
                self.assertIn("cotton", product.materials)
                self.assertEqual(constraint_relation(product, ConstraintView("material", "cotton")), 1)

    def test_mixed_sign_mentions_preserve_uncertainty_and_unrelated_material(self) -> None:
        product = self.ranker.catalog.products["MIXED"]
        self.assertEqual(product.uncertain_materials, frozenset({"cotton"}))
        self.assertNotIn("cotton", product.materials)
        self.assertIn("polyester", product.materials)

    def test_negative_evidence_does_not_invent_cotton_violation(self) -> None:
        profile = {"hard_exclusions": [{"attribute": "material", "value": "cotton"}]}
        evidence = self.ranker.build_demo_evidence(
            profile, [{"parent_asin": "HYPHEN"}, {"parent_asin": "POSITIVE"}],
        )["products"]
        self.assertEqual(evidence["HYPHEN"]["conflicts"], [])
        self.assertEqual(evidence["POSITIVE"]["conflicts"][0]["reason"], "contains_excluded_value")

    def test_late_material_match_uses_local_verbatim_evidence(self) -> None:
        profile = {"constraints": [{"attribute": "material", "value": "cotton", "strength": "hard"}]}
        evidence = self.ranker.build_demo_evidence(profile, [{"parent_asin": "LATE"}])
        match = evidence["products"]["LATE"]["matched"][0]
        self.assertEqual(match["field"], "features")
        self.assertIn("cotton lining", match["snippet"])
        self.assertLessEqual(len(match["snippet"]), 240)
        self.assertIn(match["snippet"], self.ranker.catalog.products["LATE"].raw_field("features"))

    def test_late_unicode_match_preserves_original_source_spelling(self) -> None:
        profile = {"constraints": [{"attribute": "feature", "value": "Caf\u00e9 d'Or breathable cotton lining"}]}
        evidence = self.ranker.build_demo_evidence(profile, [{"parent_asin": "LATE_UNICODE"}])
        match = evidence["products"]["LATE_UNICODE"]["matched"][0]
        self.assertEqual(match["field"], "description")
        self.assertIn("Caf\u00e9 d\u2019Or breathable COTTON lining", match["snippet"])
        self.assertLessEqual(len(match["snippet"]), 240)

    def test_late_conflict_quotes_the_known_material(self) -> None:
        profile = {"constraints": [{"attribute": "material", "value": "cotton", "strength": "hard"}]}
        evidence = self.ranker.build_demo_evidence(profile, [{"parent_asin": "LATE_CONFLICT"}])
        conflict = evidence["products"]["LATE_CONFLICT"]["conflicts"][0]
        self.assertEqual(conflict["reason"], "known_structured_mismatch")
        self.assertIn("100% polyester", conflict["snippet"])
        self.assertLessEqual(len(conflict["snippet"]), 240)

    def test_partial_or_unquotable_match_is_not_presented_as_full_evidence(self) -> None:
        cases = (
            ("POSITIVE", "material", "100% cotton"),
            ("WIDE_SPAN", "feature", "machine washable waterproof"),
        )
        for parent_asin, attribute, value in cases:
            with self.subTest(parent_asin=parent_asin):
                profile = {"constraints": [{"attribute": attribute, "value": value}]}
                evidence = self.ranker.build_demo_evidence(profile, [{"parent_asin": parent_asin}])
                self.assertEqual(evidence["products"][parent_asin]["matched"], [])


if __name__ == "__main__":
    unittest.main()
