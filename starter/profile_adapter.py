from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, runtime_checkable

from starter.budget import parse_budget
from starter.catalog import flatten_text, normalize_text


_MISSING = object()


@dataclass(frozen=True)
class ConstraintView:
    """Canonical active constraint consumed by retrieval and ranking."""

    attribute: str
    value: str
    strength: str = "soft"
    polarity: str = "include"
    confidence: float = 1.0
    source_turn: int = 0
    active: bool = True
    constraint_id: str | None = None

    @property
    def normalized_value(self) -> str:
        if self.attribute == "budget":
            # Comparators carry meaning: <=60 and >=60 are not duplicates.
            return " ".join(self.value.casefold().split())
        return normalize_text(self.value)


@dataclass(frozen=True)
class NormalizedShopperProfile:
    """Stable search-side view of Shayna's profile.

    Ranker internals depend only on this type.  The original profile can be a
    mapping, dataclass, attrs/Pydantic-like object, or a team-defined object
    handled by a custom ``ProfileAdapter``.
    """

    category: str | None = None
    mission: str = ""
    use_case: str = ""
    query_terms: tuple[str, ...] = ()
    constraints: tuple[ConstraintView, ...] = ()
    preference_tags: tuple[str, ...] = ()
    asked_attributes: frozenset[str] = frozenset()
    no_preference_attributes: frozenset[str] = frozenset()
    exhausted_attributes: frozenset[str] = frozenset()


@runtime_checkable
class ProfileAdapter(Protocol):
    def adapt(self, profile: object) -> NormalizedShopperProfile:
        """Convert a team-owned profile into the ranker's canonical view."""


ProfileAdapterLike = ProfileAdapter | Callable[[object], NormalizedShopperProfile]


DEFAULT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "category": (
        "current_category",
        "active_category",
        "category",
        "target_category",
        "product_category",
        "product_type",
    ),
    "mission": ("current_mission", "active_mission", "mission", "shopping_mission"),
    "use_case": ("current_use_case", "active_use_case", "use_case", "useCase", "occasion"),
    "query_terms": (
        "active_query_terms",
        "current_query_terms",
        "query_terms",
        "search_terms",
        "keywords",
    ),
    "asked_attributes": ("asked_attributes", "attributes_asked", "asked"),
    "exhausted_attributes": ("exhausted_attributes", "answered_attributes", "completed_attributes"),
    "no_preference_attributes": (
        "no_preference_attributes",
        "no_preference",
        "no_preferences",
        "indifferent_attributes",
    ),
    "preference_tags": ("preference_tags", "profile_tags", "aggregate_preference_tags"),
}

DEFAULT_CONSTRAINT_ALIASES: dict[str, tuple[str, ...]] = {
    "attribute": ("attribute", "field", "name", "key", "type"),
    "value": ("value", "normalized_value", "phrase", "text", "term"),
    "strength": ("strength", "priority", "importance", "constraint_type"),
    "polarity": ("polarity", "include_exclude", "direction"),
    "confidence": ("confidence", "certainty", "score"),
    "source_turn": ("source_turn", "turn", "turn_index"),
    "active": ("active", "is_active", "enabled"),
    "status": ("status", "state"),
    "negated": ("negated", "is_negative", "exclude"),
    "constraint_id": ("constraint_id", "id", "uid"),
}

_STATE_CONTAINERS = ("active_state", "current_intent", "active_intent", "search_state")
_AGGREGATE_CONTAINERS = ("user_profile", "aggregate_profile", "personalization")
_GENERAL_CONSTRAINT_CONTAINERS = ("active_constraints", "constraints", "requirements")
_HARD_CONSTRAINT_CONTAINERS = ("hard_inclusions", "hard_constraints", "must_haves")
_SOFT_CONSTRAINT_CONTAINERS = ("soft_preferences", "preferences", "nice_to_haves")
_NEGATIVE_CONSTRAINT_CONTAINERS = (
    "hard_exclusions",
    "negative_constraints",
    "exclusions",
    "avoid",
)

