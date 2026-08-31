from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.catalog import MATERIALS, CatalogIndex, extract_known_terms, flatten_text, normalize_text, parse_price
from starter.retrieval import CandidateRetriever, reciprocal_rank_fusion


PRODUCTS = [
    {
        "parent_asin": "A",
        "title": "Blue cotton running shoe",
        "features": ["breathable cotton", "wide fit"],
        "details": {"Department": "Women"},
        "description": ["comfortable gym shoe"],
        "categories": ["Clothing", "Women", "Shoes"],
        "store": "Alpha",
        "price": 49.0,
        "average_rating": 4.4,
        "rating_number": 20,
    },
    {
        "parent_asin": "B",
        "title": "Black leather winter boot",
        "features": [],
        "details": {},
        "description": [],
        "categories": ["Clothing", "Women", "Boots"],
        "store": None,
        "price": "$89.00",
        "average_rating": 4.7,
        "rating_number": 30,
    },
    {
        "parent_asin": "C",
        "title": "Red polyester dress",
        "features": ["formal"],
        "details": {"Department": "Women"},
        "description": None,
        "categories": ["Clothing", "Women", "Dresses"],
        "store": "Charlie",
        "price": None,
        "average_rating": 4.0,
        "rating_number": 10,
    },
]


class CatalogFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "catalog.jsonl"
        self.path.write_text(
            "".join(json.dumps(product) + "\n" for product in PRODUCTS),
            encoding="utf-8",
        )
        self.catalog = CatalogIndex(self.path)

    def tearDown(self) -> None:
        self.catalog.close()
        self.directory.cleanup()

    def test_catalog_normalizes_missing_fields_and_prices(self) -> None:
        self.assertEqual(len(self.catalog.valid_ids), 3)
        self.assertEqual(self.catalog.products["B"].price, 89.0)
        self.assertIsNone(self.catalog.products["C"].price)
        self.assertEqual(flatten_text({"a": ["b", "c"]}), "a b c")
        self.assertIsNone(parse_price("not listed"))

    def test_weighted_and_category_routes_retrieve_expected_product(self) -> None:
        retriever = CandidateRetriever(self.catalog)
        profile = {
            "category": "shoes",
            "query_terms": ["blue cotton running"],
            "constraints": [],
        }
        scores = retriever.retrieve(profile, route_limit=10)
        self.assertIn("A", scores)
        self.assertEqual(max(scores, key=scores.get), "A")

    def test_rrf_deduplicates_each_route(self) -> None:
        scores = reciprocal_rank_fusion([["A", "A", "B"], ["B", "A"]])
        self.assertGreater(scores["A"], 0)
        self.assertGreater(scores["B"], 0)

    def test_exact_phrase_and_structured_routes_are_distinct(self) -> None:
        retriever = CandidateRetriever(self.catalog)
        profile = {
            "category": "shoes",
            "query_terms": ["running shoe"],
            "constraints": [
                {"attribute": "material", "value": "cotton", "strength": "hard"},
                {"attribute": "color", "value": "blue", "strength": "soft"},
            ],
        }
        result = retriever.retrieve_with_routes(profile, route_limit=10)
        self.assertIn("exact_clauses", result.routes)
        self.assertIn("structured_material_0", result.routes)
        self.assertIn("structured_color_1", result.routes)
        self.assertEqual(result.routes["structured_material_0"][0], "A")

    def test_unicode_normalization_and_python_fallback(self) -> None:
        self.assertEqual(normalize_text("Café d’Or 東京"), "café d or 東京")
        product = {
            "parent_asin": "U",
            "title": "Café d’Or 東京 scarf",
            "features": [],
            "details": {},
            "description": [],
            "categories": ["Accessories"],
            "store": "Élan",
            "price": None,
            "average_rating": "4.5",
            "rating_number": "8",
        }
        unicode_path = Path(self.directory.name) / "unicode.jsonl"
        unicode_path.write_text(json.dumps(product) + "\n", encoding="utf-8")
        fallback = CatalogIndex(unicode_path, force_python_search=True)
        try:
            self.assertFalse(fallback.fts_available)
            self.assertEqual(fallback.search(["cafe scarf"]), ["U"])
            self.assertEqual(fallback.search_phrases(["cafe d or"]), ["U"])
            self.assertEqual(fallback.products["U"].average_rating, 4.5)
            self.assertEqual(fallback.products["U"].rating_number, 8)
        finally:
            fallback.close()
        fts = CatalogIndex(unicode_path)
        try:
            self.assertEqual(fts.search(["cafe scarf"]), ["U"])
        finally:
            fts.close()

    def test_specific_material_phrase_does_not_collapse_to_generic_term(self) -> None:
        self.assertEqual(extract_known_terms("faux leather upper", MATERIALS), {"faux leather"})

    def test_empty_and_duplicate_ids_are_rejected(self) -> None:
        bad_path = Path(self.directory.name) / "bad.jsonl"
        bad_path.write_text(
            json.dumps({**PRODUCTS[0], "parent_asin": ""}) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "no parent_asin"):
            CatalogIndex(bad_path)

        bad_path.write_text(
            json.dumps(PRODUCTS[0]) + "\n" + json.dumps(PRODUCTS[0]) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate parent_asin"):
            CatalogIndex(bad_path)


class OfficialCatalogIntegrityTest(unittest.TestCase):
    @unittest.skipUnless(Path("data/catalog.jsonl").exists(), "downloaded catalog is not present")
    def test_official_catalog_has_50000_unique_nonempty_ids(self) -> None:
        identifiers: list[str] = []
        with Path("data/catalog.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    identifiers.append(str(json.loads(line).get("parent_asin") or "").strip())
        self.assertEqual(len(identifiers), 50_000)
        self.assertTrue(all(identifiers))
        self.assertEqual(len(set(identifiers)), 50_000)


if __name__ == "__main__":
    unittest.main()
