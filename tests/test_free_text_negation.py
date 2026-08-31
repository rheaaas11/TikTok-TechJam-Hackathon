"""An explicit catalog negation must not become an exclusion violation."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from starter.catalog import Product, normalize_text
from starter.profile_adapter import ConstraintView
from starter.ranker import Ranker, constraint_relation


def product(*, title="Example garment", features="", description=""):
    raw = (title, "", features, "", "", description)
    return Product(
        parent_asin="FIXTURE", title=normalize_text(title), categories="",
        features=normalize_text(features), details="", store="",
        description=normalize_text(description), price=None, average_rating=None,
        rating_number=0, materials=frozenset(), colors=frozenset(), sizes=frozenset(),
        styles=frozenset(), category_path=(), raw_fields=raw,
    )


class FreeTextNegationTests(unittest.TestCase):
    def test_negated_feature_does_not_violate_exclusion(self):
        for text in (
            "No ironing", "without ironing", "not requiring ironing",
            "Does not require ironing", "No need for ironing", "ironing-free",
            "ironing\u2011free", "ironing is not required", "ironing not needed",
            "\uff2e\uff4f ironing", "No washing or ironing",
        ):
            with self.subTest(text=text):
                self.assertEqual(constraint_relation(product(features=text),
                    ConstraintView("feature", "ironing", "hard", "exclude")), 0)

    def test_positive_affirmative_feature_remains_a_violation(self):
        for text in ("Ironing required", "Requires ironing", "Ironing", "Ironing; free shipping"):
            with self.subTest(text=text):
                self.assertEqual(constraint_relation(product(features=text),
                    ConstraintView("feature", "ironing", "hard", "exclude")), 1)

    def test_explicit_positive_no_ironing_phrase_still_matches(self):
        self.assertEqual(constraint_relation(product(features="No ironing; No shrinkage"),
            ConstraintView("feature", "no ironing", "hard", "include")), 1)
        self.assertEqual(constraint_relation(product(features="No ironing; No shrinkage"),
            ConstraintView("feature", "no shrinkage", "hard", "include")), 1)

    def test_mixed_positive_and_negated_fields_are_unknown(self):
        for item in (
            product(title="Ironing required", features="No ironing"),
            product(title="No ironing", features="Ironing required"),
            product(features="No ironing. Ironing required."),
        ):
            self.assertEqual(constraint_relation(item,
                ConstraintView("feature", "ironing", "hard", "exclude")), 0)

    def test_multiword_exclusion_requires_local_phrase_not_distributed_tokens(self):
        clause = ConstraintView("feature", "dry cleaning", "hard", "exclude")
        self.assertEqual(constraint_relation(product(features="Keep dry; gentle cleaning"), clause), 0)
        self.assertEqual(constraint_relation(product(title="Keep dry", features="Cleaning recommended"), clause), 0)
        self.assertEqual(constraint_relation(product(features="Dry-cleaning required"), clause), 1)
        self.assertEqual(constraint_relation(product(features="No dry cleaning"), clause), 0)

    def test_field_and_sentence_boundaries_do_not_invent_negation_scope(self):
        clause = ConstraintView("other", "ironing", "hard", "exclude")
        self.assertEqual(constraint_relation(product(title="No cotton", features="Ironing required"), clause), 1)
        self.assertEqual(constraint_relation(product(features="No cotton. Ironing required."), clause), 1)
        # Negation with unclear coordination is insufficient to exclude safely.
        self.assertEqual(constraint_relation(product(features="No washing or ironing is needed"), clause), 0)

    def test_missing_or_substring_only_evidence_is_unknown(self):
        clause = ConstraintView("feature", "ironing", "hard", "exclude")
        self.assertEqual(constraint_relation(product(), clause), 0)
        self.assertEqual(constraint_relation(product(features="preironing treatment"), clause), 0)

    def test_no_ironing_and_no_shrinkage_product_survives_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.jsonl"
            rows = [
                {"parent_asin": "SAFE", "title": "Women tops", "features": ["No ironing", "No shrinkage"]},
                {"parent_asin": "REQUIRES", "title": "Women tops", "features": ["Ironing required", "Shrinkage expected"]},
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            ranker = Ranker(path)
            try:
                profile = {"query_terms": ["women tops"], "constraints": [
                    ConstraintView("feature", "ironing", "hard", "exclude"),
                    ConstraintView("feature", "shrinkage", "hard", "exclude"),
                ]}
                self.assertEqual(ranker.rank(profile), [{"parent_asin": "SAFE"}])
            finally:
                ranker.close()


if __name__ == "__main__":
    unittest.main()
