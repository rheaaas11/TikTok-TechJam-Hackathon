from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from heapq import nsmallest
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from starter.budget import parse_budget
from starter.catalog import CatalogIndex, normalize_text
from starter.profile_adapter import (
    ConstraintView,
    DefaultProfileAdapter,
    NormalizedShopperProfile,
)


def profile_value(profile: object, name: str, default: object = None) -> object:
    """Backward-compatible shallow accessor for demo integrations."""

    if isinstance(profile, Mapping):
        return profile.get(name, default)
    return getattr(profile, name, default)


def _normalized(profile: object) -> NormalizedShopperProfile:
    if isinstance(profile, NormalizedShopperProfile):
        return profile
    return DefaultProfileAdapter().adapt(profile)


def active_constraints(profile: object) -> list[ConstraintView]:
    return list(_normalized(profile).constraints)


def query_terms(profile: object) -> list[str]:
    canonical = _normalized(profile)
    parts: list[str] = []
    for value in (canonical.category, canonical.mission, canonical.use_case):
        if value:
            parts.append(value)
    parts.extend(canonical.query_terms)
    parts.extend(
        constraint.value
        for constraint in canonical.constraints
        if constraint.polarity == "include"
    )
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = normalize_text(part)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(str(part))
    return result


def reciprocal_rank_fusion(
    routes: Iterable[Sequence[str]],
    k: int = 60,
) -> dict[str, float]:
    if k < 1:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = {}
    for route in routes:
        seen: set[str] = set()
        for rank, parent_asin in enumerate(route, 1):
            if parent_asin in seen:
                continue
            seen.add(parent_asin)
            scores[parent_asin] = scores.get(parent_asin, 0.0) + 1.0 / (k + rank)
    return scores


@dataclass(frozen=True)
class RetrievalResult:
    scores: Mapping[str, float]
    routes: Mapping[str, tuple[str, ...]]


class CandidateRetriever:
    """Deterministic multi-route candidate generator with RRF merging."""

    def __init__(self, catalog: CatalogIndex, *, rrf_k: int = 60) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        self.catalog = catalog
        self.rrf_k = rrf_k
        # Numeric evidence is absent from FTS fields. Index known prices once so
        # an affordable item cannot disappear behind a lexical top-N cutoff.
        self._priced_ids = tuple(sorted(
            (product.price, parent_asin)
            for parent_asin, product in catalog.products.items()
            if product.price is not None
        ))
        self._prices = tuple(price for price, _ in self._priced_ids)
        self._popularity_order = {
            parent_asin: index
            for index, parent_asin in enumerate(catalog.fallback(len(catalog.products)))
        }

    def _budget_candidates(self, value: str, category: str | None, limit: int) -> list[str]:
        interval = parse_budget(value)
        if interval is None:
            return []
        start = 0
        stop = len(self._prices)
        if interval.lower is not None:
            start = (bisect_left if interval.lower_inclusive else bisect_right)(
                self._prices, interval.lower
            )
        if interval.upper is not None:
            stop = (bisect_right if interval.upper_inclusive else bisect_left)(
                self._prices, interval.upper
            )
        category_terms = tuple(dict.fromkeys(normalize_text(category).split()))

        def in_category(item: tuple[float, str]) -> bool:
            parent_asin = item[1]
            product = self.catalog.products[parent_asin]
            padded_category = f" {product.categories} "
            # Do not let off-category known-price products outrank an otherwise
            # relevant product with unknown price. Other routes still retain
            # unknown-price or incomplete-category products for missing-safe ranking.
            return all(f" {term} " in padded_category for term in category_terms)

        def preference(item: tuple[float, str]) -> tuple[int, str]:
            parent_asin = item[1]
            return (self._popularity_order[parent_asin], parent_asin)

        return [
            parent_asin
            for _, parent_asin in nsmallest(
                limit, (item for item in self._priced_ids[start:stop] if in_category(item)),
                key=preference,
            )
        ]

    def retrieve_with_routes(
        self,
        profile: object,
        route_limit: int = 200,
    ) -> RetrievalResult:
        canonical = _normalized(profile)
        limit = max(1, int(route_limit))
        terms = query_terms(canonical)
        constraints = canonical.constraints
        routes: dict[str, list[str]] = {}

        broad = self.catalog.search(terms, limit)
        if broad:
            routes["weighted_fts"] = broad

        if canonical.category:
            category_route = self.catalog.search_category(canonical.category, limit)
            if category_route:
                routes["category_path"] = category_route

        hard_phrases = [
            constraint.value
            for constraint in constraints
            if constraint.polarity == "include" and constraint.strength == "hard"
        ]
        soft_phrases = [
            constraint.value
            for constraint in constraints
            if constraint.polarity == "include" and constraint.strength != "hard"
        ]
        exact_phrases = [*hard_phrases, *soft_phrases]
        if exact_phrases:
            exact_route = self.catalog.search_phrases(exact_phrases, limit)
            if exact_route:
                routes["exact_clauses"] = exact_route

        structured_pairs = [
            (constraint.attribute, constraint.value)
            for constraint in constraints
            if constraint.polarity == "include"
            and constraint.attribute in {"material", "color", "size", "style", "brand"}
        ]
        for index, pair in enumerate(structured_pairs):
            structured_route = self.catalog.structured_search([pair], limit)
            if structured_route:
                routes[f"structured_{pair[0]}_{index}"] = structured_route

        budget_constraints = [
            constraint for constraint in constraints
            if constraint.polarity == "include" and constraint.attribute == "budget"
        ]
        for index, constraint in enumerate(budget_constraints):
            budget_route = self._budget_candidates(constraint.value, canonical.category, limit)
            if budget_route:
                routes[f"numeric_budget_{index}"] = budget_route

        if not routes:
            routes["catalog_fallback"] = self.catalog.fallback(limit)

        fused = reciprocal_rank_fusion(routes.values(), self.rrf_k)
        immutable_routes = MappingProxyType(
            {name: tuple(values) for name, values in routes.items()}
        )
        return RetrievalResult(MappingProxyType(fused), immutable_routes)

    def retrieve(self, profile: object, route_limit: int = 200) -> dict[str, float]:
        return dict(self.retrieve_with_routes(profile, route_limit).scores)
