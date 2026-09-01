from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from starter.budget import budget_relation, parse_budget
from starter.catalog import CatalogIndex
from starter.profile_adapter import ConstraintView, NormalizedShopperProfile
from starter.ranker import Ranker
from starter.retrieval import CandidateRetriever


class BudgetRelationTest(unittest.TestCase):
    def test_comparison_endpoints_are_explicit(self) -> None:
        for value, below, equal, above in (
            ("< 60", 1, -1, -1), ("<= 60", 1, 1, -1),
            ("> 60", -1, -1, 1), (">= 60", -1, 1, 1),
            ("= 60", -1, 1, -1), ("under $60", 1, -1, -1),
            ("at most 60 USD", 1, 1, -1), ("at least 60", -1, 1, 1),
        ):
            with self.subTest(value=value):
                self.assertEqual([budget_relation(price, value) for price in (59, 60, 61)],
                                 [below, equal, above])

    def test_ranges_and_conjunction_preserve_both_endpoints(self) -> None:
        for value in ("between 20 and 60", "$20 to $60", "20–60", "from 20 to 60"):
            with self.subTest(value=value):
                self.assertEqual([budget_relation(price, value) for price in (19, 20, 60, 61)],
                                 [-1, 1, 1, -1])
        self.assertEqual([budget_relation(price, ">= 20 and < 60") for price in (19, 20, 59, 60)],
                         [-1, 1, 1, -1])
        self.assertEqual([budget_relation(price, "> 20 and <= 60") for price in (20, 21, 60, 61)],
                         [-1, 1, 1, -1])

    def test_catalog_bucket_and_usd_representations(self) -> None:
        self.assertEqual(budget_relation(200, "200 and above"), 1)
        self.assertEqual(budget_relation(199, "200 and above"), -1)
        self.assertEqual(budget_relation(50, "25 to 50"), 1)
        for value in ("USD <= 60", "budget: <= $60", "price ≤ 60", "up to USD 60"):
            with self.subTest(value=value):
                self.assertEqual(budget_relation(60, value), 1)
                self.assertEqual(budget_relation(61, value), -1)
        self.assertEqual(budget_relation(1200, "<= $1,200.00"), 1)
        self.assertEqual(budget_relation(1201, "<= $1,200.00"), -1)

    def test_legacy_approximation_is_documented_and_explicit_equality_is_not_approximate(self) -> None:
        for value in ("60", "about $60", "budget around $60"):
            self.assertEqual(budget_relation(45, value), 1)
            self.assertEqual(budget_relation(75, value), 1)
            self.assertEqual(budget_relation(76, value), -1)
        self.assertEqual(budget_relation(5, "around 10"), 1)
        self.assertEqual(budget_relation(59, "= 60"), -1)

    def test_unsupported_or_missing_evidence_is_unknown(self) -> None:
        for value in ("cheap", "under", "SGD <= 60", "<= EUR 60", "£60",
                      "under 30 or over 100", "60 plus 10 shipping", "60 per month",
                      ">= 60 and < 20", "between 60 and 20", "<= -1", "NaN"):
            with self.subTest(value=value):
                self.assertIsNone(parse_budget(value))
                self.assertEqual(budget_relation(500, value), 0)
        for price in (None, math.nan, math.inf, -1, True):
            with self.subTest(price=price):
                self.assertEqual(budget_relation(price, "under 30"), 0)


def _product(parent_asin: str, price: float | None, *, category: str = "Shoes",
             popularity: int = 1000) -> dict:
    return {
        "parent_asin": parent_asin,
        "title": f"Classic training {category.lower()}",
        "features": [], "details": {}, "description": [],
        "categories": ["Clothing", category], "store": "Example",
        "price": price, "average_rating": 4.5, "rating_number": popularity,
    }


class NumericBudgetRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "catalog.jsonl"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _write_products(self, products: list[dict]) -> None:
        self.path.write_text("".join(json.dumps(product) + "\n" for product in products),
                             encoding="utf-8")

    @staticmethod
    def _profile(value: str, *, polarity: str = "include") -> NormalizedShopperProfile:
        return NormalizedShopperProfile(
            category="shoes", query_terms=("classic training shoes",),
            constraints=(ConstraintView("budget", value, "hard", polarity),),
        )

    def test_affordable_201st_product_survives_lexical_cutoff_and_ranks_first(self) -> None:
        products = [_product(f"EXPENSIVE-{index:03}", 500) for index in range(200)]
        products.append(_product("Z-AFFORDABLE", 20, popularity=1))
        self._write_products(products)
        ranker = Ranker(self.path)
        try:
            profile = self._profile("under 30")
            result = ranker.retriever.retrieve_with_routes(profile, route_limit=200)
            self.assertNotIn("Z-AFFORDABLE", result.routes["weighted_fts"])
            self.assertNotIn("Z-AFFORDABLE", result.routes["category_path"])
            self.assertEqual(result.routes["numeric_budget_0"], ("Z-AFFORDABLE",))
            self.assertEqual(ranker.rank(profile)[0]["parent_asin"], "Z-AFFORDABLE")
        finally:
            ranker.close()

    def test_numeric_route_prefers_category_before_popularity_and_is_deterministic(self) -> None:
        products = [_product(f"DRESS-{index:03}", 10, category="Dresses") for index in range(210)]
        products.extend([_product("SHOE-B", 20, popularity=1),
                         _product("SHOE-A", 20, popularity=1)])
        self._write_products(products)
        catalog = CatalogIndex(self.path)
        try:
            retriever = CandidateRetriever(catalog)
            first = retriever.retrieve_with_routes(self._profile("<= 30"), route_limit=2)
            second = retriever.retrieve_with_routes(self._profile("<= 30"), route_limit=2)
            self.assertEqual(first.routes["numeric_budget_0"], ("SHOE-A", "SHOE-B"))
            self.assertEqual(first, second)
        finally:
            catalog.close()

    def test_numeric_route_respects_bounds_and_keeps_unknown_prices_out_of_numeric_evidence(self) -> None:
        self._write_products([_product("P20", 20), _product("P30", 30), _product("UNKNOWN", None)])
        catalog = CatalogIndex(self.path)
        try:
            retriever = CandidateRetriever(catalog)
            strict = retriever.retrieve_with_routes(self._profile("< 30"))
            inclusive = retriever.retrieve_with_routes(self._profile(">= 20 and <= 30"))
            self.assertEqual(strict.routes["numeric_budget_0"], ("P20",))
            self.assertEqual(set(inclusive.routes["numeric_budget_0"]), {"P20", "P30"})
            self.assertIn("UNKNOWN", strict.scores)
            for profile in (self._profile("SGD <= 30"), self._profile("<= 30", polarity="exclude")):
                result = retriever.retrieve_with_routes(profile)
                self.assertFalse(any(name.startswith("numeric_budget") for name in result.routes))
        finally:
            catalog.close()

    def test_numeric_route_does_not_promote_off_category_known_price_over_unknown_price(self) -> None:
        self._write_products([
            {**_product("BOOTS", 89, category="Boots"), "title": "Black winter boots"},
            {**_product("DRESS", None, category="Dresses", popularity=1),
             "title": "Red polyester dress"},
        ])
        ranker = Ranker(self.path)
        try:
            profile = NormalizedShopperProfile(
                category="dresses", query_terms=("red polyester dress",),
                constraints=(ConstraintView("budget", "under 100", "hard"),),
            )
            result = ranker.retriever.retrieve_with_routes(profile)
            self.assertNotIn("numeric_budget_0", result.routes)
            self.assertEqual(ranker.rank(profile)[0]["parent_asin"], "DRESS")
        finally:
            ranker.close()


if __name__ == "__main__":
    unittest.main()
