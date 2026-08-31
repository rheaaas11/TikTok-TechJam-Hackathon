from __future__ import annotations

import unittest

from src.profile import extract_constraints, new_profile, update_profile


class ProfileTest(unittest.TestCase):
    def test_extracts_product_dna_from_specific_request(self) -> None:
        constraints = extract_constraints(
            "I need white leather ankle boots, size 8, under $80 for winter.", turn=1
        )
        found = {(item.attribute, item.value, item.polarity) for item in constraints}
        self.assertIn(("category", "boots", "include"), found)
        self.assertIn(("color", "white", "include"), found)
        self.assertIn(("material", "leather", "include"), found)
        self.assertIn(("budget", "under 80", "include"), found)
        self.assertIn(("use_case", "winter", "include"), found)

    def test_tracks_negative_preference_as_hard_exclusion(self) -> None:
        profile = update_profile(new_profile("session", {}), "I need shoes for a wedding, no heels.", 1)
        exclusions = [item for item in profile.active_constraints if item.polarity == "exclude"]
        self.assertEqual(len(exclusions), 1)
        self.assertEqual(exclusions[0].value, "heels")
        self.assertEqual(exclusions[0].strength, "hard")

    def test_override_deactivates_previous_soft_preference(self) -> None:
        profile = new_profile("session", {})
        profile = update_profile(profile, "I am looking for shoes and I prefer casual style.", 1)
        profile = update_profile(profile, "Actually, ignore my earlier preference. I need formal shoes.", 3)
        active_styles = [item.value for item in profile.active_constraints if item.attribute == "style"]
        inactive_styles = [item.value for item in profile.constraints if not item.active and item.attribute == "style"]
        self.assertIn("formal", active_styles)
        self.assertIn("casual", inactive_styles)

    def test_no_preference_records_last_requested_attribute(self) -> None:
        profile = new_profile("session", {})
        profile = update_profile(profile, "I need a jacket.", 1)
        profile = profile.__class__(**{**profile.__dict__, "last_asked_attribute": "material"})
        profile = update_profile(profile, "I don't have a preference for material.", 2)
        self.assertIn("material", profile.no_preference_attributes)
        self.assertNotIn("material", profile.active_attributes)

    def test_extracts_a_common_multiword_feature(self) -> None:
        profile = update_profile(new_profile("session", {}), "I need water-resistant shoes.", 1)
        self.assertIn("water resistant", [item.value for item in profile.active_constraints])

    def test_v2_extracts_budget_range_and_brand(self) -> None:
        constraints = extract_constraints("I want a blazer by Acme between $50 and $120.", turn=1)
        found = {(item.attribute, item.value) for item in constraints}
        self.assertIn(("budget", "between 50 and 120"), found)
        self.assertIn(("brand", "acme"), found)

    def test_v2_keeps_unrelated_soft_preferences_on_targeted_override(self) -> None:
        profile = new_profile("session", {})
        profile = update_profile(profile, "I want comfortable shoes.", 1)
        profile = update_profile(profile, "Actually, make them white sneakers.", 2)
        active = {(item.attribute, item.value) for item in profile.active_constraints}
        self.assertIn(("style", "comfortable"), active)
        self.assertIn(("category", "sneakers"), active)


if __name__ == "__main__":
    unittest.main()
