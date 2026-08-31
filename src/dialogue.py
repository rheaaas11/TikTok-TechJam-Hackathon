"""Clarification policy owned by Shayna.

The policy is deliberately small and deterministic for V1.  It selects one
allowed attribute only when the profile is materially incomplete; Rhea can
combine the resulting message with Leon's recommendations in the official
agent response.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import fsum
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
    if not counts:
        return 0.0
    positive = [count for count in counts.values() if count > 0]
    total = sum(positive)
    if total <= 0 or len(positive) < 2:
        return 0.0
    return 1.0 - fsum((count / total) ** 2 for count in positive)


def choose_ask_attribute(
    profile: ShopperProfile, candidate_attribute_counts: CandidateAttributeCounts | None = None
) -> tuple[str | None, float | None]:
    """Pick the highest-value unseen attribute for the current conversation.

    Without candidate evidence this preserves the V1 priority order.  With
    evidence, it prefers the allowed question that best separates Leon's
    current candidate pool.
    """
    if _active_detail_count(profile) >= 3:
        return None, None

    if profile.intent_mode == "browsing":
        priority = ("category", "use_case", "style", "budget", "material", "color", "size", "feature")
    else:
        priority = ("category", "budget", "material", "color", "size", "feature", "use_case", "style")

    unavailable = set(profile.active_attributes) | set(profile.no_preference_attributes)
    eligible = [attribute for attribute in priority if attribute not in unavailable]

    if candidate_attribute_counts:
        scored = [
            (attribute, _question_value(candidate_attribute_counts.get(attribute)))
            for attribute in eligible
            if attribute != profile.last_asked_attribute
        ]
        valuable = [(attribute, value) for attribute, value in scored if value > 0.0]
        if valuable:
            # ``max`` is stable, so a tie keeps the declared priority order.
            return max(valuable, key=lambda item: item[1])

    # Do not repeat the immediately preceding question if there is an alternative.
    for attribute in eligible:
        if attribute != profile.last_asked_attribute:
            return attribute, None
    if eligible:
        return eligible[0], None
    return None, None


def decide_next_turn(
    profile: ShopperProfile, candidate_attribute_counts: CandidateAttributeCounts | None = None
) -> DialogueDecision:
    attribute, question_value = choose_ask_attribute(profile, candidate_attribute_counts)
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
) -> DialogueDecision:
    """Public handoff function for Rhea's future ``Agent.respond`` integration."""
    return decide_next_turn(update_profile(profile, user_message, turn), candidate_attribute_counts)
