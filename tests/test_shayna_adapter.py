"""Shayna-schema compatibility without importing or copying teammate source."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
from pathlib import Path
import tempfile
import unittest

from starter.catalog import canonical_category, category_query_variants, category_terms_match
from starter.profile_adapter import ConstraintView, DefaultProfileAdapter, NormalizedShopperProfile
from starter.ranker import Ranker, constraint_relation
from starter.retrieval import query_terms
from starter.shayna_adapter import ShaynaProfileAdapter


@dataclass(frozen=True)
class TeamConstraint:
    attribute: str
    value: str
    strength: str = "hard"
    polarity: str = "include"
    source_turn: int = 1
    confidence: float = 1.0
    active: bool = True


@dataclass(frozen=True)
class TeamProfile:
    session_id: str = "fixture"
    user_profile: dict = field(default_factory=dict)
    intent_mode: str = "buying"
    constraints: tuple[TeamConstraint, ...] = ()
    asked_attributes: frozenset[str] = frozenset()
    no_preference_attributes: frozenset[str] = frozenset()
    exhausted_attributes: frozenset[str] = frozenset()
    messages: tuple[str, ...] = ()

    @property
    def active_constraints(self):
        return tuple(item for item in self.constraints if item.active)

    @property
    def query_terms(self):
        # Deliberately simulate the older derived query's no-preference leak.
        return tuple(item.value for item in self.active_constraints if item.polarity == "include")


class ShaynaAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = ShaynaProfileAdapter()

    def test_category_comes_only_from_active_inclusions(self):
        profile = TeamProfile(constraints=(
            TeamConstraint("category", "boots", active=False),
            TeamConstraint("category", "dress", "soft", source_turn=3, confidence=0.7),
            TeamConstraint("category", "shirts", polarity="exclude", source_turn=4),
        ), messages=("old cotton boots",))
        normalized = self.adapter.adapt(profile)
        self.assertEqual(normalized.category, "dresses")
        self.assertEqual(normalized.query_terms, ("dresses", "dress"))
        self.assertEqual([(c.value, c.strength, c.polarity, c.confidence, c.source_turn)
                          for c in normalized.constraints],
                         [("dresses", "soft", "include", 0.7, 3), ("shirts", "hard", "exclude", 1.0, 4)])

    def test_excluded_category_does_not_become_positive_query(self):
        normalized = self.adapter.adapt(TeamProfile(constraints=(
            TeamConstraint("category", "dress", polarity="exclude"),
            TeamConstraint("color", "blue", "soft"),
        )))
        self.assertIsNone(normalized.category)
        self.assertEqual(query_terms(normalized), ["blue"])
        self.assertEqual(normalized.constraints[0].polarity, "exclude")

    def test_latest_alias_exclusion_resolves_same_category(self):
        normalized = self.adapter.adapt(TeamProfile(constraints=(
            TeamConstraint("category", "dress", source_turn=1),
            TeamConstraint("category", "dresses", polarity="exclude", source_turn=2),
        )))
        self.assertEqual(len(normalized.constraints), 1)
        self.assertEqual(normalized.constraints[0].polarity, "exclude")
        self.assertIsNone(normalized.category)
        self.assertEqual(normalized.query_terms, ())

    def test_no_preference_and_replacement_are_complete_snapshots(self):
        original = TeamProfile(constraints=(
            TeamConstraint("category", "dress"), TeamConstraint("color", "red"),
        ), no_preference_attributes=frozenset({"color"}),
           asked_attributes=frozenset({"material"}), exhausted_attributes=frozenset({"brand"}))
        normalized = self.adapter.adapt(asdict(original))
        self.assertNotIn("red", " ".join(query_terms(normalized)))
        self.assertEqual(normalized.asked_attributes, frozenset({"material"}))
        self.assertEqual(normalized.no_preference_attributes, frozenset({"color"}))
        self.assertEqual(normalized.exhausted_attributes, frozenset({"brand"}))
        replaced = replace(original, constraints=(
            TeamConstraint("category", "dress", active=False),
            TeamConstraint("category", "shirt", source_turn=3),
            TeamConstraint("color", "blue", source_turn=3),
        ), no_preference_attributes=frozenset())
        new = self.adapter.adapt(asdict(replaced))
        self.assertEqual(new.category, "shirts")
        self.assertIn("blue", new.query_terms)
        self.assertNotIn("dress", " ".join(query_terms(new)))
        self.assertEqual(normalized.category, "dresses")

    def test_no_preference_category_removes_hint_and_query_too(self):
        normalized = self.adapter.adapt(TeamProfile(
            constraints=(TeamConstraint("category", "dress"),),
            no_preference_attributes=frozenset({"category"}),
        ))
        self.assertIsNone(normalized.category)
        self.assertEqual(normalized.query_terms, ())
        self.assertEqual(normalized.constraints, ())

    def test_uncommon_active_phrase_and_weak_prior_are_preserved(self):
        phrase = "pearlescent asymmetric lunar applique"
        normalized = self.adapter.adapt(TeamProfile(
            user_profile={"preference_tags": ["old cotton boots"]},
            constraints=(TeamConstraint("other", phrase, "soft"),
                         TeamConstraint("use_case", "date night", "soft"),
                         TeamConstraint("budget", "<= 60", confidence=0.6)),
        ))
        self.assertIn(phrase, normalized.query_terms)
        self.assertEqual(normalized.use_case, "date night")
        self.assertEqual(normalized.constraints[-1].value, "<= 60")
        self.assertEqual(normalized.constraints[-1].confidence, 0.6)
        self.assertEqual(normalized.preference_tags, ("old cotton boots",))
        self.assertNotIn("old cotton boots", normalized.query_terms)

    def test_generic_profiles_delegate_without_reinterpretation(self):
        profile = {"category": "dress", "query_terms": ["supplemental rare phrase"],
                   "constraints": [{"attribute": "material", "value": "silk"}]}
        self.assertEqual(self.adapter.adapt(profile), DefaultProfileAdapter().adapt(profile))
        canonical = NormalizedShopperProfile(category="dress", query_terms=("do not rebuild",))
        self.assertIs(self.adapter.adapt(canonical), canonical)

    def test_explicit_empty_active_constraints_are_authoritative(self):
        profile = asdict(TeamProfile(constraints=(TeamConstraint("category", "dress"),)))
        profile["active_constraints"] = []
        profile["category"] = "old boots"
        profile["query_terms"] = ["old red cotton boots"]
        normalized = self.adapter.adapt(profile)
        self.assertIsNone(normalized.category)
        self.assertEqual(normalized.query_terms, ())
        self.assertEqual(normalized.constraints, ())

    def test_exact_category_aliases_are_symmetric_and_not_substrings(self):
        for singular, plural in (("dress", "dresses"), ("shirt", "shirts"),
                                 ("jacket", "jackets"), ("hoodie", "hoodies"), ("shoe", "shoes")):
            with self.subTest(category=singular):
                self.assertTrue(category_terms_match(f"Women {plural}", singular))
                self.assertTrue(category_terms_match(f"Women {singular}", plural))
                self.assertEqual(canonical_category(singular), plural)
                self.assertEqual(category_query_variants(plural), (plural, singular))
        self.assertFalse(category_terms_match("address labels", "dress"))
        self.assertFalse(category_terms_match("dressing gowns", "dress"))
        self.assertFalse(category_terms_match("", "dress"))
        self.assertFalse(category_terms_match("dresses", ""))
        self.assertTrue(category_terms_match("Women DRESSES", "ＤＲＥＳＳ"))


class ShaynaCategoryRankingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name) / "catalog.jsonl"
        records = [
            {"parent_asin": "PLURAL", "title": "Red summer dress", "categories": ["Women", "Dresses"]},
            {"parent_asin": "SINGULAR", "title": "Red evening dresses", "categories": ["Women", "Dress"]},
            {"parent_asin": "UNKNOWN", "title": "Red dress", "categories": []},
            {"parent_asin": "SHIRT", "title": "Red shirt", "categories": ["Women", "Shirts"]},
            {"parent_asin": "SUBSTRING", "title": "Red dressing gown", "categories": ["Dressing Gowns"]},
        ]
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        self.ranker = Ranker(path, profile_adapter=ShaynaProfileAdapter())
        self.addCleanup(self.ranker.close)

    def test_hard_category_relation_handles_both_forms_and_missing_stays_neutral(self):
        for value in ("dress", "dresses"):
            constraint = ConstraintView("category", value, "hard")
            relations = {name: constraint_relation(product, constraint)
                         for name, product in self.ranker.catalog.products.items()}
            self.assertEqual(relations, {"PLURAL": 1, "SINGULAR": 1, "UNKNOWN": 0, "SHIRT": -1, "SUBSTRING": -1})

    def test_hard_category_match_wins_and_returns_valid_unique_ids(self):
        profile = TeamProfile(constraints=(TeamConstraint("category", "dress"), TeamConstraint("color", "red", "soft")))
        ranked = self.ranker.rank(profile)
        ids = [row["parent_asin"] for row in ranked]
        self.assertEqual(set(ids[:2]), {"PLURAL", "SINGULAR"})
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(ids) <= self.ranker.catalog.valid_ids)
        self.assertEqual(ranked, self.ranker.rank(profile))

    def test_category_exclusion_removes_both_spellings_but_not_unknown(self):
        profile = TeamProfile(constraints=(TeamConstraint("category", "dress", polarity="exclude"),
                                           TeamConstraint("color", "red", "soft")))
        ids = {row["parent_asin"] for row in self.ranker.rank(profile)}
        self.assertNotIn("PLURAL", ids)
        self.assertNotIn("SINGULAR", ids)
        self.assertIn("UNKNOWN", ids)


if __name__ == "__main__":
    unittest.main()
