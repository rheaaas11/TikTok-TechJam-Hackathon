"""Conversation-state primitives for the ShopSense shopping copilot.

This module deliberately has no catalog or evaluator dependency.  It turns a
customer's message into a structured Product DNA profile that the retrieval
layer can consume later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Literal


Attribute = Literal[
    "category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"
]
ConstraintStrength = Literal["hard", "soft"]
ConstraintPolarity = Literal["include", "exclude"]
IntentMode = Literal["buying", "browsing", "unclear"]

ALLOWED_ASK_ATTRIBUTES: frozenset[str] = frozenset(
    {"category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"}
)

COLOR_WORDS = frozenset(
    {"black", "white", "blue", "red", "pink", "green", "brown", "gray", "grey", "purple", "yellow", "orange"}
)
MATERIAL_WORDS = frozenset(
    {"cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric", "linen", "denim"}
)
STYLE_WORDS = frozenset(
    {"casual", "formal", "cute", "elegant", "minimal", "comfortable", "sporty", "classic", "warm", "waterproof"}
)
USE_CASE_WORDS = frozenset(
    {"running", "hiking", "walking", "gym", "work", "office", "winter", "outdoor", "travel", "wedding", "beach", "party"}
)
FEATURE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bwater[ -]?resistant\b", re.I), "water resistant"),
    (re.compile(r"\bbreathable\b", re.I), "breathable"),
    (re.compile(r"\blightweight\b", re.I), "lightweight"),
    (re.compile(r"\barch support\b", re.I), "arch support"),
    (re.compile(r"\bwide(?:[- ]fit)?\b", re.I), "wide fit"),
)
CATEGORY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:ankle )?boots?\b", re.I), "boots"),
    (re.compile(r"\bsneakers?\b", re.I), "sneakers"),
    (re.compile(r"\bshoes?\b", re.I), "shoes"),
    (re.compile(r"\bsandals?\b", re.I), "sandals"),
    (re.compile(r"\bheels?\b", re.I), "heels"),
    (re.compile(r"\bdresses?\b", re.I), "dress"),
    (re.compile(r"\b(?:t-)?shirts?\b", re.I), "shirt"),
    (re.compile(r"\bjackets?\b", re.I), "jacket"),
    (re.compile(r"\bcoats?\b", re.I), "coat"),
    (re.compile(r"\b(?:jeans|pants|trousers)\b", re.I), "pants"),
    (re.compile(r"\b(?:shorts|skirt|leggings)\b", re.I), "bottoms"),
    (re.compile(r"\bhoodies?\b", re.I), "hoodie"),
    (re.compile(r"\bsweaters?\b", re.I), "sweater"),
    (re.compile(r"\bblazers?\b", re.I), "blazer"),
    (re.compile(r"\b(?:handbags?|purses?)\b", re.I), "handbag"),
)

HARD_SIGNAL_RE = re.compile(
    r"\b(?:must|need|cannot|can't|can not|no |not |without|avoid|only|under|below|less than|at most|key requirement|what matters)\b",
    re.I,
)
OVERRIDE_RE = re.compile(r"\b(?:actually|instead|ignore (?:my |the )?(?:earlier|previous)|change my mind|rather)\b", re.I)
NO_PREFERENCE_RE = re.compile(
    r"\b(?:no preference|not preference|don't have (?:a[n]? )?preference|do not have (?:a[n]? )?preference)(?: for)?\s*(category|material|color|size|style|brand|budget|feature|use case|use_case|other)?",
    re.I,
)
BUDGET_RE = re.compile(
    r"\b(?:under|below|less than|at most|maximum|max|budget(?: of| around| is)?|up to)\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)",
    re.I,
)
RANGE_BUDGET_RE = re.compile(
    r"\bbetween\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)\s*(?:and|to|-)\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)",
    re.I,
)
AROUND_BUDGET_RE = re.compile(r"\b(?:around|about|roughly)\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)", re.I)
SIZE_RE = re.compile(r"\b(?:size\s*\d{1,2}(?:\.\d)?|\d{1,2}\s*(?:w|waist)|small|medium|large|xl|xxl)\b", re.I)
NEGATIVE_RE = re.compile(r"\b(?:no|not|without|avoid|cannot wear|can't wear)\s+([a-z][a-z0-9 -]{1,35})", re.I)
BRAND_RE = re.compile(r"\b(?:brand|by|from)\s+(?:is\s+)?([A-Za-z][A-Za-z0-9&' -]{1,30})", re.I)
USE_CASE_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blong walks?\b", re.I), "walking"),
    (re.compile(r"\bdaily commute\b", re.I), "commute"),
    (re.compile(r"\bdate night\b", re.I), "date night"),
)
WORD_RE = re.compile(r"[a-z0-9]+", re.I)


@dataclass(frozen=True)
class Constraint:
    """One active or superseded user preference."""

    attribute: Attribute
    value: str
    strength: ConstraintStrength
    polarity: ConstraintPolarity
    source_turn: int
    confidence: float = 1.0
    active: bool = True


@dataclass(frozen=True)
class ShopperProfile:
    """Current Product DNA for one evaluator session."""

    session_id: str
    user_profile: dict
    turn: int = 0
    intent_mode: IntentMode = "unclear"
    constraints: tuple[Constraint, ...] = ()
    asked_attributes: frozenset[str] = frozenset()
    no_preference_attributes: frozenset[str] = frozenset()
    last_asked_attribute: str | None = None
    messages: tuple[str, ...] = ()
    change_log: tuple[str, ...] = ()

    @property
    def active_constraints(self) -> tuple[Constraint, ...]:
        return tuple(constraint for constraint in self.constraints if constraint.active)

    @property
    def active_attributes(self) -> frozenset[str]:
        return frozenset(constraint.attribute for constraint in self.active_constraints)

    @property
    def query_terms(self) -> tuple[str, ...]:
        """Terms intended for Leon's retrieval module, without negative terms."""
        values: list[str] = []
        for constraint in self.active_constraints:
            if constraint.polarity == "include":
                values.extend(_normalised_terms(constraint.value))
        return tuple(dict.fromkeys(values))


