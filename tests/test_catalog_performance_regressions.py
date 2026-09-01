from __future__ import annotations

import unittest
import unicodedata
from unittest.mock import Mock, patch

from starter import catalog


def _reference_material_terms(raw_fields, present, *, possible_negation):
    """Pre-optimization algorithm, retained as a differential test oracle."""
    raw_fields = tuple(raw_fields)
    if not present or not possible_negation:
        return present, frozenset()
    affirmative = set()
    negated = set()
    for raw_field in raw_fields:
        text = unicodedata.normalize("NFKC", raw_field).casefold()
        for material in present:
            for match in catalog._MATERIAL_PATTERNS[material].finditer(text):
                prefix = text[max(0, match.start() - 80):match.start()]
                suffix = text[match.end():match.end() + 50]
                if catalog._NEGATED_MATERIAL_PREFIX.search(prefix) or catalog._NEGATED_MATERIAL_SUFFIX.search(suffix):
                    negated.add(material)
                else:
                    affirmative.add(material)
    return frozenset(affirmative - negated), frozenset(affirmative & negated)


class CatalogPerformanceRegressionTest(unittest.TestCase):
    def test_material_first_word_fast_path_preserves_reference_semantics(self) -> None:
        fields = (
            ("Cotton-free polyester shoe", "Shoes", "Without cotton", "100% polyester", "Store", ""),
            ("Cotton shoe", "Shoes", "Cotton-free upper", "Polyester lining", "", ""),
            ("\uff2e\uff2f cotton; polyester", "", "", "", "", ""),
            ("Faux\u2011leather free upper", "", "No faux leather", "", "", ""),
            ("Stainless\u2014steel pin", "", "Sterling-silver coating", "Free shipping", "", ""),
            ("Cotton free shipping", "Free size", "No defects", "", "", ""),
            ("No colour preference. Genuine suede.", "", "Silk-free finish", "", "", ""),
            ("No materials specified", "", "", "", "", ""),
        )
        for raw_fields in fields:
            for present in (frozenset(catalog.MATERIALS), frozenset({"cotton"}), frozenset()):
                for possible_negation in (False, True):
                    with self.subTest(raw_fields=raw_fields, present=present, possible_negation=possible_negation):
                        expected = _reference_material_terms(raw_fields, present, possible_negation=possible_negation)
                        actual = catalog._catalog_material_terms(raw_fields, present, possible_negation=possible_negation)
                        self.assertEqual(actual, expected)

    def test_all_controlled_materials_keep_hyphen_and_unicode_matches(self) -> None:
        for material in catalog.MATERIALS:
            for separator in (" ", "-", "\u2011", "\u2014"):
                mention = material.replace(" ", separator)
                raw_fields = (f"No {mention}", "Unrelated category", f"Contains {mention}", "Free shipping")
                present = frozenset(catalog.MATERIALS)
                with self.subTest(material=material, separator=separator):
                    self.assertEqual(
                        catalog._catalog_material_terms(raw_fields, present, possible_negation=True),
                        _reference_material_terms(raw_fields, present, possible_negation=True),
                    )

    def test_unrelated_fields_do_not_trigger_material_regex_scans(self) -> None:
        tracker = Mock(wraps=catalog._MATERIAL_PATTERNS["cotton"])
        fields = ("No cotton", "Shoes", "Comfortable fit", "Size medium", "Example store", "Free shipping")
        with patch.dict(catalog._MATERIAL_PATTERNS, {"cotton": tracker}):
            actual = catalog._catalog_material_terms(fields, frozenset({"cotton"}), possible_negation=True)
        self.assertEqual(actual, (frozenset(), frozenset()))
        self.assertEqual(tracker.finditer.call_count, 1)
        tracker.finditer.assert_called_once_with("no cotton")


if __name__ == "__main__":
    unittest.main()
