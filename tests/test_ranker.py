from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.conversation import ReferenceConversationBrain
from starter.profile_adapter import ConstraintView
from starter.ranker import Ranker, constraint_relation
from tests.test_retrieval import PRODUCTS


class RankerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "catalog.jsonl"
        self.path.write_text(
            "".join(json.dumps(product) + "\n" for product in PRODUCTS),
            encoding="utf-8",
        )
        self.ranker = Ranker(self.path)

    def tearDown(self) -> None:
        self.ranker.close()
        self.directory.cleanup()

    def test_hard_match_ranks_first_and_output_is_valid_unique(self) -> None:
        profile = {
            "category": "shoes",
            "query_terms": ["cotton running shoe"],
            "constraints": [
                {
                    "attribute": "material",
                    "value": "100% cotton",
                    "strength": "hard",
                    "polarity": "include",
                    "confidence": 1.0,
                    "active": True,
                }
            ],
        }
        result = self.ranker.rank(profile, top_k=10)
        self.assertEqual(result[0]["parent_asin"], "A")
        ids = [item["parent_asin"] for item in result]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(ids) <= self.ranker.catalog.valid_ids)
        self.assertLessEqual(len(ids), 10)

    def test_inactive_override_constraint_does_not_control_ranking(self) -> None:
        profile = {
            "category": "boots",
            "query_terms": ["black leather winter boot"],
            "constraints": [
                {"attribute": "material", "value": "cotton", "strength": "hard", "active": False},
                {"attribute": "material", "value": "leather", "strength": "hard", "active": True},
            ],
        }
        self.assertEqual(self.ranker.rank(profile)[0]["parent_asin"], "B")

    def test_missing_price_is_unknown_not_contradiction(self) -> None:
        profile = {
            "category": "dresses",
            "query_terms": ["red polyester dress"],
            "constraints": [
                {"attribute": "budget", "value": "under 100", "strength": "hard", "active": True}
            ],
        }
        self.assertEqual(self.ranker.rank(profile)[0]["parent_asin"], "C")

    def test_attribute_stats_excludes_no_preference(self) -> None:
        profile = {
            "query_terms": ["women clothing"],
            "constraints": [],
            "no_preference_attributes": {"color"},
            "exhausted_attributes": {"brand"},
        }
        stats = self.ranker.attribute_stats(profile, candidate_limit=3)
        self.assertEqual(stats["pool_size"], 3)
        self.assertNotIn("color", stats["attributes"])
        self.assertNotIn("brand", stats["attributes"])
        self.assertIn("category", stats["attributes"])

    def test_demo_evidence_is_separate_and_factual(self) -> None:
        profile = {
            "query_terms": ["cotton shoe"],
            "constraints": [
                {"attribute": "material", "value": "cotton", "strength": "hard", "active": True}
            ],
        }
        ranked = self.ranker.rank(profile, top_k=1)
        evidence = self.ranker.build_demo_evidence(profile, ranked)
        self.assertIn("A", evidence["products"])
        self.assertEqual(evidence["products"]["A"]["matched"][0]["field"], "title")

    def test_override_drops_old_free_text_but_keeps_confirmed_constraints(self) -> None:
        brain = ReferenceConversationBrain()
        brain.reset("session", {"preference_tags": []})
        brain.update(
            "session",
            "I'm looking for Shoes Slippers. I used to prefer a plush closure.",
            1,
        )
        brain.update(
            "session",
            "For that, what matters is: Rubber sole; Textile upper.",
            2,
        )
        update = brain.update(
            "session",
            "Actually, ignore my earlier preference. What I need is: Rubber sole.",
            3,
        )
        profile = update.profile
        active_terms = " ".join(profile["query_terms"]).lower()
        self.assertNotIn("plush closure", active_terms)
        self.assertIn("textile upper", active_terms)
        self.assertIn("rubber sole", active_terms)

    def test_unstructured_hard_absence_is_unknown(self) -> None:
        product = self.ranker.catalog.products["B"]
        constraint = ConstraintView("feature", "machine washable", strength="hard")
        self.assertEqual(constraint_relation(product, constraint), 0)

    def test_budget_symbols_survive_and_are_enforced(self) -> None:
        under = ConstraintView("budget", "< $60", strength="hard")
        over = ConstraintView("budget", ">= 60", strength="hard")
        self.assertEqual(constraint_relation(self.ranker.catalog.products["A"], under), 1)
        self.assertEqual(constraint_relation(self.ranker.catalog.products["B"], under), -1)
        self.assertEqual(constraint_relation(self.ranker.catalog.products["B"], over), 1)

    def test_negative_evidence_marks_only_verified_violation(self) -> None:
        profile = {
            "query_terms": ["shoe"],
            "negative_constraints": [
                {"attribute": "material", "value": "cotton", "constraint_id": "avoid-cotton"}
            ],
        }
        ranked = [{"parent_asin": "A"}, {"parent_asin": "B"}]
        evidence = self.ranker.build_demo_evidence(profile, ranked)
        self.assertEqual(
            evidence["products"]["A"]["conflicts"][0]["reason"],
            "contains_excluded_value",
        )
        self.assertEqual(evidence["products"]["B"]["conflicts"], [])

    def test_explicit_negative_is_not_reintroduced_by_fallback(self) -> None:
        profile = {
            "query_terms": ["women clothing"],
            "negative_constraints": [{"attribute": "material", "value": "cotton"}],
        }
        identifiers = [item["parent_asin"] for item in self.ranker.rank(profile)]
        self.assertNotIn("A", identifiers)
        self.assertEqual(set(identifiers), {"B", "C"})

    def test_soft_preference_boosts_but_never_eliminates(self) -> None:
        profile = {
            "query_terms": ["women clothing"],
            "soft_preferences": [{"attribute": "material", "value": "leather"}],
        }
        identifiers = [item["parent_asin"] for item in self.ranker.rank(profile)]
        self.assertEqual(identifiers[0], "B")
        self.assertEqual(set(identifiers), {"A", "B", "C"})

    def test_empty_query_and_detailed_ranking_are_deterministic(self) -> None:
        first = self.ranker.rank({}, top_k=10)
        second = self.ranker.rank({}, top_k=10)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        detailed = self.ranker.rank_detailed({}, top_k=2)
        self.assertEqual(len(detailed.recommendations), 2)
        self.assertGreaterEqual(detailed.candidate_pool_size, 1)

    def test_budget_stats_use_coverage_and_ranges_not_exact_prices(self) -> None:
        stats = self.ranker.attribute_stats({"query_terms": ["women"]}, candidate_limit=3)
        budget = stats["attributes"]["budget"]
        self.assertEqual(budget["coverage"], 0.666667)
        values = {item[0] for item in budget["top_values"]}
        self.assertEqual(values, {"25 to 50", "50 to 100"})


if __name__ == "__main__":
    unittest.main()