_ATTRIBUTE_ALIASES = {
    "colour": "color",
    "price": "budget",
    "price_range": "budget",
    "maximum_price": "budget",
    "usage": "use_case",
    "occasion": "use_case",
    "product_type": "category",
    "features": "feature",
}


def _read_direct(source: object, name: str) -> object:
    if isinstance(source, Mapping):
        return source[name] if name in source else _MISSING
    try:
        return getattr(source, name)
    except (AttributeError, TypeError):
        return _MISSING


def _sources(profile: object) -> tuple[object, ...]:
    nested: list[object] = []
    seen = {id(profile)}
    for name in _STATE_CONTAINERS:
        value = _read_direct(profile, name)
        if value is _MISSING or value is None or id(value) in seen:
            continue
        seen.add(id(value))
        nested.append(value)
    # An explicitly active/current nested state wins over legacy root fields.
    return (*nested, profile)


def _read_first(sources: tuple[object, ...], aliases: tuple[str, ...], default: object = None) -> object:
    for source in sources:
        for alias in aliases:
            value = _read_direct(source, alias)
            if value is not _MISSING:
                return value
    return default


def _read_all(sources: tuple[object, ...], aliases: tuple[str, ...]) -> list[object]:
    values: list[object] = []
    seen: set[int] = set()
    for source in sources:
        for alias in aliases:
            value = _read_direct(source, alias)
            if value is _MISSING or value is None or id(value) in seen:
                continue
            seen.add(id(value))
            values.append(value)
    return values


def _as_sequence(value: object) -> list[object]:
    if value is None or value is _MISSING:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return list(value.values())
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=lambda item: (normalize_text(item), flatten_text(item)))
    try:
        return list(value)  # type: ignore[arg-type]
    except TypeError:
        return [value]


def _dedupe_strings(values: object) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in _as_sequence(values):
        value = flatten_text(raw).strip()
        key = normalize_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


def _attribute_set(value: object) -> frozenset[str]:
    if isinstance(value, Mapping):
        raw_values = [key for key, enabled in value.items() if enabled]
    else:
        raw_values = _as_sequence(value)
    return frozenset(
        _ATTRIBUTE_ALIASES.get(normalize_text(item).replace(" ", "_"), normalize_text(item).replace(" ", "_"))
        for item in raw_values
        if normalize_text(item)
    )


def _bool_value(value: object, default: bool) -> bool:
    if value is _MISSING or value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"false", "0", "no", "off", "inactive", "disabled", "replaced", "superseded"}:
            return False
        if lowered in {"true", "1", "yes", "on", "active", "enabled", "current"}:
            return True
    return bool(value)


def _confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return min(1.0, max(0.0, number))


