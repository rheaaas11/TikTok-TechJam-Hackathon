from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass
from typing import Protocol

from starter.catalog import COLORS, MATERIALS, SIZES, STYLES, normalize_text


@dataclass(frozen=True)
class StateUpdate:
    """Team-neutral handoff from Shayna's conversation brain to Rhea."""

    profile: object
    message: str
    ask_attribute: str | None


class ConversationBrain(Protocol):
    def reset(self, session_id: str, user_profile: dict) -> None: ...

    def update(self, session_id: str, user_message: str, turn: int) -> StateUpdate: ...


_CLAUSE_RE = re.compile(
    r"(?:a\s+key\s+requirement\s+is|what\s+matters\s+is|what\s+i\s+need\s+is|"
    r"please\s+prioriti[sz]e)\s*:?\s*(.+)$",
    re.IGNORECASE,
)
_CATEGORY_RE = re.compile(r"(?:looking|shopping)\s+for\s+(.+?)(?:,|\.|$)", re.IGNORECASE)
_OVERRIDE_RE = re.compile(
    r"\b(?:actually|instead|rather|ignore|forget|switch|change|replace|no\s+longer)\b",
    re.IGNORECASE,
)
_NO_PREFERENCE_RE = re.compile(
    r"(?:don['’]?t\s+have\s+(?:(?:a|any)\s+)?preference\s+for|"
    r"no\s+preference\s+(?:for|on))\s+([a-z_ ]+?)(?:[;,.]|$)",
    re.IGNORECASE,
)
_NO_ADDITIONAL_RE = re.compile(
    r"don['’]?t\s+have\s+(?:an?\s+)?additional\s+preference\s+for\s+"
    r"([a-z_ ]+?)(?:[;,.]|$)",
    re.IGNORECASE,
)

_ATTRIBUTE_ALIASES = {"colour": "color", "price": "budget", "usage": "use_case"}


def _attribute_name(value: str) -> str:
    normalized = normalize_text(value).replace(" ", "_")
    return _ATTRIBUTE_ALIASES.get(normalized, normalized)


def _contains_known(value: str, vocabulary: tuple[str, ...]) -> bool:
    padded = f" {normalize_text(value)} "
    return any(f" {known} " in padded for known in vocabulary)


def classify_constraint(value: str) -> str:
    lowered = value.lower()
    if re.search(r"(?:budget|price|\$|[<>]=?)\s*\d|\b(?:under|below|over|above)\s+\d", lowered):
        return "budget"
    if _contains_known(value, MATERIALS):
        return "material"
    if _contains_known(value, COLORS):
        return "color"
    if _contains_known(value, SIZES) or re.search(r"\b(?:size|sizing|width)\b", lowered):
        return "size"
    if _contains_known(value, STYLES) or re.search(r"\b(?:style|fit|sleeve|neckline)\b", lowered):
        return "style"
    if re.search(r"\b(?:brand|made by|store)\b", lowered):
        return "brand"
    if re.search(r"\b(?:hiking|running|gym|winter|outdoor|work|wedding|travel|school)\b", lowered):
        return "use_case"
    return "feature"


