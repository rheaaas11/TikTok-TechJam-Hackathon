"""Run a deterministic, catalog-free walkthrough of Shayna's V2 module."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow the documented ``python3 scripts/demo_shayna_v2.py`` command to run
# directly from the repository root without requiring package installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dialogue import process_message
from src.profile import new_profile


def _show(decision) -> None:
    profile = decision.updated_profile
    print(f"Agent: {decision.message}")
    print(f"ask_attribute: {decision.ask_attribute}; question_value: {decision.question_value}")
    print("active Product DNA:")
    for constraint in profile.active_constraints:
        print(f"  - {constraint.attribute}: {constraint.value} ({constraint.strength}, {constraint.polarity})")
    print()


def main() -> None:
    profile = new_profile("shopsense-demo", {"style_affinity": "minimal"})
    candidate_counts = {
        "budget": {"under 50": 90, "50 to 100": 10},
        "color": {"black": 50, "white": 50},
    }

    print("ShopSense / Shayna V2 walkthrough\n")
    messages = (
        "I need shoes for a trip.",
        "Water-resistant, comfortable and between $50 and $120.",
        "Actually, make them white sneakers.",
    )
    for turn, message in enumerate(messages, start=1):
        print(f"Customer: {message}")
        decision = process_message(profile, message, turn, candidate_counts if turn == 1 else None)
        profile = decision.updated_profile
        _show(decision)


if __name__ == "__main__":
    main()
