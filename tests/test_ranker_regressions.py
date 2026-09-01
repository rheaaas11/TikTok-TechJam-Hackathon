from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from starter.ranker import Ranker
from tests.test_retrieval import PRODUCTS


class RankerRegressionTest(unittest.TestCase):
    def test_combined_handoff_reuses_one_search_and_matches_separate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.jsonl"
            path.write_text("".join(json.dumps(p) + "\n" for p in PRODUCTS), encoding="utf-8")
            ranker = Ranker(path)
            profile = {"category": "shoes", "query_terms": ["cotton shoe"]}
            try:
                expected_products = ranker.rank(profile)
                expected_stats = ranker.attribute_stats(profile)
                with patch.object(ranker, "_ranked_candidates", wraps=ranker._ranked_candidates) as search:
                    products, stats = ranker.rank_with_stats(profile)
                    self.assertEqual(search.call_count, 1)
                self.assertEqual(products, expected_products)
                self.assertEqual(stats, expected_stats)
            finally:
                ranker.close()

    def test_soft_exclusion_penalizes_without_eliminating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.jsonl"
            path.write_text("".join(json.dumps(p) + "\n" for p in PRODUCTS), encoding="utf-8")
            ranker = Ranker(path)
            try:
                result = ranker.rank({"query_terms": ["women clothing"], "constraints": [
                    {"attribute": "material", "value": "cotton", "strength": "soft",
                     "polarity": "exclude", "confidence": 1.0},
                ]})
                identifiers = [p["parent_asin"] for p in result]
                self.assertEqual(set(identifiers), {"A", "B", "C"})
                self.assertNotEqual(identifiers[0], "A")
            finally:
                ranker.close()

    def test_unknown_metadata_is_retained_in_question_estimate(self) -> None:
        products = {
            str(i): SimpleNamespace(attribute_values=lambda attribute, known=i < 10:
                                   ("cotton",) if attribute == "material" and known else ())
            for i in range(100)
        }
        ranker = Ranker.__new__(Ranker)
        ranker.catalog = SimpleNamespace(products=products)
        ranker._adapt = lambda profile: SimpleNamespace(
            asked_attributes=set(), no_preference_attributes=set(), exhausted_attributes=set())
        ranker._ranked_candidates = lambda *args, **kwargs: list(products)
        material = ranker.attribute_stats({})["attributes"]["material"]
        self.assertEqual(material["coverage"], 0.1)
        self.assertEqual(material["expected_remaining"], 100.0)
        self.assertEqual(material["question_value"], 0.0)

    def test_ambiguous_material_survives_its_specific_answer(self) -> None:
        products = {
            str(i): SimpleNamespace(
                attribute_values=lambda attribute, value="polyester" if i < 2 else "cotton":
                    (value,) if attribute == "material" else (),
                uncertain_materials=frozenset({"cotton"}) if i < 2 else frozenset(),
            )
            for i in range(4)
        }
        ranker = Ranker.__new__(Ranker)
        ranker.catalog = SimpleNamespace(products=products)
        ranker._adapt = lambda profile: SimpleNamespace(
            asked_attributes=set(), no_preference_attributes=set(), exhausted_attributes=set())
        ranker._ranked_candidates = lambda *args, **kwargs: list(products)
        material = ranker.attribute_stats({})["attributes"]["material"]
        self.assertEqual(material["coverage"], 1.0)
        self.assertEqual(material["expected_remaining"], 3.0)
        self.assertEqual(material["question_value"], 0.25)


if __name__ == "__main__":
    unittest.main()
