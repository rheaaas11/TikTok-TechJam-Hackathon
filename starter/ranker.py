from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from starter.budget import budget_relation
from starter.catalog import (
    COLORS,
    MATERIALS,
    SIZES,
    STYLES,
    CatalogIndex,
    Product,
    extract_known_terms,
    normalize_text,
)
from starter.profile_adapter import (
    ConstraintView,
    DefaultProfileAdapter,
    NormalizedShopperProfile,
    ProfileAdapterLike,
    adapt_profile,
)
from starter.retrieval import CandidateRetriever


ALLOWED_STATS_ATTRIBUTES = ("category", "material", "color", "size", "style", "brand", "budget")
STRICT_STRUCTURED_ATTRIBUTES = frozenset(
    {"category", "material", "color", "size", "style", "brand", "budget"}
)
_STRUCTURED_VOCABULARIES = {
    "material": MATERIALS,
    "color": COLORS,
    "size": SIZES,
    "style": STYLES,
}


def _contains_all(text: str, value: str) -> bool:
    normalized = normalize_text(value)
    if not normalized:
        return False
    padded = f" {text} "
    return all(f" {term} " in padded for term in normalized.split())


def _contains_phrase(text: str, value: str) -> bool:
    normalized = normalize_text(value)
    return bool(normalized and f" {normalized} " in f" {text} ")


def _field_text(product: Product, attribute: str) -> str:
    if attribute == "category":
        return product.categories
    if attribute == "brand":
        return product.store
    if attribute == "material":
        return " ".join(product.materials)
    if attribute == "color":
        return " ".join(product.colors)
    if attribute == "size":
        return " ".join(product.sizes)
    if attribute == "style":
        return " ".join(product.styles)
    return product.searchable_text


def _budget_relation(product: Product, constraint: ConstraintView) -> int:
    """Return 1 match, -1 contradiction, or 0 unknown for a budget clause."""
    return budget_relation(product.price, constraint.value)


def constraint_relation(product: Product, constraint: ConstraintView) -> int:
    """Three-valued catalog relation: match, contradiction, or unknown.

    Absence of a free-text feature is unknown.  A contradiction is emitted only
    for trustworthy structured fields whose catalog value is actually known.
    """

    if constraint.attribute == "budget":
        return _budget_relation(product, constraint)

    if constraint.attribute in _STRUCTURED_VOCABULARIES:
        requested = set(
            extract_known_terms(
                constraint.value,
                _STRUCTURED_VOCABULARIES[constraint.attribute],
            )
        )
        if constraint.attribute == "color":
            requested = {"gray" if value == "grey" else value for value in requested}
        product_values = set(product.attribute_values(constraint.attribute))
        if requested:
            if requested & product_values:
                return 1
            if constraint.attribute == "material" and requested & getattr(product, "uncertain_materials", frozenset()):
                return 0
            if not product_values:
                return 0
            return -1
        # The controlled vocabulary is intentionally incomplete.  An unfamiliar
        # material/size phrase can match text, but cannot prove a contradiction.
        return 1 if _contains_all(product.searchable_text, constraint.value) else 0

    field = _field_text(product, constraint.attribute)
    if not field:
        return 0
    if _contains_all(field, constraint.value):
        return 1
    if constraint.attribute in {"category", "brand"}:
        return -1
    return 0


@dataclass(frozen=True)
class _Candidate:
    parent_asin: str
    sort_key: tuple[object, ...]
    relations: tuple[int, ...]


@dataclass(frozen=True)
class RankingResult:
    """Internal/debug result; never place this object in the official payload."""

    recommendations: tuple[dict[str, str], ...]
    candidate_pool_size: int
    route_sizes: tuple[tuple[str, int], ...]
    relaxed_hard_constraints: tuple[str, ...]