def new_profile(session_id: str, user_profile: dict) -> ShopperProfile:
    """Create clean per-session state after the official ``reset`` call."""
    return ShopperProfile(session_id=session_id, user_profile=dict(user_profile))


def _normalised_terms(value: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(value) if len(token) > 1]


def _attribute_for_value(value: str) -> Attribute:
    lowered = value.lower()
    if any(word in lowered for word in MATERIAL_WORDS):
        return "material"
    if any(word in lowered.split() for word in COLOR_WORDS):
        return "color"
    if any(pattern.search(lowered) for pattern, _ in CATEGORY_PATTERNS):
        return "category"
    if any(word in lowered for word in USE_CASE_WORDS):
        return "use_case"
    if any(word in lowered for word in STYLE_WORDS):
        return "style"
    return "feature"


def _constraint_strength(message: str, attribute: Attribute) -> ConstraintStrength:
    if attribute in {"category", "budget", "size"}:
        return "hard"
    if re.search(r"\b(?:must|cannot|can't|can not|without|avoid|only|key requirement|what matters)\b", message, re.I):
        return "hard"
    return "soft"


def _trim_negative_value(value: str) -> str:
    value = re.split(r"\b(?:and|but|for|because|please)\b|[.;,:!?]", value, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\s+", " ", value).strip()


def _trim_brand(value: str) -> str:
    """Keep a brand mention bounded to its phrase rather than the whole request."""
    value = re.split(r"\b(?:and|but|for|with|under|below|between|around|about|in)\b|[.;,:!?]", value, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\s+", " ", value).strip().lower()


def extract_constraints(message: str, turn: int) -> tuple[Constraint, ...]:
    """Extract lightweight, deterministic shopping constraints from one message.

    The function intentionally favours precision over clever guessing.  V2 can
    swap this extractor for a model-assisted parser behind the same interface.
    """
    lowered = message.lower()
    result: list[Constraint] = []
    negative_values: list[str] = []

    for match in NEGATIVE_RE.finditer(message):
        value = _trim_negative_value(match.group(1))
        if value and "preference" not in value.lower():
            negative_values.append(value.lower())
            result.append(
                Constraint(
                    attribute=_attribute_for_value(value),
                    value=value.lower(),
                    strength="hard",
                    polarity="exclude",
                    source_turn=turn,
                )
            )

    for match in BUDGET_RE.finditer(message):
        value = match.group(1)
        result.append(Constraint("budget", f"under {value}", "hard", "include", turn))

    for match in RANGE_BUDGET_RE.finditer(message):
        result.append(Constraint("budget", f"between {match.group(1)} and {match.group(2)}", "hard", "include", turn))

    for match in AROUND_BUDGET_RE.finditer(message):
        result.append(Constraint("budget", f"around {match.group(1)}", "hard", "include", turn))

    for match in SIZE_RE.finditer(message):
        value = match.group(0).lower()
        result.append(Constraint("size", value, "hard", "include", turn))

    for pattern, category in CATEGORY_PATTERNS:
        if pattern.search(message) and not any(category in value for value in negative_values):
            result.append(Constraint("category", category, "hard", "include", turn))

    for color in COLOR_WORDS:
        if re.search(rf"\b{re.escape(color)}\b", lowered) and not any(color in value for value in negative_values):
            result.append(
                Constraint("color", color, _constraint_strength(message, "color"), "include", turn)
            )

    for material in MATERIAL_WORDS:
        if re.search(rf"\b{re.escape(material)}\b", lowered) and not any(material in value for value in negative_values):
            result.append(
                Constraint("material", material, _constraint_strength(message, "material"), "include", turn)
            )

    for pattern, feature in FEATURE_PATTERNS:
        if pattern.search(message) and not any(feature in value for value in negative_values):
            result.append(Constraint("feature", feature, _constraint_strength(message, "feature"), "include", turn))

    for pattern, use_case in USE_CASE_PHRASES:
        if pattern.search(message):
            result.append(Constraint("use_case", use_case, _constraint_strength(message, "use_case"), "include", turn, 0.95))

    for style in STYLE_WORDS:
        if re.search(rf"\b{re.escape(style)}\b", lowered):
            result.append(
                Constraint("style", style, _constraint_strength(message, "style"), "include", turn)
            )

    for use_case in USE_CASE_WORDS:
        if re.search(rf"\b{re.escape(use_case)}\b", lowered):
            result.append(
                Constraint("use_case", use_case, _constraint_strength(message, "use_case"), "include", turn)
            )

    for match in BRAND_RE.finditer(message):
        brand = _trim_brand(match.group(1))
        if brand and brand not in {"a", "an", "the", "my", "this", "that"}:
            result.append(Constraint("brand", brand, "soft", "include", turn, 0.85))

    # Keep one copy of each extracted constraint from a single message.
    unique: list[Constraint] = []
    seen: set[tuple[str, str, str]] = set()
    for constraint in result:
        key = (constraint.attribute, constraint.value, constraint.polarity)
        if key not in seen:
            seen.add(key)
            unique.append(constraint)
    return tuple(unique)


def detect_intent(message: str, existing: IntentMode) -> IntentMode:
    """Classify a message as a precise purchase, exploratory browse, or unclear."""
    lowered = message.lower()
    if any(phrase in lowered for phrase in ("still exploring", "browse", "inspiration", "not sure", "something nice")):
        return "browsing"
    constraints = extract_constraints(message, turn=1)
    explicit_category = any(item.attribute == "category" and item.polarity == "include" for item in constraints)
    specific_count = len({item.attribute for item in constraints if item.polarity == "include"})
    if explicit_category and (specific_count >= 2 or HARD_SIGNAL_RE.search(message)):
        return "buying"
    if explicit_category:
        return "browsing" if existing == "browsing" else "unclear"
    return existing


def _deactivate_conflicts(
    existing: tuple[Constraint, ...], additions: tuple[Constraint, ...], broad_override: bool
) -> tuple[tuple[Constraint, ...], list[str]]:
    """Deactivate stale constraints while preserving an auditable history."""
    addition_attributes = {item.attribute for item in additions}
    updated: list[Constraint] = []
    changes: list[str] = []
    single_value_attributes = {"category", "color", "material", "size", "budget"}
    for constraint in existing:
        replace_same_attribute = (
            constraint.active
            and constraint.attribute in addition_attributes
            and constraint.attribute in single_value_attributes
        )
        replace_soft_on_override = broad_override and constraint.active and constraint.strength == "soft"
        if replace_same_attribute or replace_soft_on_override:
            updated.append(replace(constraint, active=False))
            changes.append(f"turn {constraint.source_turn} {constraint.attribute}='{constraint.value}' deactivated")
        else:
            updated.append(constraint)
    return tuple(updated), changes


def update_profile(profile: ShopperProfile, user_message: str, turn: int) -> ShopperProfile:
    """Apply one customer message to a profile without making retrieval decisions."""
    if turn < 1:
        raise ValueError("turn must be at least 1")
    if not user_message.strip():
        return replace(profile, turn=turn, messages=profile.messages + (user_message,))

    no_preference = NO_PREFERENCE_RE.search(user_message)
    no_preference_attributes = set(profile.no_preference_attributes)
    if no_preference:
        requested = no_preference.group(1)
        attribute = (requested or profile.last_asked_attribute or "other").replace(" ", "_")
        if attribute == "use_case":
            attribute = "use_case"
        if attribute in ALLOWED_ASK_ATTRIBUTES:
            no_preference_attributes.add(attribute)

    additions = extract_constraints(user_message, turn)
    # A boundary answer such as "no preference for material" is not a positive
    # material requirement just because it contains the word "material".
    if no_preference:
        additions = tuple(
            item
            for item in additions
            if not (item.attribute == attribute and item.polarity == "include")
        )
    override = bool(OVERRIDE_RE.search(user_message))
    broad_override = bool(
        re.search(r"\b(?:ignore (?:my |the )?(?:earlier|previous) (?:preferences?|requirements?)|start over)\b", user_message, re.I)
    )
    prior_constraints, changes = _deactivate_conflicts(profile.constraints, additions, broad_override)
    merged = list(prior_constraints)
    active_keys = {
        (item.attribute, item.value, item.polarity)
        for item in merged
        if item.active
    }
    for addition in additions:
        key = (addition.attribute, addition.value, addition.polarity)
        if key not in active_keys:
            merged.append(addition)
            active_keys.add(key)

    intent = detect_intent(user_message, profile.intent_mode)
    if override and additions:
        intent = "buying" if any(item.strength == "hard" for item in additions) else intent
    return replace(
        profile,
        turn=turn,
        intent_mode=intent,
        constraints=tuple(merged),
        no_preference_attributes=frozenset(no_preference_attributes),
        messages=profile.messages + (user_message,),
        change_log=profile.change_log + tuple(changes),
    )
