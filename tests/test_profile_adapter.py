from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from starter.profile_adapter import (
    ConstraintView,
    DefaultProfileAdapter,
    NormalizedShopperProfile,
)
from starter.ranker import Ranker
from tests.test_retrieval import PRODUCTS


@dataclass
class ObjectConstraint:
    field: str
    text: str
    priority: str = "required"
    is_active: bool = True
    turn_index: int = 1


@dataclass
class DataclassProfile:
    product_type: str
    search_terms: list[str]
    requirements: list[ObjectConstraint] = field(default_factory=list)
    attributes_asked: set[str] = field(default_factory=set)


class NestedState:
    def __init__(self) -> None:
        self.category = "boots"
        self.query_terms = ["black leather winter boot"]
        self.constraints = [ObjectConstraint("material", "leather")]


class WrapperProfile:
    current_category = "stale shoes"
    query_terms = ["stale cotton shoe"]

    def __init__(self) -> None:
        self.active_state = NestedState()


class ProfileAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = DefaultProfileAdapter()
        self.directory = tempfile.TemporaryDirectory()
        self.catalog_path = Path(self.directory.name) / "catalog.jsonl"
        self.catalog_path.write_text(
            "".join(json.dumps(product) + "\n" for product in PRODUCTS),
            encoding="utf-8",
        )
        self.ranker = Ranker(self.catalog_path)

    def tearDown(self) -> None:
        self.ranker.close()
        self.directory.cleanup()

    def test_mapping_aliases_and_raw_budget_operator(self) -> None:
        profile = {
            "target_category": "shoes",
            "active_query_terms": ["running shoe"],
            "hard_constraints": {"price": "<= $60", "colour": "blue"},
            "aggregate_profile": {"profile_tags": ["wide fit"]},
        }
        canonical = self.adapter.adapt(profile)
        self.assertEqual(canonical.category, "shoes")
        self.assertEqual(canonical.preference_tags, ("wide fit",))
        self.assertIn(
            ("budget", "<= $60", "hard"),
            {(item.attribute, item.value, item.strength) for item in canonical.constraints},
        )
        self.assertEqual(self.ranker.rank(profile)[0]["parent_asin"], "A")

    def test_dataclass_and_constraint_objects(self) -> None:
        profile = DataclassProfile(
            product_type="boots",
            search_terms=["winter boot"],
            requirements=[ObjectConstraint("material", "leather")],
            attributes_asked={"colour"},
        )
        canonical = self.adapter.adapt(profile)
        self.assertEqual(canonical.category, "boots")
        self.assertEqual(canonical.constraints[0].strength, "hard")
        self.assertEqual(canonical.asked_attributes, frozenset({"color"}))
        self.assertEqual(self.ranker.rank(profile)[0]["parent_asin"], "B")

    def test_nested_active_state_beats_stale_root_aliases(self) -> None:
        canonical = self.adapter.adapt(WrapperProfile())
        self.assertEqual(canonical.category, "boots")
        self.assertEqual(canonical.query_terms, ("black leather winter boot",))
        self.assertNotIn("stale cotton shoe", canonical.query_terms)
        self.assertEqual(self.ranker.rank(WrapperProfile())[0]["parent_asin"], "B")

    def test_duplicate_generic_and_typed_constraint_keeps_hard_once(self) -> None:
        profile = {
            "constraints": [{"attribute": "material", "value": "cotton", "strength": "soft"}],
            "hard_constraints": [{"attribute": "material", "value": "cotton"}],
        }
        canonical = self.adapter.adapt(profile)
        self.assertEqual(len(canonical.constraints), 1)
        self.assertEqual(canonical.constraints[0].strength, "hard")

    def test_no_preference_removes_slot_and_newer_exclusion_wins(self) -> None:
        profile = {
            "constraints": [
                {"attribute": "color", "value": "red", "polarity": "include", "source_turn": 1},
                {"attribute": "material", "value": "cotton", "polarity": "include", "source_turn": 1},
                {"attribute": "material", "value": "cotton", "polarity": "exclude", "source_turn": 3},
            ],
            "no_preferences": {"color": True},
        }
        canonical = self.adapter.adapt(profile)
        self.assertNotIn("color", {item.attribute for item in canonical.constraints})
        self.assertEqual(len(canonical.constraints), 1)
        self.assertEqual(canonical.constraints[0].polarity, "exclude")

    def test_custom_adapter_is_the_only_ranker_schema_hook(self) -> None:
        class CustomAdapter:
            def adapt(self, profile: object) -> NormalizedShopperProfile:
                return NormalizedShopperProfile(
                    category="dresses",
                    query_terms=("red polyester dress",),
                    constraints=(ConstraintView("material", "polyester", "hard"),),
                )

        custom_ranker = Ranker(self.catalog_path, profile_adapter=CustomAdapter())
        try:
            self.assertEqual(custom_ranker.rank(object())[0]["parent_asin"], "C")
        finally:
            custom_ranker.close()


if __name__ == "__main__":
    unittest.main()