class Ranker:
    """Deterministic, offline retrieval and missing-safe reranking.

    ``profile_adapter`` is the only compatibility boundary.  Future Shayna
    profile schemas do not require changes to catalog, retrieval, or scoring.
    """

    def __init__(
        self,
        catalog_path: str | Path,
        *,
        profile_adapter: ProfileAdapterLike | None = None,
    ) -> None:
        self.catalog = CatalogIndex(catalog_path)
        self.profile_adapter = profile_adapter or DefaultProfileAdapter()
        self.retriever = CandidateRetriever(self.catalog)

    def _adapt(self, profile: object) -> NormalizedShopperProfile:
        return adapt_profile(profile, self.profile_adapter)

    def _candidate_records(
        self,
        profile: NormalizedShopperProfile,
        candidate_limit: int,
        diagnostics: dict | None = None,
    ) -> tuple[list[_Candidate], tuple[ConstraintView, ...]]:
        route_limit = min(500, max(100, int(candidate_limit)))
        retrieval = self.retriever.retrieve_with_routes(profile, route_limit=route_limit)
        constraints = profile.constraints
        rows: list[_Candidate] = []
        if diagnostics is not None:
            diagnostics["route_sizes"] = tuple(
                (name, len(values)) for name, values in retrieval.routes.items()
            )
            diagnostics["candidate_pool_size"] = len(retrieval.scores)

        for parent_asin, rrf_score in retrieval.scores.items():
            product = self.catalog.products.get(parent_asin)
            if product is None:
                continue
            relations = tuple(constraint_relation(product, item) for item in constraints)
            negative_violations = sum(
                constraint.confidence
                for constraint, relation in zip(constraints, relations)
                if constraint.polarity == "exclude" and constraint.strength == "hard" and relation == 1
            )
            soft_negative_violations = sum(
                constraint.confidence
                for constraint, relation in zip(constraints, relations)
                if constraint.polarity == "exclude" and constraint.strength != "hard" and relation == 1
            )
            hard_violations = sum(
                constraint.confidence
                for constraint, relation in zip(constraints, relations)
                if constraint.polarity == "include"
                and constraint.strength == "hard"
                and relation == -1
            )
            hard_matches = sum(
                constraint.confidence
                for constraint, relation in zip(constraints, relations)
                if constraint.polarity == "include"
                and constraint.strength == "hard"
                and relation == 1
            )
            soft_matches = sum(
                constraint.confidence
                for constraint, relation in zip(constraints, relations)
                if constraint.polarity == "include"
                and constraint.strength != "hard"
                and relation == 1
            )
            exact_matches = sum(
                constraint.confidence
                for constraint, relation in zip(constraints, relations)
                if constraint.polarity == "include"
                and relation == 1
                and _contains_phrase(product.searchable_text, constraint.value)
            )
            category_match = (
                1.0
                if profile.category and _contains_all(product.categories, profile.category)
                else 0.0
            )
            profile_matches = sum(
                1.0
                for tag in profile.preference_tags
                if tag and _contains_all(product.searchable_text, tag)
            )

            # RRF is the main within-tier signal.  Smaller boosts are combined
            # with it so a soft preference or weak prior can actually resolve a
            # close retrieval result without overruling hard constraints.
            relevance = (
                100.0 * rrf_score
                + 2.0 * exact_matches
                + 0.75 * category_match
                + 0.50 * soft_matches
                - 0.50 * soft_negative_violations
                + 0.05 * profile_matches
            )
            sort_key = (
                round(negative_violations, 8),
                round(hard_violations, 8),
                -round(hard_matches, 8),
                -round(relevance, 12),
                -product.rating_number,
                -(product.average_rating or 0.0),
                parent_asin,
            )
            rows.append(_Candidate(parent_asin, sort_key, relations))
        return rows, constraints

    @staticmethod
    def _violates_negative(candidate: _Candidate, constraints: tuple[ConstraintView, ...]) -> bool:
        return any(
            constraint.polarity == "exclude"
            and constraint.strength == "hard"
            and constraint.confidence >= 0.9
            and relation == 1
            for constraint, relation in zip(constraints, candidate.relations)
        )

    @staticmethod
    def _violates_hard_filter(
        candidate: _Candidate,
        constraints: tuple[ConstraintView, ...],
        active_filter_indexes: set[int],
    ) -> bool:
        return any(
            index in active_filter_indexes and candidate.relations[index] == -1
            for index in active_filter_indexes
        )

    def _ranked_candidates(
        self,
        profile: NormalizedShopperProfile,
        candidate_limit: int = 200,
        diagnostics: dict | None = None,
    ) -> list[str]:
        records, constraints = self._candidate_records(profile, candidate_limit, diagnostics)
        negative_safe = [
            candidate
            for candidate in records
            if not self._violates_negative(candidate, constraints)
        ]
        hard_filter_indexes = {
            index
            for index, constraint in enumerate(constraints)
            if constraint.polarity == "include"
            and constraint.strength == "hard"
            and constraint.attribute in STRICT_STRUCTURED_ATTRIBUTES
            and constraint.confidence >= 0.9
        }

        def survivors(active_indexes: set[int]) -> list[_Candidate]:
            return [
                candidate
                for candidate in negative_safe
                if not self._violates_hard_filter(candidate, constraints, active_indexes)
            ]

        active_filters = set(hard_filter_indexes)
        chosen = survivors(active_filters)
        # Relax the lowest-confidence (then oldest) hard filter first until the
        # reranking pool is broad enough.  The relaxed relation remains a penalty.
        relaxation_order = sorted(
            hard_filter_indexes,
            key=lambda index: (
                constraints[index].confidence,
                constraints[index].source_turn,
                constraints[index].constraint_id or "",
                index,
            ),
        )
        while len(chosen) < 50 and relaxation_order:
            relaxed_index = relaxation_order.pop(0)
            active_filters.remove(relaxed_index)
            if diagnostics is not None:
                diagnostics.setdefault("relaxed_hard_constraints", []).append(
                    constraints[relaxed_index].constraint_id
                    or f"{constraints[relaxed_index].attribute}:{constraints[relaxed_index].value}"
                )
            chosen = survivors(active_filters)

        chosen.sort(key=lambda candidate: candidate.sort_key)
        result = [candidate.parent_asin for candidate in chosen]

        # Empty/bare queries and tiny retrieval unions still return the best ten
        # valid products available.  This fallback is deterministic and built once.
        target_pool = min(max(10, int(candidate_limit)), len(self.catalog.products))
        if len(result) < target_pool:
            seen = set(result)
            for parent_asin in self.catalog.fallback(len(self.catalog.products)):
                if parent_asin in seen:
                    continue
                product = self.catalog.products[parent_asin]
                if any(
                    constraint.polarity == "exclude"
                    and constraint.strength == "hard"
                    and constraint.confidence >= 0.9
                    and constraint_relation(product, constraint) == 1
                    for constraint in constraints
                ):
                    continue
                result.append(parent_asin)
                seen.add(parent_asin)
                if len(result) >= target_pool:
                    break
        return result

    @staticmethod
    def _validated_output(
        ranked_ids: list[str],
        valid_ids: set[str],
        limit: int,
    ) -> list[dict[str, str]]:
        seen: set[str] = set()
        output: list[dict[str, str]] = []
        for parent_asin in ranked_ids:
            if parent_asin in seen or parent_asin not in valid_ids:
                continue
            seen.add(parent_asin)
            output.append({"parent_asin": parent_asin})
            if len(output) >= limit:
                break
        return output

    def rank(self, profile: object, top_k: int = 10) -> list[dict[str, str]]:
        try:
            requested = int(top_k)
        except (TypeError, ValueError):
            requested = 10
        limit = min(10, max(0, requested))
        if limit == 0:
            return []
        canonical = self._adapt(profile)
        ranked_ids = self._ranked_candidates(canonical)
        return self._validated_output(ranked_ids, self.catalog.valid_ids, limit)

    def rank_detailed(self, profile: object, top_k: int = 10) -> RankingResult:
        """Return ranking diagnostics for tests/demo code, outside Agent.respond."""

        try:
            requested = int(top_k)
        except (TypeError, ValueError):
            requested = 10
        limit = min(10, max(0, requested))
        canonical = self._adapt(profile)
        diagnostics: dict = {}
        ranked_ids = self._ranked_candidates(canonical, diagnostics=diagnostics)
        recommendations = self._validated_output(ranked_ids, self.catalog.valid_ids, limit)
        return RankingResult(
            recommendations=tuple(recommendations),
            candidate_pool_size=int(diagnostics.get("candidate_pool_size", 0)),
            route_sizes=tuple(diagnostics.get("route_sizes", ())),
            relaxed_hard_constraints=tuple(diagnostics.get("relaxed_hard_constraints", ())),
        )

    def attribute_stats(self, profile: object, candidate_limit: int = 100) -> dict:
        limit = max(1, int(candidate_limit))
        canonical = self._adapt(profile)
        candidate_ids = self._ranked_candidates(canonical, candidate_limit=max(200, limit))[:limit]
        return self._attribute_stats_for_candidates(canonical, candidate_ids)

    def rank_with_stats(
        self, profile: object, top_k: int = 10, candidate_limit: int = 100
    ) -> tuple[list[dict[str, str]], dict]:
        """One search for recommendations and question-policy context.

        Shayna owns question selection; Rhea can pass the returned statistics to
        her policy after updating the profile. Statistics are never API payload.
        No per-session mutable cache is introduced.
        """
        try:
            requested = int(top_k)
        except (TypeError, ValueError):
            requested = 10
        limit = min(10, max(0, requested))
        stats_limit = max(1, int(candidate_limit))
        canonical = self._adapt(profile)
        ranked_ids = self._ranked_candidates(canonical, candidate_limit=max(200, stats_limit))
        recommendations = self._validated_output(ranked_ids, self.catalog.valid_ids, limit) if limit else []
        stats = self._attribute_stats_for_candidates(canonical, ranked_ids[:stats_limit])
        return recommendations, stats

    def _attribute_stats_for_candidates(
        self, canonical: NormalizedShopperProfile, candidate_ids: list[str]
    ) -> dict:
        pool_size = len(candidate_ids)
        attributes: dict[str, dict] = {}
        for attribute in ALLOWED_STATS_ATTRIBUTES:
            if (
                attribute in canonical.asked_attributes
                or attribute in canonical.no_preference_attributes
                or attribute in canonical.exhausted_attributes
            ):
                continue
            counts: Counter[str] = Counter()
            uncertain_counts: Counter[str] = Counter()
            covered_products = 0
            for parent_asin in candidate_ids:
                product = self.catalog.products[parent_asin]
                values = set(product.attribute_values(attribute))
                if not values:
                    continue
                covered_products += 1
                counts.update(values)
                if attribute == "material":
                    # These products have some known material, but must still
                    # survive an answer about a specifically ambiguous material.
                    # Fully missing products are already counted below.
                    uncertain_counts.update(set(getattr(product, "uncertain_materials", ())) - values)
            mentions = sum(counts.values())
            if pool_size == 0 or covered_products == 0 or mentions == 0:
                continue
            probabilities = [count / mentions for count in counts.values()]
            entropy = -sum(probability * math.log2(probability) for probability in probabilities)
            expected_remaining = min(
                float(pool_size),
                # Missing metadata survives every possible answer. Value mention
                # frequency is a documented approximation of answer probability.
                pool_size - covered_products
                + sum(count * (count + uncertain_counts[value]) for value, count in counts.items()) / mentions,
            )
            coverage = covered_products / pool_size
            question_value = coverage * (1.0 - expected_remaining / pool_size)
            top_values = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
            attributes[attribute] = {
                "coverage": round(coverage, 6),
                "entropy": round(entropy, 6),
                "expected_remaining": round(expected_remaining, 6),
                "question_value": round(max(0.0, question_value), 6),
                "top_values": [[value, count] for value, count in top_values],
            }
        return {"pool_size": pool_size, "attributes": attributes}

    def build_demo_evidence(
        self,
        profile: object,
        ranked_products: list[dict[str, str]],
    ) -> dict:
        from starter.evidence import build_demo_evidence

        return build_demo_evidence(
            profile,
            ranked_products,
            catalog=self.catalog,
            profile_adapter=self.profile_adapter,
        )

    def close(self) -> None:
        self.catalog.close()
