from __future__ import annotations

import copy
import threading
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
            if not isinstance(item, Mapping):
                continue
            parent_asin = item.get("parent_asin")
            if not isinstance(parent_asin, str):
                continue
            parent_asin = parent_asin.strip()
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
    """Official entrypoint: active state -> ranking/stats -> question -> payload.

    With both reviewed feature branches present, auto mode uses Shayna's real
    parser and policy. A Leon-only checkout retains its reference fallback;
    explicit ``conversation_mode='shayna'`` requires the combined implementation.
    """

    def __init__(
        self,
        catalog_path: str | Path | None = "data/catalog.jsonl",
        *,
        brain: ConversationBrain | None = None,
        ranker: RankingBackend | None = None,
        composer: ResponseComposer | None = None,
        conversation_mode: str = "auto",
    ) -> None:
        if conversation_mode not in {"auto", "shayna", "reference"}:
            raise ValueError("conversation_mode must be auto, shayna, or reference")
        if brain is None:
            source_root = Path(__file__).resolve().parents[1] / "src"
            bundled_parts = [(source_root / name).is_file() for name in ("profile.py", "dialogue.py")]
            use_shayna = conversation_mode == "shayna" or (
                conversation_mode == "auto" and any(bundled_parts)
            )
            if use_shayna:
                if not all(bundled_parts):
                    raise ImportError("Shayna integration requires both src/profile.py and src/dialogue.py")
                # Do not swallow import or interface errors and quietly score
                # the reference brain instead of the requested implementation.
                from starter.shayna_conversation import ShaynaConversationBrain

                brain = ShaynaConversationBrain()
            else:
                brain = ReferenceConversationBrain()
        if ranker is None:
            if catalog_path is None:
                raise ValueError("catalog_path is required when ranker is not injected")
            ranker = Ranker(catalog_path, profile_adapter=getattr(brain, "profile_adapter", None))
        self.brain = brain
        self.ranker = ranker
        self.composer = composer or OfficialResponseComposer()
        self._lock = threading.RLock()
        self._responses: dict[str, dict[int, tuple[str, int, dict]]] = {}

    def reset(self, session_id: str, user_profile: dict) -> None:
        with self._lock:
            self.brain.reset(session_id, copy.deepcopy(user_profile))
            self._responses[session_id] = {}

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict:
        with self._lock:
            if session_id not in self._responses:
                raise RuntimeError("reset must be called before respond")
            if type(turn) is not int or not 1 <= turn <= 10:
                raise ValueError("turn must be an integer between 1 and 10")
            cache = self._responses[session_id]
            if turn in cache:
                previous_message, previous_top_k, previous_response = cache[turn]
                if (user_message, top_k) != (previous_message, previous_top_k):
                    raise ValueError("a completed turn cannot be replaced; reset the session first")
                return copy.deepcopy(previous_response)
            if cache and turn <= max(cache):
                raise ValueError("new turns must be increasing")
            update = self.brain.update(session_id, user_message, turn)
            finalize = getattr(self.brain, "finalize", None)
            rank_with_stats = getattr(self.ranker, "rank_with_stats", None)
            statistics = None
            if callable(finalize) and callable(rank_with_stats):
                recommendations, statistics = rank_with_stats(update.profile, top_k)
            else:
                recommendations = self.ranker.rank(update.profile, top_k)
            if callable(finalize):
                update = finalize(session_id, update, statistics)
            response = self.composer.compose(update, recommendations)
            cached_response = copy.deepcopy(response)
            commit = getattr(self.brain, "commit", None)
            if callable(commit):
                commit(session_id, update)
            cache[turn] = (user_message, top_k, cached_response)
            return response

    def close(self) -> None:
        close = getattr(self.ranker, "close", None)
        if callable(close):
            close()
