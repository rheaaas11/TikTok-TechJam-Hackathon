"""Conversation-state primitives for the ShopSense shopping copilot.

This module deliberately has no catalog or evaluator dependency.  It turns a
customer's message into a structured Product DNA profile that the retrieval
layer can consume later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
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
    (re.compile(r"\bdress(?:es)?\b(?!\s+(?:shoes?|shirts?|pants|boots?))", re.I), "dress"),
    (re.compile(r"\b(?:t[ -]?)?shirts?\b", re.I), "shirt"),
    (re.compile(r"\bjackets?\b", re.I), "jacket"),
    (re.compile(r"\bcoats?\b", re.I), "coat"),
    (re.compile(r"\bjeans\b", re.I), "jeans"),
    (re.compile(r"\bpants\b", re.I), "pants"),
    (re.compile(r"\btrousers\b", re.I), "trousers"),
    (re.compile(r"\bshorts\b", re.I), "shorts"),
    (re.compile(r"\bskirts?\b", re.I), "skirt"),
    (re.compile(r"\bleggings?\b", re.I), "leggings"),
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
    r"\b(?:no preferences?|not preference|don't have (?:an? |any )?preferences?|do not have (?:an? |any )?preferences?)(?: for)?\s*(category|material|color|size|style|brand|budget|feature|use case|use_case|other)?",
    re.I,
)
EXHAUSTED_RE = re.compile(
    r"\b(?:no\s+|(?:do not|don't) have (?:an? |any )?)(?:additional|other|further) preferences?(?: for)?\s*(category|material|color|size|style|brand|budget|feature|use case|use_case|other)?",
    re.I,
)
BUDGET_RE = re.compile(
    r"\b(under|below|less than|at most|maximum|max|budget(?: of| is)?|up to|at least|over|above|more than)\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)",
    re.I,
)
RANGE_BUDGET_RE = re.compile(
    r"\bbetween\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)\s*(?:and|to|-)\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)",
    re.I,
)
AROUND_BUDGET_RE = re.compile(r"\b(?:around|about|roughly)\s*\$?\s*(\d{1,5}(?:\.\d{1,2})?)", re.I)
NON_MONEY_UNIT_RE = re.compile(
    r"\s*[-\u2013\u2014]?\s*(?:[\"\u2032\u2033%]|"
    r"(?:inches?|inch|millimeters?|millimetres?|centimeters?|centimetres?|meters?|metres?|"
    r"mm|cm|m|feet|foot|ft|ounces?|oz|pounds?|lbs?|kilograms?|kg|grams?|g|"
    r"hours?|hrs?|minutes?|mins?|seconds?|secs?|days?|weeks?|months?|years?|"
    r"stars?|ratings?|percent|degrees?)\b|out\s+of\s+\d|/\s*\d)",
    re.I,
)
NON_MONEY_CONTEXT_RE = re.compile(
    r"\b(?:fits?|sized?|sizing|rated?|rating|score|weighs?|weighing|weight|length|width|"
    r"height|circumference|lasts?|lasting|duration|ages?|aged)\s*(?:(?:is|of|at|for)\s*)?[:=]?\s*$", re.I
)
SIZE_RE = re.compile(r"\b(?:size\s*\d{1,2}(?:\.\d)?|\d{1,2}\s*(?:w|waist)|small|medium|large|xl|xxl)\b", re.I)
NEGATIVE_RE = re.compile(r"(?=\b(?:no|not|without|avoid|cannot wear|can't wear)\s+([a-z][a-z0-9 -]{1,100}))", re.I)
BRAND_RE = re.compile(r"\b(?:brand|by|from)\s+(?:is\s+)?([A-Za-z][A-Za-z0-9&' -]{1,30})", re.I)
USE_CASE_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blong walks?\b", re.I), "walking"),
    (re.compile(r"\bdaily commute\b", re.I), "commute"),
    (re.compile(r"\bdate night\b", re.I), "date night"),
)
WORD_RE = re.compile(r"[a-z0-9]+", re.I)
DETAIL_INTRO_RE = re.compile(
    r"\b(?:key requirement(?:\s+is)?|what matters(?:\s+is)?|what i need(?:\s+is)?|need\s+is)\s*:?\s+", re.I
)
SENTENCE_BREAK_RE = re.compile(r"(?<!\d)\.(?!\d)|[!?\n]")


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
    exhausted_attributes: frozenset[str] = frozenset()
    last_asked_attribute: str | None = None
    last_broad_constraint_signature: tuple[tuple[str, str, str, str], ...] | None = None
    last_broad_asked_turn: int | None = None
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
        """Whole active inclusion phrases, never a concatenated message history."""
        return tuple(dict.fromkeys(
            constraint.value
            for constraint in self.active_constraints
            if constraint.polarity == "include"
            and constraint.attribute not in self.no_preference_attributes
        ))


def new_profile(session_id: str, user_profile: dict) -> ShopperProfile:
    """Create clean per-session state after the official ``reset`` call."""
    return ShopperProfile(session_id=session_id, user_profile=dict(user_profile))


def _normalised_terms(value: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(value) if len(token) > 1]


def _attribute_for_value(value: str) -> Attribute:
    lowered = value.lower()
    words = set(WORD_RE.findall(lowered))
    if words & MATERIAL_WORDS:
        return "material"
    if words & COLOR_WORDS:
        return "color"
    if any(pattern.search(lowered) for pattern, _ in CATEGORY_PATTERNS):
        return "category"
    if SIZE_RE.fullmatch(lowered):
        return "size"
    if words & USE_CASE_WORDS:
        return "use_case"
    if words & STYLE_WORDS:
        return "style"
    return "feature"


def _constraint_strength(message: str, attribute: Attribute) -> ConstraintStrength:
    if attribute in {"category", "budget", "size"}:
        return "hard"
    if re.search(r"\b(?:must|cannot|can't|can not|without|avoid|only|key requirement|what matters|what i need|need is)\b", message, re.I):
        return "hard"
    return "soft"


def _trim_negative_value(value: str) -> str:
    value = re.split(r"\b(?:and|but|for|because|please)\b|[.;,:!?]", value, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\s+", " ", value).strip()


def _trim_brand(value: str) -> str:
    """Keep a brand mention bounded to its phrase rather than the whole request."""
    value = re.split(r"\b(?:and|but|for|with|under|below|between|around|about|in)\b|[.;,:!?]", value, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\s+", " ", value).strip().lower()


def _is_money_bound(message: str, match: re.Match[str]) -> bool:
    """Do not turn product measurements into monetary hard constraints.

    Plain 'at most 50' remains the existing budget shorthand. A physical unit
    or an explicit measurement/rating context takes precedence unless the
    numeric expression itself supplies an unambiguous currency symbol.
    """
    if "$" in match.group(0):
        return True
    suffix = message[match.end():]
    if suffix[:1].isdigit() or NON_MONEY_UNIT_RE.match(suffix):
        return False
    return not NON_MONEY_CONTEXT_RE.search(message[max(0, match.start() - 48):match.start()])


def extract_constraints(message: str, turn: int) -> tuple[Constraint, ...]:
    """Extract lightweight, deterministic shopping constraints from one message.

    The function intentionally favours precision over clever guessing.  V2 can
    swap this extractor for a model-assisted parser behind the same interface.
    """
    message = message.replace("\u2019", "'").replace("\u2018", "'")
    lowered = message.lower()
    result: list[Constraint] = []
    negative_spans: list[tuple[int, int]] = []
    detail_spans: list[tuple[int, int]] = []
    for prefix in DETAIL_INTRO_RE.finditer(message):
        boundary = SENTENCE_BREAK_RE.search(message, prefix.end())
        detail_spans.append((prefix.end(), boundary.start() if boundary else len(message)))

    def is_negative(match: re.Match[str]) -> bool:
        return any(start < match.end() and match.start() < end for start, end in negative_spans)

    def is_detail(match: re.Match[str]) -> bool:
        return any(start <= match.start() < end for start, end in detail_spans)

    for match in NEGATIVE_RE.finditer(message):
        raw = re.split(r"\b(?:but|for|because|please|with)\b|[.;,:!?]", match.group(1), maxsplit=1, flags=re.I)[0]
        first_attribute = None
        cursor = 0
        for part in re.split(r"\b(?:and|or)\b", raw, flags=re.I):
            start = raw.find(part, cursor)
            cursor = start + len(part)
            value = re.sub(r"^(?:no|not|avoid|without)\s+", "", part.strip(), flags=re.I)
            if not value or "preference" in value.lower() or re.match(r"(?:sure|certain|know|quite right)\b", value, re.I):
                break
            attribute = _attribute_for_value(value)
            # Propagate a coordinated exclusion only within the same slot:
            # 'no leather and wool' excludes both; 'no leather and red shoes'
            # does not turn the separate positive color/category into negatives.
            if first_attribute is not None and attribute != first_attribute:
                break
            first_attribute = attribute
            negative_spans.append((match.start(1) + start, match.start(1) + cursor))
            canonical = value.lower()
            if attribute == "category":
                canonical = next((category for pattern, category in CATEGORY_PATTERNS
                                  if pattern.fullmatch(value)), canonical)
            result.append(Constraint(attribute, canonical, "hard", "exclude", turn))

    for match in BUDGET_RE.finditer(message):
        operator, value = match.group(1).lower(), match.group(2)
        relation = ("under" if operator in {"under", "below", "less than"} else
                    "<=" if operator in {"at most", "maximum", "max", "up to"} else
                    ">=" if operator == "at least" else
                    ">" if operator in {"over", "above", "more than"} else "around")
        if not is_negative(match) and _is_money_bound(message, match):
            result.append(Constraint("budget", f"{relation} {value}", "hard", "include", turn))

    for match in RANGE_BUDGET_RE.finditer(message):
        if not is_negative(match) and _is_money_bound(message, match):
            result.append(Constraint("budget", f"between {match.group(1)} and {match.group(2)}", "hard", "include", turn))

    for match in AROUND_BUDGET_RE.finditer(message):
        if not is_negative(match) and _is_money_bound(message, match):
            result.append(Constraint("budget", f"around {match.group(1)}", "hard", "include", turn))

    for match in SIZE_RE.finditer(message):
        value = match.group(0).lower()
        if not is_negative(match):
            result.append(Constraint("size", value, "hard", "include", turn))

    for pattern, category in CATEGORY_PATTERNS:
        if any(not is_negative(match) and not is_detail(match) for match in pattern.finditer(message)):
            result.append(Constraint("category", category, "hard", "include", turn))

    for color in sorted(COLOR_WORDS):
        if any(not is_negative(match) for match in re.finditer(rf"\b{re.escape(color)}\b", lowered)):
            result.append(
                Constraint("color", color, _constraint_strength(message, "color"), "include", turn)
            )

    for material in sorted(MATERIAL_WORDS):
        if any(not is_negative(match) for match in re.finditer(rf"\b{re.escape(material)}\b", lowered)):
            result.append(
                Constraint("material", material, _constraint_strength(message, "material"), "include", turn)
            )

    for pattern, feature in FEATURE_PATTERNS:
        if any(not is_negative(match) for match in pattern.finditer(message)):
            result.append(Constraint("feature", feature, _constraint_strength(message, "feature"), "include", turn))

    for pattern, use_case in USE_CASE_PHRASES:
        if any(not is_negative(match) for match in pattern.finditer(message)):
            result.append(Constraint("use_case", use_case, _constraint_strength(message, "use_case"), "include", turn, 0.95))

    for style in sorted(STYLE_WORDS):
        if any(not is_negative(match) for match in re.finditer(rf"\b{re.escape(style)}\b", lowered)):
            result.append(
                Constraint("style", style, _constraint_strength(message, "style"), "include", turn)
            )

    for use_case in sorted(USE_CASE_WORDS):
        if any(not is_negative(match) for match in re.finditer(rf"\b{re.escape(use_case)}\b", lowered)):
            result.append(
                Constraint("use_case", use_case, _constraint_strength(message, "use_case"), "include", turn)
            )

    for match in BRAND_RE.finditer(message):
        brand = _trim_brand(match.group(1))
        if is_detail(match) and not match.group(0).lower().startswith("brand"):
            continue
        if brand and not is_negative(match) and brand not in {"a", "an", "the", "my", "this", "that"}:
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


def _replacement_text(message: str) -> str:
    """Remove the superseded side of explicit replacements before extraction."""
    message = message.replace("\u2019", "'").replace("\u2018", "'")
    attributes = r"category|material|color|size|style|brand|budget|feature|use case|other"
    message = re.sub(
        rf"\b(?:switch|change)\s+(?:the\s+)?({attributes})\s+from\s+[^,;.!?]+?\s+to\s+",
        lambda match: match.group(1) + ": ", message, flags=re.I,
    )
    message = re.sub(r"\b(?:switch|change)\s+from\s+[^,;.!?]+?\s+to\s+", "", message, flags=re.I)
    message = re.sub(r"\breplace\s+[^,;.!?]+?\s+with\s+", "", message, flags=re.I)
    return re.sub(r"\binstead of\s+[^,;.!?]+", "", message, flags=re.I)


def _phrase_constraint(attribute: Attribute, value: str, message: str, turn: int) -> Constraint | None:
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n.,;:!?\"'").lower()
    value = re.sub(r"^(?:please\s+)?(?:is|are|be)\s*:?\s+", "", value)
    if not value or len(value) > 512 or len(value.split()) > 80:
        return None
    if re.fullmatch(r"(?:yes|no|okay|ok|thanks|thank you|maybe|not sure|that|this|it|them|i (?:do not|don't) know)", value):
        return None
    if re.search(r"\b(?:use your judg(?:e)?ment|not quite right|ask me about|one specific attribute)\b", value):
        return None
    if "preference" in value or re.search(r"\b(?:start over|ignore (?:my )?(?:earlier|previous))\b", value):
        return None
    polarity: ConstraintPolarity = "include"
    if re.match(r"^(?:no|not|avoid|without)\s+", value):
        value = re.sub(r"^(?:no|not|avoid|without)\s+", "", value)
        polarity = "exclude"
    if attribute == "category":
        value = next((category for pattern, category in CATEGORY_PATTERNS if pattern.fullmatch(value)), value)
    if attribute == "size" and re.fullmatch(r"\d{1,2}(?:\.\d)?", value):
        value = "size " + value
    if attribute == "budget" and re.fullmatch(r"\$?\d+(?:\.\d+)?", value):
        value = "around " + value.lstrip("$")
    if attribute == "budget" and "$" not in value:
        if any(NON_MONEY_UNIT_RE.match(value, match.end()) for match in re.finditer(r"\d+(?:\.\d+)?", value)):
            return None
    strength = "hard" if polarity == "exclude" else _constraint_strength(message, attribute)
    return Constraint(attribute, value, strength, polarity, turn)


def _contextual_constraints(
    message: str, turn: int, asked: str | None, known: tuple[Constraint, ...]
) -> tuple[Constraint, ...]:
    """Bounded explicit phrases/answers, kept as replaceable constraint records."""
    result: list[Constraint] = []
    for match in re.finditer(r"\b(?:looking|shopping|searching)\s+for\s+([^,;.!?\n]+)", message, re.I):
        value = re.sub(r"^(?:a|an|some)\s+", "", match.group(1).strip(), flags=re.I)
        value = re.split(r"\b(?:with|without|under|below|between|but|not|no|avoid|except|by|from|for)\b", value, maxsplit=1, flags=re.I)[0].strip()
        # Category context must not become a second, untracked copy of a color,
        # fabric, size, etc. Those preferences already have their own records and
        # must disappear completely when their slot is cleared or replaced.
        independent_slots = {"color", "material", "size", "style", "brand", "budget", "feature"}
        for item in known:
            if item.polarity == "include" and item.attribute in independent_slots:
                value = re.sub(r"(?<!\w)" + re.escape(item.value) + r"(?!\w)", " ", value, flags=re.I)
        value = re.sub(r"\s+", " ", value).strip()
        value = re.sub(r"^(?:(?:in|and|or|a|an|the)\s+)+|(?:\s+(?:in|and|or))+$", "", value, flags=re.I).strip()
        if value.lower() in {"something", "something nice", "anything", "inspiration"}:
            continue
        phrase = _phrase_constraint("category", value, message, turn)
        if phrase:
            # Keep the complete category context for retrieval, without claiming
            # every adjective is a trustworthy hard taxonomy requirement.
            result.append(replace(phrase, strength="soft", confidence=0.75))
    label_re = re.compile(
        r"\b(category|material|color|size|style|brand|budget|feature|use case|use_case|other)\s*:\s*([^,;!?\n]+)", re.I
    )
    for match in label_re.finditer(message):
        attribute = match.group(1).lower().replace(" ", "_")
        phrase = _phrase_constraint(attribute, match.group(2), message, turn)
        if phrase:
            result.append(phrase)

    requirement_re = re.compile(
        r"\b(key requirement(?:\s+is)?|what matters(?:\s+is)?|what i need(?:\s+is)?|prioriti[sz]e|need(?:\s+is)?)\s*:?\s+([^!?\n]+)", re.I
    )
    for match in requirement_re.finditer(message):
        for value in re.split(r"\s*;\s*|(?<!\d)\.(?!\d)", match.group(2)):
            value = value.strip()
            if label_re.match(value):
                continue
            # A structured 'need red leather boots' already has independently
            # replaceable slots. Do not retain it as a stale whole sentence.
            if match.group(1).lower() == "need" and extract_constraints(value, turn):
                continue
            attribute = _attribute_for_value(value)
            if attribute == "category":
                # A sneaker mentioned inside a descriptive requirement is not
                # a request to replace an existing walking-shoe category.
                attribute = "other"
            if attribute == "feature" and not any(pattern.search(value) for pattern, _ in FEATURE_PATTERNS):
                attribute = "other"
            phrase = _phrase_constraint(attribute, value, message, turn)
            if phrase:
                result.append(phrase)

    # Preserve uncommon explicit modifiers without attaching the old category.
    for match in re.finditer(r"\b(with|featuring|for)\s+([^,;!?\n]+)", message, re.I):
        value = match.group(2).strip()
        value = SENTENCE_BREAK_RE.split(value, maxsplit=1)[0].strip()
        if re.search(r"\b(?:looking|shopping|searching)\s+$", message[:match.start()], re.I):
            continue
        if extract_constraints(value, turn) or "preference" in message.lower():
            continue
        attribute = "use_case" if match.group(1).lower() == "for" else "feature"
        phrase = _phrase_constraint(attribute, value, message, turn)
        if phrase:
            result.append(phrase)

    if not known and not result and asked in ALLOWED_ASK_ATTRIBUTES:
        value = re.sub(r"^(?:actually[, ]+|it(?:'s| is)\s+|i (?:want|prefer)\s+)", "", message.strip(), flags=re.I)
        if len(value.split()) <= 12 and not re.search(r"[?;]|\b(?:no|not)\s+(?:additional|other|further)\b", value, re.I):
            phrase = _phrase_constraint(asked, value, message, turn)
            if phrase:
                result.append(phrase)
    return tuple(result)


def _excluded_category_in_anchor(anchor: str, excluded: str) -> bool:
    """Recognize the existing leaf aliases, without introducing a taxonomy."""
    if re.search(r"(?<!\w)" + re.escape(excluded) + r"(?!\w)", anchor, re.I):
        return True
    return any(
        (category == excluded or pattern.fullmatch(excluded)) and pattern.search(anchor)
        for pattern, category in CATEGORY_PATTERNS
    )


def _deactivate_conflicts(
    existing: tuple[Constraint, ...], additions: tuple[Constraint, ...], broad_override: bool,
    *, cleared: set[str], targeted_override: bool = False, reset_all: bool = False,
) -> tuple[tuple[Constraint, ...], list[str]]:
    """Deactivate stale constraints while preserving an auditable history."""
    updated: list[Constraint] = []
    changes: list[str] = []
    single_value_attributes = {"category", "color", "material", "size", "budget", "brand"}
    for constraint in existing:
        replace_same_attribute = any(
            addition.attribute == constraint.attribute and (
                addition.value == constraint.value
                or (constraint.attribute == "category" and addition.polarity == "exclude"
                    and constraint.polarity == "include"
                    and _excluded_category_in_anchor(constraint.value, addition.value))
                or (addition.polarity == constraint.polarity == "include"
                    and (constraint.attribute in single_value_attributes or targeted_override))
            ) for addition in additions
        )
        replace_soft_on_override = (broad_override and constraint.active and constraint.strength == "soft"
                                    and constraint.attribute != "category")
        if constraint.active and (reset_all or constraint.attribute in cleared or replace_same_attribute or replace_soft_on_override):
            updated.append(replace(constraint, active=False))
            changes.append(f"turn {constraint.source_turn} {constraint.attribute}='{constraint.value}' deactivated")
        else:
            updated.append(constraint)
    return tuple(updated), changes


def update_profile(profile: ShopperProfile, user_message: str, turn: int) -> ShopperProfile:
    """Apply one customer message to a profile without making retrieval decisions."""
    if type(turn) is not int or turn < 1:
        raise ValueError("turn must be at least 1")
    if turn == profile.turn and profile.messages and profile.messages[-1] == user_message:
        return profile
    if not user_message.strip():
        return replace(profile, turn=turn, messages=profile.messages + (user_message,))

    parsed_message = _replacement_text(user_message)
    reset_all = bool(re.search(
        r"\b(?:start over|ignore (?:my |the )?(?:earlier|previous) requirements?)\b", parsed_message, re.I
    ))
    broad_override = reset_all or bool(re.search(
        r"\bignore (?:my |the )?(?:earlier|previous) preferences?\b", parsed_message, re.I
    ))
    override = broad_override or parsed_message != user_message or bool(OVERRIDE_RE.search(parsed_message))
    no_preference_attributes = set(profile.no_preference_attributes)
    exhausted_attributes = set(profile.exhausted_attributes)
    if broad_override:
        no_preference_attributes.clear()
        exhausted_attributes.clear()
    cleared: set[str] = set()
    clear_ends: dict[str, int] = {}
    for pattern, destination in ((NO_PREFERENCE_RE, cleared), (EXHAUSTED_RE, exhausted_attributes)):
        for match in pattern.finditer(parsed_message):
            attribute = (match.group(1) or profile.last_asked_attribute or "other").lower().replace(" ", "_")
            if attribute in ALLOWED_ASK_ATTRIBUTES:
                destination.add(attribute)
                if pattern is NO_PREFERENCE_RE:
                    clear_ends[attribute] = match.end()
    no_preference_attributes.update(cleared)
    exhausted_attributes.difference_update(cleared)

    additions = extract_constraints(parsed_message, turn)
    additions += _contextual_constraints(parsed_message, turn, profile.last_asked_attribute, additions)
    additions = tuple(item for item in additions if item.attribute not in cleared)
    for attribute, end in clear_ends.items():
        # 'No color preference, but not red' first clears the old slot and then
        # supplies a new explicit exclusion. Do not hide it behind the flag.
        tail = parsed_message[end:].lstrip(" ,;.")
        tail_known = extract_constraints(tail, turn)
        tail_additions = tail_known + _contextual_constraints(tail, turn, attribute, tail_known)
        additions += tuple(item for item in tail_additions if item.attribute == attribute)
    explicit_attributes = {item.attribute for item in additions}
    no_preference_attributes.difference_update(explicit_attributes)
    exhausted_attributes.difference_update(explicit_attributes)
    prior_constraints, changes = _deactivate_conflicts(
        profile.constraints, additions, broad_override, cleared=cleared,
        targeted_override=override, reset_all=reset_all,
    )
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

    intent = detect_intent(parsed_message, "unclear" if reset_all else profile.intent_mode)
    if override and additions:
        intent = "buying" if any(item.strength == "hard" for item in additions) else intent
    return replace(
        profile,
        turn=turn,
        intent_mode=intent,
        constraints=tuple(merged),
        no_preference_attributes=frozenset(no_preference_attributes),
        exhausted_attributes=frozenset(exhausted_attributes),
        asked_attributes=frozenset() if reset_all else profile.asked_attributes,
        last_asked_attribute=None if reset_all else profile.last_asked_attribute,
        last_broad_constraint_signature=None if reset_all else profile.last_broad_constraint_signature,
        last_broad_asked_turn=None if reset_all else profile.last_broad_asked_turn,
        messages=profile.messages + (user_message,),
        change_log=profile.change_log + tuple(changes),
    )
