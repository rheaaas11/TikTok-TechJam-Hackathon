"""Clarification policy owned by Shayna.

The policy is deliberately small and deterministic for V1.  It selects one
allowed attribute only when the profile is materially incomplete; Rhea can
combine the resulting message with Leon's recommendations in the official
agent response.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import fsum, isfinite
from typing import Mapping

from src.profile import ALLOWED_ASK_ATTRIBUTES, ShopperProfile, update_profile


QUESTION_TEXT = {
    "category": "What type of item are you looking for?",
    "use_case": "What will you mainly use it for?",
    "budget": "What budget are you aiming for?",
    "material": "Do you have a material preference?",
    "color": "Would you like a particular color?",
    "size": "What size do you need?",
    "style": "What style would you prefer?",
    "brand": "Is there a brand you prefer?",
    "feature": "Is there one feature that matters most?",
    "other": "What is the most important thing for me to know?",
}

# Leon's ranker can expose a distribution of still-eligible candidates for an
# attribute, e.g. {"color": {"black": 34, "white": 21}}.  This remains a
# small protocol rather than a dependency on Leon's implementation.
CandidateAttributeCounts = Mapping[str, Mapping[str, int]]
CandidateStatistics = Mapping[str, object]


@dataclass(frozen=True)
class DialogueDecision:
    updated_profile: ShopperProfile
    message: str
    ask_attribute: str | None
    should_ask: bool
    question_value: float | None = None


def _active_detail_count(profile: ShopperProfile) -> int:
    return len(
        {
            constraint.attribute
            for constraint in profile.active_constraints
            if constraint.attribute != "category" and constraint.polarity == "include"
        }
    )


def _question_value(counts: Mapping[str, int] | None) -> float:
    """Estimate candidate reduction from a question using Gini impurity.

    Values are intentionally bounded between 0 and 1.  A single remaining
    value has no value to ask about; a balanced distribution has high value.
    Leon should provide normalized, shopper-facing buckets (such as budget
    bands), not raw one-off prices.
    """
    if not isinstance(counts, Mapping) or not counts:
        return 0.0
    if any(type(count) is not int or count < 0 for count in counts.values()):
        return 0.0
    positive = [count for count in counts.values() if count > 0]
    total = sum(positive)
    if total <= 0 or len(positive) < 2:
        return 0.0
    return 1.0 - fsum((count / total) ** 2 for count in positive)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _statistics_value(statistics: CandidateStatistics, attribute: str) -> float:
    """Consume Leon's coverage-aware utility, not its truncated top-values list.

    Missing products must survive every answer. Cap inconsistent externally
    supplied summaries conservatively; no distribution is reconstructed.
    """
    if not isinstance(statistics, Mapping):
        return 0.0
    pool = _finite_number(statistics.get("pool_size"))
    attributes = statistics.get("attributes")
    if pool is None or pool <= 1 or not isinstance(attributes, Mapping):
        return 0.0
    metrics = attributes.get(attribute)
    if not isinstance(metrics, Mapping):
        return 0.0
    coverage = _finite_number(metrics.get("coverage"))
    remaining = _finite_number(metrics.get("expected_remaining"))
    if coverage is None or not 0 <= coverage <= 1 or remaining is None or not 0 <= remaining <= pool:
        return 0.0
    remaining = max(remaining, pool * (1 - coverage))
    utility = coverage * (1 - remaining / pool)
    if "question_value" in metrics:
        supplied = _finite_number(metrics["question_value"])
        if supplied is None or not 0 <= supplied <= 1:
            return 0.0
        utility = min(utility, supplied)
    return max(0.0, min(1.0, utility))


def _constraint_signature(profile: ShopperProfile) -> tuple[tuple[str, str, str, str], ...]:
    """Meaningful active information, not messages or repeated answer wording."""
    return tuple(sorted({
        (constraint.attribute, constraint.value.strip(), constraint.polarity, constraint.strength)
        for constraint in profile.active_constraints
        if constraint.value.strip() and constraint.attribute not in profile.no_preference_attributes
    }))


def _productive_broad_answer(profile: ShopperProfile) -> bool:
    previous = profile.last_broad_constraint_signature
    return (
        profile.last_asked_attribute == "other"
        and profile.last_broad_asked_turn is not None
        and profile.turn > profile.last_broad_asked_turn
        and previous is not None
        and bool(set(_constraint_signature(profile)) - set(previous))
    )


def choose_ask_attribute(
    profile: ShopperProfile, candidate_attribute_counts: CandidateAttributeCounts | None = None,
    *, candidate_statistics: CandidateStatistics | None = None,
) -> tuple[str | None, float | None]:
    """Pick the highest-value unseen attribute for the current conversation.

    Without candidate evidence this preserves the V1 priority order.  With
    evidence, it prefers the allowed question that best separates Leon's
    current candidate pool.
    """
    if candidate_statistics is None and _active_detail_count(profile) >= 3:
        return None, None

    if profile.intent_mode == "browsing":
        priority = ("category", "use_case", "style", "budget", "material", "color", "size", "feature", "brand", "other")
    else:
        priority = ("category", "budget", "material", "color", "size", "feature", "use_case", "style", "brand", "other")

    unavailable = (set(profile.active_attributes) | set(profile.no_preference_attributes)
                   | set(profile.asked_attributes) | set(profile.exhausted_attributes))
    if profile.last_asked_attribute:
        unavailable.add(profile.last_asked_attribute)
    eligible = [attribute for attribute in priority if attribute not in unavailable]

    if candidate_statistics is not None:
        # Broad clarification requests *additional* requirements, so one known
        # `other` phrase does not fill a single-valued slot. Repeat only after a
        # demonstrably productive answer, never after explicit refusal/exhaustion.
        productive_broad = _productive_broad_answer(profile)
        broad_blocked = "other" in profile.no_preference_attributes or "other" in profile.exhausted_attributes
        broad_available = not broad_blocked and (
            "other" not in profile.asked_attributes or productive_broad
        )
        eligible = [attribute for attribute in eligible if attribute != "other"]
        if broad_available:
            eligible.append("other")
        if (profile.last_asked_attribute == "other" and profile.last_broad_asked_turn is not None
                and profile.turn <= profile.last_broad_asked_turn):
            # No new answer yet. Re-running policy cannot spend another question.
            return None, None
        previous_narrow = profile.last_asked_attribute
        unproductive_narrow = previous_narrow not in (None, "other") and (
            previous_narrow in profile.no_preference_attributes
            or previous_narrow in profile.exhausted_attributes
        )
        if broad_available and (productive_broad or unproductive_narrow):
            # Catalogue diversity estimates reduction *if answered*. An observed
            # unanswerable question is evidence to broaden the next clarification,
            # without assuming any specific attribute is intrinsically useless.
            return "other", None
        scored = [(attribute, _statistics_value(candidate_statistics, attribute)) for attribute in eligible]
        valuable = [(attribute, value) for attribute, value in scored if value > 0.0]
        if valuable:
            return max(valuable, key=lambda item: item[1])
        if _active_detail_count(profile) >= 3:
            if "other" in eligible:
                return "other", None
            # A new unproductive broad answer does not prove every narrower
            # question is exhausted. Continue with an unseen slot if available.
    elif isinstance(candidate_attribute_counts, Mapping) and candidate_attribute_counts:
        scored = [
            (attribute, _question_value(candidate_attribute_counts.get(attribute)))
            for attribute in eligible
            if attribute != profile.last_asked_attribute
        ]
        valuable = [(attribute, value) for attribute, value in scored if value > 0.0]
        if valuable:
            # ``max`` is stable, so a tie keeps the declared priority order.
            return max(valuable, key=lambda item: item[1])

    # All previously asked, exhausted and no-preference slots are unavailable.
    if eligible:
        return eligible[0], None
    return None, None


def decide_next_turn(
    profile: ShopperProfile, candidate_attribute_counts: CandidateAttributeCounts | None = None,
    *, candidate_statistics: CandidateStatistics | None = None,
) -> DialogueDecision:
    attribute, question_value = choose_ask_attribute(
        profile, candidate_attribute_counts, candidate_statistics=candidate_statistics
    )
    if attribute is None:
        return DialogueDecision(
            updated_profile=replace(profile, last_asked_attribute=None),
            message="I’ll use those preferences to refine the closest matches.",
            ask_attribute=None,
            should_ask=False,
            question_value=None,
        )
    if attribute not in ALLOWED_ASK_ATTRIBUTES:
        raise RuntimeError(f"unsupported ask attribute: {attribute}")
    return DialogueDecision(
        updated_profile=replace(
            profile,
            asked_attributes=frozenset(set(profile.asked_attributes) | {attribute}),
            last_asked_attribute=attribute,
            last_broad_constraint_signature=(
                _constraint_signature(profile) if attribute == "other" else profile.last_broad_constraint_signature
            ),
            last_broad_asked_turn=profile.turn if attribute == "other" else profile.last_broad_asked_turn,
        ),
        message=QUESTION_TEXT[attribute],
        ask_attribute=attribute,
        should_ask=True,
        question_value=question_value,
    )


def process_message(
    profile: ShopperProfile,
    user_message: str,
    turn: int,
    candidate_attribute_counts: CandidateAttributeCounts | None = None,
    *, candidate_statistics: CandidateStatistics | None = None,
) -> DialogueDecision:
    """Public handoff function for Rhea's future ``Agent.respond`` integration."""
    return decide_next_turn(
        update_profile(profile, user_message, turn), candidate_attribute_counts,
        candidate_statistics=candidate_statistics,
    )
