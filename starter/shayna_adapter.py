"""Optional, dependency-free boundary for Shayna's real ShopperProfile schema.

Use ``Ranker(path, profile_adapter=ShaynaProfileAdapter())``. Generic profiles
continue through DefaultProfileAdapter unchanged. This module never imports
``src``, reads conversation history, or asks the parser to reinterpret intent.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from starter.catalog import canonical_category, category_query_variants, normalize_text
from starter.profile_adapter import DefaultProfileAdapter, NormalizedShopperProfile


def _has_field(profile: object, name: str) -> bool:
    return name in profile if isinstance(profile, Mapping) else hasattr(profile, name)


def _is_shayna_profile(profile: object) -> bool:
    # Also accepts an asdict()/JSON representation of the same dataclass.
    # A generic mapping with category/query_terms is not a Shayna snapshot.
    return all(_has_field(profile, name)
               for name in ("session_id", "user_profile", "intent_mode", "constraints"))


class ShaynaProfileAdapter:
    """Adapt a complete Shayna state, preserving active constraint semantics.

    Shayna's supplemental phrases are full-valued active constraints (including
    ``other``), not an independent query history. Rebuilding from that source
    preserves uncommon phrases while dropping overrides, exclusions and
    no-preference slots. A future schema with independently authoritative query
    terms needs an explicit contract update rather than merging stale history.
    """

    def __init__(self) -> None:
        self._default = DefaultProfileAdapter()

    def adapt(self, profile: object) -> NormalizedShopperProfile:
        normalized = self._default.adapt(profile)
        if isinstance(profile, NormalizedShopperProfile) or not _is_shayna_profile(profile):
            return normalized

        canonical_constraints = tuple(
            replace(item, value=canonical_category(item.value))
            if item.attribute == "category" else item
            for item in normalized.constraints
        )
        # Canonical forms can expose an include/exclude duplicate that was
        # spelled differently (dress/dresses). Reuse the existing recent-turn,
        # strength/confidence and negative-polarity conflict rules.
        constraints = self._default.adapt({"active_constraints": canonical_constraints}).constraints
        inclusions = tuple(item for item in constraints if item.polarity == "include")
        categories = tuple(item for item in inclusions if item.attribute == "category")
        current_category = max(
            categories,
            key=lambda item: (item.source_turn, item.confidence, item.strength == "hard", item.value),
            default=None,
        )
        phrases: list[str] = []
        seen: set[str] = set()
        for item in inclusions:
            values = category_query_variants(item.value) if item.attribute == "category" else (item.value,)
            for value in values:
                key = normalize_text(value)
                if key and key not in seen:
                    seen.add(key)
                    phrases.append(value)
        use_cases = tuple(item.value for item in inclusions if item.attribute == "use_case")
        return replace(
            normalized,
            category=current_category.value if current_category else None,
            mission="",
            use_case=" ".join(dict.fromkeys(use_cases)),
            query_terms=tuple(phrases),
            constraints=constraints,
        )