def _integer(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _with_budget_operator(operator: str, text: str) -> str:
    """Avoid duplicating a compatible comparator already carried by the value.

    A complete stricter value is preserved (``<=`` plus ``under 60``); an
    operator that would reinterpret the bound or its endpoint is not chosen
    over the explicit value. Conflicting combinations remain unsupported by
    the budget parser and therefore receive the normal unknown relation.
    """
    combined = f"{operator} {text}"
    if parse_budget(combined) is not None:
        return combined
    existing = parse_budget(text)
    if existing is None:
        return combined
    if operator == "between":
        # Bare amounts also parse as approximate intervals, but they are not
        # complete range expressions and must not absorb an incomplete operator.
        lowered = text.casefold()
        explicit_range = any(token in lowered for token in ("between", " to ", " and ", "-", "\u2013", "\u2014"))
        if explicit_range and existing.lower is not None and existing.upper is not None:
            return text
        return combined
    expected = parse_budget(f"{operator} 1")
    if expected is None:
        return combined
    if expected.lower is None and existing.lower is None:
        if expected.upper_inclusive or not existing.upper_inclusive:
            return text
    elif expected.upper is None and existing.upper is None:
        if expected.lower_inclusive or not existing.lower_inclusive:
            return text
    elif (
        expected.lower == expected.upper
        and existing.lower == existing.upper
        and existing.lower_inclusive and existing.upper_inclusive
    ):
        return text
    return combined


class DefaultProfileAdapter:
    """Alias-tolerant adapter for mapping, dataclass, and object profiles.

    Extra aliases can be supplied without editing retrieval/ranking code.  A
    team with a materially different schema can instead pass its own adapter to
    ``Ranker(..., profile_adapter=...)``.
    """

    def __init__(
        self,
        *,
        field_aliases: Mapping[str, tuple[str, ...] | list[str]] | None = None,
        constraint_aliases: Mapping[str, tuple[str, ...] | list[str]] | None = None,
    ) -> None:
        self.field_aliases = dict(DEFAULT_FIELD_ALIASES)
        self.constraint_aliases = dict(DEFAULT_CONSTRAINT_ALIASES)
        for target, aliases in (field_aliases or {}).items():
            self.field_aliases[target] = tuple(aliases) + self.field_aliases.get(target, ())
        for target, aliases in (constraint_aliases or {}).items():
            self.constraint_aliases[target] = tuple(aliases) + self.constraint_aliases.get(target, ())

    def _constraint_value(self, raw: object, name: str, default: object = None) -> object:
        aliases = self.constraint_aliases.get(name, (name,))
        return _read_first((raw,), aliases, default)

    def _is_constraint_record(self, raw: Mapping[object, object]) -> bool:
        names = {
            alias
            for field in ("attribute", "value", "strength", "polarity", "active", "status")
            for alias in self.constraint_aliases.get(field, ())
        }
        return any(name in raw for name in names)

    def _expand_constraint_container(self, container: object) -> list[object]:
        if isinstance(container, Mapping) and self._is_constraint_record(container):
            return [container]
        if isinstance(container, Mapping) and not self._is_constraint_record(container):
            expanded: list[object] = []
            for attribute, raw_value in container.items():
                values = (_as_sequence(raw_value)
                          if isinstance(raw_value, (list, tuple, set, frozenset)) else [raw_value])
                for value in values:
                    if isinstance(value, Mapping):
                        record = dict(value)
                        record.setdefault("attribute", attribute)
                        expanded.append(record)
                    else:
                        expanded.append({"attribute": attribute, "value": value})
            return expanded
        return _as_sequence(container)

    def _budget_value(self, raw: object, value: object) -> str:
        """Preserve supplied numeric operators/ranges without guessing intent."""
        structured_value = value is not _MISSING and value is not None and not isinstance(
            value, (str, int, float, bool, list, tuple, set, frozenset)
        )
        sources = (value, raw) if structured_value else (raw,)
        lower = _read_first(sources, ("min", "minimum", "lower", "min_price"), _MISSING)
        upper = _read_first(sources, ("max", "maximum", "upper", "max_price"), _MISSING)
        operator = str(_read_first(sources, ("operator", "comparison", "op"), "") or "").strip().lower()
        operator = {"lt": "<", "lte": "<=", "le": "<=", "gt": ">", "gte": ">=",
                    "ge": ">=", "eq": "=", "range": "between"}.get(operator, operator)
        parts: list[str] = []
        if lower is not _MISSING and lower is not None:
            inclusive = _bool_value(_read_first(sources, ("lower_inclusive", "min_inclusive"), True), True)
            parts.append(f"{'>=' if inclusive else '>'} {flatten_text(lower)}")
        if upper is not _MISSING and upper is not None:
            inclusive = _bool_value(_read_first(sources, ("upper_inclusive", "max_inclusive"), True), True)
            parts.append(f"{'<=' if inclusive else '<'} {flatten_text(upper)}")
        if parts:
            text = " and ".join(parts)
        elif isinstance(value, (list, tuple)) and len(value) == 2 and operator in {"", "between"}:
            text = f"between {flatten_text(value[0])} and {flatten_text(value[1])}"
        else:
            amount = _read_first((value,), ("amount", "limit", "value"), _MISSING)
            amount = value if amount is _MISSING else amount
            text = "" if amount is _MISSING else flatten_text(amount).strip()
            if operator and operator not in {"include", "exclude", "positive", "negative", "avoid", "not"}:
                text = _with_budget_operator(operator, text)
        currency = _read_first(sources, ("currency", "currency_code"), "")
        return f"{flatten_text(currency)} {text}".strip()

    def _constraint(
        self,
        raw: object,
        *,
        default_strength: str = "soft",
        default_polarity: str = "include",
    ) -> ConstraintView | None:
        if isinstance(raw, str):
            raw = {"attribute": "feature", "value": raw}

        status = str(self._constraint_value(raw, "status", "") or "").strip().lower()
        active = _bool_value(self._constraint_value(raw, "active", True), True)
        if status in {"inactive", "replaced", "superseded", "removed", "expired"}:
            active = False
        if not active:
            return None

        attribute = normalize_text(self._constraint_value(raw, "attribute", "feature")).replace(" ", "_")
        attribute = _ATTRIBUTE_ALIASES.get(attribute, attribute or "feature")
        raw_value = self._constraint_value(raw, "value", _MISSING)
        value = (self._budget_value(raw, raw_value) if attribute == "budget"
                 else "" if raw_value is _MISSING else flatten_text(raw_value).strip())
        if not normalize_text(value):
            return None

        strength_raw = str(self._constraint_value(raw, "strength", default_strength) or default_strength).lower()
        strength = "hard" if strength_raw in {"hard", "required", "must", "mandatory"} else "soft"

        polarity_value = self._constraint_value(raw, "polarity", _MISSING)
        if polarity_value is _MISSING:
            legacy_operator = _read_direct(raw, "operator")
            # Older profiles used operator for polarity; numeric comparisons are
            # handled only by the budget adapter, never by this compatibility alias.
            polarity_value = legacy_operator if legacy_operator in (
                "include", "exclude", "excluded", "positive", "negative", "avoid", "must_not", "not"
            ) else default_polarity
        polarity_raw = str(polarity_value or default_polarity).lower()
        negated = _bool_value(self._constraint_value(raw, "negated", False), False)
        polarity = (
            "exclude"
            if negated or polarity_raw in {"exclude", "excluded", "negative", "avoid", "must_not", "not"}
            else "include"
        )

        raw_id = self._constraint_value(raw, "constraint_id", None)
        constraint_id = str(raw_id).strip() if raw_id not in (None, "") else None
        return ConstraintView(
            attribute=attribute,
            value=value,
            strength=strength,
            polarity=polarity,
            confidence=_confidence(self._constraint_value(raw, "confidence", 1.0)),
            source_turn=_integer(self._constraint_value(raw, "source_turn", 0)),
            active=True,
            constraint_id=constraint_id,
        )

    def _constraints(self, sources: tuple[object, ...]) -> tuple[ConstraintView, ...]:
        groups = (
            (_GENERAL_CONSTRAINT_CONTAINERS, "soft", "include"),
            (_HARD_CONSTRAINT_CONTAINERS, "hard", "include"),
            (_SOFT_CONSTRAINT_CONTAINERS, "soft", "include"),
            (_NEGATIVE_CONSTRAINT_CONTAINERS, "hard", "exclude"),
        )
        if _read_first(sources, ("active_constraints",), _MISSING) is not _MISSING:
            # A supplied active collection is authoritative, including an empty
            # collection. Do not resurrect historical or typed legacy copies.
            groups = ((("active_constraints",), "soft", "include"),)
        result: list[ConstraintView] = []
        positions: dict[tuple[str, str, str], int] = {}
        for aliases, strength, polarity in groups:
            for container in _read_all(sources, aliases):
                for raw in self._expand_constraint_container(container):
                    constraint = self._constraint(
                        raw,
                        default_strength=strength,
                        default_polarity=polarity,
                    )
                    if constraint is None:
                        continue
                    key = (constraint.attribute, constraint.normalized_value, constraint.polarity)
                    if key not in positions:
                        positions[key] = len(result)
                        result.append(constraint)
                        continue
                    # The same slot/value is sometimes exposed in both a generic
                    # and a typed collection.  Retain one semantic constraint,
                    # preferring hard, confident, and recent metadata.
                    index = positions[key]
                    existing = result[index]
                    priority = (
                        constraint.strength == "hard",
                        constraint.confidence,
                        constraint.source_turn,
                    )
                    existing_priority = (
                        existing.strength == "hard",
                        existing.confidence,
                        existing.source_turn,
                    )
                    if priority > existing_priority:
                        result[index] = constraint
        resolved: dict[tuple[str, str], ConstraintView] = {}
        order: list[tuple[str, str]] = []
        for constraint in result:
            key = (constraint.attribute, constraint.normalized_value)
            if key not in resolved:
                resolved[key] = constraint
                order.append(key)
                continue
            existing = resolved[key]
            priority = (
                constraint.source_turn,
                constraint.strength == "hard",
                constraint.confidence,
                constraint.polarity == "exclude",
            )
            existing_priority = (
                existing.source_turn,
                existing.strength == "hard",
                existing.confidence,
                existing.polarity == "exclude",
            )
            if priority > existing_priority:
                resolved[key] = constraint
        return tuple(resolved[key] for key in order)

    def adapt(self, profile: object) -> NormalizedShopperProfile:
        if isinstance(profile, NormalizedShopperProfile):
            return profile
        if profile is None:
            return NormalizedShopperProfile()

        sources = _sources(profile)
        # Named active/current containers are complete intent snapshots, not
        # patches. Partial-update schemas must supply an explicit custom adapter.
        state_sources = sources[:1] if len(sources) > 1 else sources
        no_preference = _attribute_set(
            _read_first(
                state_sources,
                self.field_aliases["no_preference_attributes"],
                (),
            )
        )
        exhausted = _attribute_set(
            _read_first(state_sources, self.field_aliases["exhausted_attributes"], ())
        )
        constraints = tuple(
            constraint
            for constraint in self._constraints(state_sources)
            if constraint.attribute not in no_preference
        )

        aggregate_sources: list[object] = []
        for container in _AGGREGATE_CONTAINERS:
            aggregate_sources.extend(_read_all(sources, (container,)))
        preference_values: list[object] = []
        for source in (*sources, *aggregate_sources):
            value = _read_first((source,), self.field_aliases["preference_tags"], _MISSING)
            if value is not _MISSING:
                preference_values.extend(_as_sequence(value))

        category_raw = _read_first(state_sources, self.field_aliases["category"], None)
        category = flatten_text(category_raw).strip() if category_raw not in (None, "") else None
        return NormalizedShopperProfile(
            category=category,
            mission=flatten_text(_read_first(state_sources, self.field_aliases["mission"], "")).strip(),
            use_case=flatten_text(_read_first(state_sources, self.field_aliases["use_case"], "")).strip(),
            query_terms=_dedupe_strings(
                _read_first(state_sources, self.field_aliases["query_terms"], ())
            ),
            constraints=constraints,
            preference_tags=_dedupe_strings(preference_values),
            asked_attributes=_attribute_set(
                _read_first(sources, self.field_aliases["asked_attributes"], ())
            ),
            no_preference_attributes=no_preference,
            exhausted_attributes=exhausted,
        )


def adapt_profile(
    profile: object,
    adapter: ProfileAdapterLike | None = None,
) -> NormalizedShopperProfile:
    """Adapt a profile and validate the custom-adapter boundary."""

    selected: ProfileAdapterLike = adapter or DefaultProfileAdapter()
    if hasattr(selected, "adapt"):
        result = selected.adapt(profile)  # type: ignore[union-attr]
    else:
        result = selected(profile)  # type: ignore[operator]
    if not isinstance(result, NormalizedShopperProfile):
        raise TypeError("profile adapter must return NormalizedShopperProfile")
    return result
