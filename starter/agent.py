from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, Sequence

from starter.conversation import (
    ConversationBrain,
    ReferenceConversationBrain,
    StateUpdate,
)
from starter.ranker import Ranker


ALLOWED_ATTRIBUTES = frozenset(
    {"category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"}
)


class RankingBackend(Protocol):
    def rank(self, profile: object, top_k: int = 10) -> list[dict[str, str]]: ...


class ResponseComposer(Protocol):
    def compose(
        self,
        update: StateUpdate,
        recommendations: Sequence[Mapping[str, object]],
    ) -> dict: ...


class OfficialResponseComposer:
    """Allow-list the official payload; diagnostics/evidence cannot leak."""

    def compose(
        self,
        update: StateUpdate,
        recommendations: Sequence[Mapping[str, object]],
    ) -> dict:
        seen: set[str] = set()
        clean: list[dict[str, str]] = []
        for item in recommendations:
            parent_asin = str(item.get("parent_asin", "")).strip()
            if not parent_asin or parent_asin in seen:
                continue
            seen.add(parent_asin)
            clean.append({"parent_asin": parent_asin})
            if len(clean) >= 10:
                break
        ask_attribute = update.ask_attribute if update.ask_attribute in ALLOWED_ATTRIBUTES else None
        return {
            "message": str(update.message),
            "ask_attribute": ask_attribute,
            "recommendations": clean,
        }


class Agent:
    """Thin official entrypoint with injectable Shayna/Rhea integration hooks."""

    def __init__(
        self,
        catalog_path: str | Path | None = "data/catalog.jsonl",
        *,
        brain: ConversationBrain | None = None,
        ranker: RankingBackend | None = None,
        composer: ResponseComposer | None = None,
    ) -> None:
        if ranker is None:
            if catalog_path is None:
                raise ValueError("catalog_path is required when ranker is not injected")
            ranker = Ranker(catalog_path)
        self.brain = brain or ReferenceConversationBrain()
        self.ranker = ranker
        self.composer = composer or OfficialResponseComposer()

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.brain.reset(session_id, user_profile)

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict:
        update = self.brain.update(session_id, user_message, turn)
        recommendations = self.ranker.rank(update.profile, top_k)
        return self.composer.compose(update, recommendations)

    def close(self) -> None:
        close = getattr(self.ranker, "close", None)
        if callable(close):
            close()
