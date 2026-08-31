"""Synthetic characterization and a TEST-ONLY category-policy proposal.

No production configuration option is introduced here. The reference permutation
shows the proposed opt-in ``category_hint_within_budget_tier`` semantics while
asserting that the current Ranker remains unchanged. Public-set impact is unmeasured.
Equal signatures may be reordered only within contiguous runs: a matching
signature later in the list is not permission to cross an intervening candidate.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from starter.catalog import normalize_text
from starter.profile_adapter import ConstraintView
from starter.ranker import Ranker, constraint_relation


def _proposed_order(ranker: Ranker, profile: object, *, enabled: bool = False) -> list[str]:
    """Reference-only stable permutation; it never adds or removes candidates.

    Each contiguous run has identical evidence for every non-budget hard
    constraint and identical known-contradiction status for every hard budget
    inclusion. A candidate cannot cross a different signature, even when the
    same signature reappears later. Within a run, an active metadata category
    match may beat positive budget evidence, but not a known hard contradiction.
    Missing category metadata receives no bonus, rather than becoming a
    contradiction or being filtered out.
    """

    canonical = ranker._adapt(profile)
    original = ranker._ranked_candidates(canonical)
    category_terms = normalize_text(canonical.category).split()
    hard_constraints = tuple(
        item for item in canonical.constraints
        if item.active and item.strength == "hard" and item.confidence > 0
    )
    if (
        not enabled
        or not category_terms
        or "category" in canonical.no_preference_attributes
        or any(item.attribute == "category" for item in hard_constraints)
        or not any(item.attribute == "budget" and item.polarity == "include"
                   and item.confidence >= 0.9 for item in hard_constraints)
    ):
        return original

    signatures: list[tuple[int, ...]] = []
    for parent_asin in original:
        product = ranker.catalog.products[parent_asin]
        signature: list[int] = []
        for item in hard_constraints:
            relation = constraint_relation(product, item)
            if item.attribute == "budget" and item.polarity == "include":
                # Unknown price is not a violation. Only the match bonus may
                # trade against a category hint; an actual violation may not.
                signature.append(-1 if relation == -1 else 0)
            else:
                signature.append(relation)
        signatures.append(tuple(signature))

    def lacks_category_match(parent_asin: str) -> bool:
        metadata = f" {ranker.catalog.products[parent_asin].categories} "
        return not all(f" {term} " in metadata for term in category_terms)

    result = list(original)
    start = 0
    while start < len(original):
        stop = start + 1
        while stop < len(original) and signatures[stop] == signatures[start]:
            stop += 1
        # Stable sorting preserves tie-breaks within each side. Never combine
        # non-adjacent runs: that could move an unknown-evidence product ahead
        # of an intervening product with stronger non-budget hard evidence.
        result[start:stop] = sorted(original[start:stop], key=lacks_category_match)
        start = stop
    return result


def _product(parent_asin: str, price: float | None, category: str | None,
             *, material: str | None = None, store: str = "Example") -> dict:
    return {
        "parent_asin": parent_asin,
        "title": "Classic training garment",
        "categories": ["Clothing", category] if category else [],
        "price": price,
        "features": [material] if material else [],
        "details": {}, "description": [], "store": store,
        "rating_number": 1000 if price is not None else 1,
        "average_rating": 4.5,
    }


class CategoryPolicyProposalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "catalog.jsonl"

    def tearDown(self) -> None:
        self.directory.cleanup()

    @contextmanager
    def catalog(self, products: list[dict] | None = None):
        products = products or [
            _product("BOOT", 89, "Boots"),
            _product("DRESS", None, "Dresses"),
        ]
        self.path.write_text("".join(json.dumps(product) + "\n" for product in products),
                             encoding="utf-8")
        ranker = Ranker(self.path)
        try:
            yield ranker
        finally:
            ranker.close()

    @staticmethod
    def profile(category: str | None = "dresses") -> dict:
        return {
            "category": category,
            "query_terms": ["classic training garment"],
            "constraints": [{"attribute": "budget", "value": "under 100", "strength": "hard"}],
        }

    def test_characterizes_current_behavior_and_opt_in_budget_match_tradeoff(self) -> None:
        with self.catalog() as ranker:
            profile = self.profile()
            self.assertEqual([item["parent_asin"] for item in ranker.rank(profile)], ["BOOT", "DRESS"])
            self.assertEqual(_proposed_order(ranker, profile), ["BOOT", "DRESS"])
            self.assertEqual(_proposed_order(ranker, profile, enabled=True), ["DRESS", "BOOT"])
            # The prototype is local to this test file, not installed in Ranker.
            self.assertEqual([item["parent_asin"] for item in ranker.rank(profile)], ["BOOT", "DRESS"])

    def test_category_hint_cannot_overrule_a_known_hard_budget_violation(self) -> None:
        with self.catalog([_product("BOOT", 89, "Boots"),
                           _product("DRESS", 500, "Dresses")]) as ranker:
            self.assertEqual(_proposed_order(ranker, self.profile(), enabled=True), ["BOOT", "DRESS"])

    def test_non_budget_hard_match_evidence_keeps_its_existing_priority(self) -> None:
        with self.catalog([_product("BOOT", 89, "Boots", material="cotton"),
                           _product("DRESS", None, "Dresses")]) as ranker:
            profile = self.profile()
            profile["constraints"].append({"attribute": "material", "value": "cotton", "strength": "hard"})
            self.assertEqual(_proposed_order(ranker, profile, enabled=True), ["BOOT", "DRESS"])

    def test_category_swap_cannot_cross_an_intervening_stronger_hard_evidence_signature(self) -> None:
        # A confirms two budget bounds, B confirms cotton, and C has neither
        # known price nor known material. A and C share the collapsed signature,
        # but swapping their non-adjacent positions would put C ahead of B.
        with self.catalog([_product("A", 50, "Boots"),
                           _product("B", None, "Boots", material="cotton"),
                           _product("C", None, "Dresses")]) as ranker:
            profile = self.profile()
            profile["constraints"].extend([
                {"attribute": "budget", "value": ">= 0", "strength": "hard"},
                {"attribute": "material", "value": "cotton", "strength": "hard"},
            ])
            material = ConstraintView("material", "cotton", "hard")
            self.assertEqual([constraint_relation(ranker.catalog.products[key], material)
                              for key in ("A", "B", "C")], [0, 1, 0])
            self.assertEqual(_proposed_order(ranker, profile), ["A", "B", "C"])
            self.assertEqual(_proposed_order(ranker, profile, enabled=True), ["A", "B", "C"])

    def test_explicit_hard_category_disables_conflicting_hint_policy(self) -> None:
        with self.catalog() as ranker:
            profile = self.profile(category="boots")
            profile["constraints"].append({"attribute": "category", "value": "dresses", "strength": "hard"})
            before = _proposed_order(ranker, profile)
            self.assertEqual(before[0], "DRESS")
            self.assertEqual(_proposed_order(ranker, profile, enabled=True), before)

    def test_missing_category_no_preference_and_soft_budget_do_not_enable_policy(self) -> None:
        with self.catalog() as ranker:
            no_preference = self.profile()
            no_preference["no_preference_attributes"] = ["category"]
            soft_budget = self.profile()
            soft_budget["constraints"][0]["strength"] = "soft"
            low_confidence = self.profile()
            low_confidence["constraints"][0]["confidence"] = 0.5
            for profile in (self.profile(category=None), no_preference, soft_budget, low_confidence):
                with self.subTest(profile=profile):
                    self.assertEqual(_proposed_order(ranker, profile, enabled=True),
                                     _proposed_order(ranker, profile))

    def test_unknown_catalog_category_remains_neutral_and_is_not_filtered(self) -> None:
        with self.catalog([_product("UNCLASSIFIED", 20, None),
                           _product("DRESS", None, "Dresses")]) as ranker:
            unknown = ranker.catalog.products["UNCLASSIFIED"]
            self.assertEqual(constraint_relation(unknown, ConstraintView("category", "dresses", "hard")), 0)
            self.assertEqual(_proposed_order(ranker, self.profile(), enabled=True), ["DRESS", "UNCLASSIFIED"])

    def test_hard_exclusions_are_never_reintroduced(self) -> None:
        with self.catalog([_product("BOOT", 89, "Boots", store="BootCo"),
                           _product("DRESS", None, "Dresses", store="DressCo")]) as ranker:
            profile = self.profile()
            profile["constraints"].append({"attribute": "brand", "value": "BootCo",
                                           "strength": "hard", "polarity": "exclude"})
            self.assertEqual(_proposed_order(ranker, profile, enabled=True), ["DRESS"])

    def test_override_uses_only_current_category_and_is_deterministic(self) -> None:
        with self.catalog([_product("DRESS", 20, "Dresses"),
                           _product("BOOT", None, "Boots")]) as ranker:
            profile = self.profile(category="dresses")
            profile["active_state"] = self.profile(category="boots")
            original_json = json.dumps(profile, sort_keys=True)
            self.assertEqual(_proposed_order(ranker, profile), ["DRESS", "BOOT"])
            self.assertEqual(_proposed_order(ranker, profile, enabled=True), ["BOOT", "DRESS"])
            self.assertEqual(_proposed_order(ranker, profile, enabled=True), ["BOOT", "DRESS"])
            self.assertEqual(json.dumps(profile, sort_keys=True), original_json)


if __name__ == "__main__":
    unittest.main()