class ReferenceConversationBrain:
    """Offline reference state builder used by the starter evaluator.

    Shayna can replace this object without changing ``Agent`` or ``Ranker``.
    It is deliberately deterministic and does not claim to be the team's final
    natural-language policy.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self._lock = threading.RLock()

    def reset(self, session_id: str, user_profile: dict) -> None:
        with self._lock:
            self.sessions[session_id] = {
                "session_id": session_id,
                "user_profile": dict(user_profile),
                "turn": 0,
                "mission": "",
                "category": None,
                "constraints": [],
                "query_terms": [],
                "free_terms": [],
                "asked_attributes": set(),
                "no_preference_attributes": set(),
                "exhausted_attributes": set(),
                "change_log": [],
                "processed_turns": {},
            }

    @staticmethod
    def _clauses(message: str) -> list[str]:
        match = _CLAUSE_RE.search(message)
        if not match:
            return []
        return [part.strip(" .") for part in match.group(1).split(";") if part.strip(" .")]

    @staticmethod
    def _replacement_clause(message: str) -> str | None:
        match = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:[.;]|$)", message, re.IGNORECASE)
        if match:
            return match.group(2).strip(" .")
        match = re.search(
            r"(?:want|need|prefer)\s+(.+?)\s+(?:instead\s+of|rather\s+than)\s+.+?(?:[.;]|$)",
            message,
            re.IGNORECASE,
        )
        return match.group(1).strip(" .") if match else None

    @staticmethod
    def _recompute_terms(profile: dict) -> None:
        values: list[str] = []
        if profile.get("category"):
            values.append(str(profile["category"]))
        values.extend(
            str(item["value"])
            for item in profile["free_terms"]
            if item.get("active", True) and item.get("value")
        )
        values.extend(
            str(item["value"])
            for item in profile["constraints"]
            if item.get("active", True) and item.get("value")
        )
        seen: set[str] = set()
        profile["query_terms"] = []
        for value in values:
            key = normalize_text(value)
            if not key or key in seen:
                continue
            seen.add(key)
            profile["query_terms"].append(value)
        profile["mission"] = " ".join(profile["query_terms"])

    def _apply_update(self, profile: dict, user_message: str, turn: int) -> None:
        profile["turn"] = turn
        lowered = user_message.lower()
        override = bool(_OVERRIDE_RE.search(user_message))

        additional = _NO_ADDITIONAL_RE.search(user_message)
        plain_no_preference = None if additional else _NO_PREFERENCE_RE.search(user_message)
        if additional:
            profile["exhausted_attributes"].add(_attribute_name(additional.group(1)))
        elif plain_no_preference:
            attribute = _attribute_name(plain_no_preference.group(1))
            profile["no_preference_attributes"].add(attribute)
            for constraint in profile["constraints"]:
                if constraint.get("attribute") == attribute:
                    constraint["active"] = False

        if override:
            for item in profile["free_terms"]:
                if item.get("replaceable", False):
                    item["active"] = False
            profile["change_log"].append({"turn": turn, "event": "intent_override"})

        category_match = _CATEGORY_RE.search(user_message)
        if category_match and not profile.get("category"):
            profile["category"] = category_match.group(1).strip()

        clauses = self._clauses(user_message)
        replacement = self._replacement_clause(user_message) if override and not clauses else None
        if replacement:
            clauses = [replacement]
        slot_override = bool(replacement) or bool(
            re.search(r"\b(?:switch|change|replace|instead|rather|no\s+longer)\b", user_message, re.IGNORECASE)
        )

        for clause in clauses:
            attribute = classify_constraint(clause)
            if slot_override and attribute in {
                "category", "material", "color", "size", "style", "brand", "budget", "use_case"
            }:
                for constraint in profile["constraints"]:
                    if constraint.get("attribute") == attribute and constraint.get("active", True):
                        constraint["active"] = False
                        profile["change_log"].append(
                            {
                                "turn": turn,
                                "event": "constraint_replaced",
                                "constraint_id": constraint.get("constraint_id"),
                            }
                        )
            duplicate = next(
                (
                    item
                    for item in profile["constraints"]
                    if item.get("active", True)
                    and item.get("attribute") == attribute
                    and normalize_text(item.get("value")) == normalize_text(clause)
                ),
                None,
            )
            if duplicate is not None:
                if override or "key requirement" in lowered:
                    duplicate["strength"] = "hard"
                continue
            profile["constraints"].append(
                {
                    "constraint_id": f"turn-{turn}-{len(profile['constraints']) + 1}",
                    "attribute": attribute,
                    "value": clause,
                    "strength": "hard" if override or "key requirement" in lowered else "soft",
                    "polarity": "include",
                    "confidence": 1.0,
                    "source_turn": turn,
                    "active": True,
                }
            )

        ignored_reply = bool(
            additional
            or plain_no_preference
            or "not quite right" in lowered
            or "ask me about" in lowered
        )
        if not clauses and not ignored_reply and not override:
            profile["free_terms"].append(
                {
                    "value": user_message,
                    "source_turn": turn,
                    "active": True,
                    "replaceable": turn == 1,
                }
            )
        self._recompute_terms(profile)

    def update(self, session_id: str, user_message: str, turn: int) -> StateUpdate:
        with self._lock:
            if session_id not in self.sessions:
                raise RuntimeError("reset must be called before respond")
            profile = self.sessions[session_id]
            if profile["processed_turns"].get(turn) != user_message:
                self._apply_update(profile, user_message, turn)
                profile["processed_turns"][turn] = user_message
            profile["asked_attributes"].add("other")
            return StateUpdate(
                profile=copy.deepcopy(profile),
                message="Here are the closest matches. What other requirement matters most?",
                ask_attribute="other",
            )
