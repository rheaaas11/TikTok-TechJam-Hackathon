"""Small integration bridge; interpretation and question policy remain in src.

This module is imported only for the combined implementation. It does not parse
conversation itself, read labels, or translate truncated top-values into counts.
"""

from __future__ import annotations

import copy
import threading

from src.dialogue import decide_next_turn
from src.profile import ShopperProfile, new_profile, update_profile
from starter.conversation import StateUpdate
from starter.shayna_adapter import ShaynaProfileAdapter


class ShaynaConversationBrain:
    def __init__(self) -> None:
        self.sessions: dict[str, ShopperProfile] = {}
        self.profile_adapter = ShaynaProfileAdapter()
        self._lock = threading.RLock()

    def reset(self, session_id: str, user_profile: dict) -> None:
        with self._lock:
            self.sessions[session_id] = new_profile(session_id, copy.deepcopy(user_profile))

    def update(self, session_id: str, user_message: str, turn: int) -> StateUpdate:
        with self._lock:
            if session_id not in self.sessions:
                raise RuntimeError("reset must be called before respond")
            # Do not commit before retrieval succeeds. Failed retrieval can be
            # retried without advancing the profile or spending another question.
            profile = update_profile(self.sessions[session_id], user_message, turn)
            return StateUpdate(profile, "", None)

    def finalize(self, session_id: str, update: StateUpdate, statistics: dict | None) -> StateUpdate:
        with self._lock:
            decision = decide_next_turn(update.profile, candidate_statistics=statistics)
            return StateUpdate(decision.updated_profile, decision.message, decision.ask_attribute)

    def commit(self, session_id: str, update: StateUpdate) -> None:
        """Publish state only after ranking, question policy and composition succeed."""
        with self._lock:
            self.sessions[session_id] = update.profile
