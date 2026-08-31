from __future__ import annotations

from collections import Counter
from typing import Mapping

from starter.catalog import TOKEN_RE, CatalogIndex, Product, normalize_text
from starter.profile_adapter import ProfileAdapterLike, adapt_profile
from starter.ranker import STRICT_STRUCTURED_ATTRIBUTES, constraint_relation
from starter.retrieval import profile_value


def _supporting_snippet(raw: str, value: str, limit: int = 240) -> str:
    """Return a verbatim local window containing every requested search token.

    Token normalization is mapped back to original offsets, so case folding and
    Unicode normalization cannot move the quote away from its source evidence.
    If the supporting span cannot fit, omit it instead of quoting an unrelated
    prefix or claiming that a partial match proves the complete clause.
    """
    required = set(normalize_text(value).split())
    if not required:
        return ""
    positions = [
        (token, match.start(), match.end())
        for match in TOKEN_RE.finditer(raw)
        for token in normalize_text(match.group()).split()
        if token in required
    ]
    counts: Counter[str] = Counter()
    left = 0
    best: tuple[int, int] | None = None
    for token, _, end in positions:
        counts[token] += 1
        while len(counts) == len(required):
            start = positions[left][1]
            if best is None or end - start < best[1] - best[0]:
                best = (start, end)
            previous = positions[left][0]
            counts[previous] -= 1
            if not counts[previous]:
                del counts[previous]
            left += 1
    if best is None or best[1] - best[0] > limit:
        return ""
    context = min(40, (limit - (best[1] - best[0])) // 2)
    start = max(0, best[0] - context)
    return raw[start:min(len(raw), start + limit)].strip()


def _snippet(product: Product, attribute: str, value: str, relation: int) -> tuple[str, str]:
    if attribute == "budget" and product.price is not None:
        return "price", f"{product.price:.2f}"

    preferred = {
        "category": ("categories",),
        "brand": ("store",),
        "material": ("title", "features", "details", "description"),
        "color": ("title", "features", "details", "description"),
        "size": ("title", "features", "details", "description"),
        "style": ("title", "features", "details", "description"),
    }.get(attribute, ("title", "features", "details", "description", "categories", "store"))
    for field in preferred:
        snippet = _supporting_snippet(product.raw_field(field), value)
        if snippet:
            return field, snippet

    # For a verified structured mismatch, show the known catalog field rather
    # than inventing an absence-based explanation.
    if relation == -1:
        for actual in product.attribute_values(attribute):
            for field in preferred:
                snippet = _supporting_snippet(product.raw_field(field), actual)
                if snippet:
                    return field, snippet
    return "", ""


def build_demo_evidence(
    profile: object,
    ranked_products: list[dict[str, str]],
    *,
    catalog: CatalogIndex | None = None,
    profile_adapter: ProfileAdapterLike | None = None,
) -> dict:
    """Build factual sidecar evidence outside the official response payload.

    Prefer ``Ranker.build_demo_evidence`` so the catalog and profile adapter are
    supplied explicitly.  Direct two-argument calls remain compatible when a
    demo profile exposes ``catalog``.
    """

    selected_catalog = catalog or profile_value(profile, "catalog")
    if not isinstance(selected_catalog, CatalogIndex):
        return {"products": {}}
    canonical = adapt_profile(profile, profile_adapter)
    evidence: dict[str, dict] = {}
    for item in ranked_products:
        parent_asin = str(item.get("parent_asin", "")) if isinstance(item, Mapping) else ""
        product = selected_catalog.products.get(parent_asin)
        if product is None:
            continue
        matched: list[dict] = []
        conflicts: list[dict] = []
        for constraint in canonical.constraints:
            relation = constraint_relation(product, constraint)
            if relation == 0:
                continue
            field, snippet = _snippet(product, constraint.attribute, constraint.value, relation)
            if not snippet:
                continue
            common = {
                "constraint_id": constraint.constraint_id,
                "attribute": constraint.attribute,
                "value": constraint.value,
                "source_turn": constraint.source_turn,
                "field": field,
                "snippet": snippet,
            }
            if constraint.polarity == "include" and relation == 1:
                matched.append(common)
            elif constraint.polarity == "exclude" and relation == 1:
                conflicts.append({**common, "reason": "contains_excluded_value"})
            elif (
                constraint.polarity == "include"
                and constraint.strength == "hard"
                and constraint.attribute in STRICT_STRUCTURED_ATTRIBUTES
                and relation == -1
            ):
                conflicts.append({**common, "reason": "known_structured_mismatch"})
        evidence[parent_asin] = {"matched": matched, "conflicts": conflicts}
    return {"products": evidence}
