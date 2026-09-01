from __future__ import annotations

from dataclasses import replace
import unittest

from src.profile import extract_constraints, new_profile, update_profile


def active(profile):
    return {(item.attribute, item.value, item.polarity) for item in profile.active_constraints}


class ProfileIntegrationRegressions(unittest.TestCase):
    def test_category_leaf_labels_and_grammatical_variants(self):
        for word, expected in (("dress", "dress"), ("dresses", "dress"),
                               ("skirt", "skirt"), ("skirts", "skirt"),
                               ("jeans", "jeans"), ("pants", "pants"),
                               ("trousers", "trousers"), ("shorts", "shorts"),
                               ("legging", "leggings"), ("leggings", "leggings")):
            with self.subTest(word=word):
                result = extract_constraints("I need " + word, 1)
                self.assertEqual([c.value for c in result if c.attribute == "category"], [expected])

    def test_dress_shoes_is_not_a_dress_category(self):
        result = extract_constraints("I need dress shoes", 1)
        self.assertEqual([c.value for c in result if c.attribute == "category"], ["shoes"])

    def test_no_preference_clears_active_query_and_new_value_clears_flag(self):
        profile = update_profile(new_profile("s", {}), "I need red shoes", 1)
        profile = update_profile(profile, "No preference for color", 2)
        self.assertNotIn("red", profile.query_terms)
        self.assertIn("color", profile.no_preference_attributes)
        self.assertTrue(any(c.value == "red" and not c.active for c in profile.constraints))
        profile = update_profile(profile, "Actually make them blue", 3)
        self.assertIn(("color", "blue", "include"), active(profile))
        self.assertNotIn("color", profile.no_preference_attributes)

    def test_no_additional_preference_preserves_requirement_but_exhausts_slot(self):
        profile = update_profile(new_profile("s", {}), "Must be cotton", 1)
        profile = replace(profile, last_asked_attribute="material")
        profile = update_profile(profile, "No additional preference", 2)
        self.assertIn(("material", "cotton", "include"), active(profile))
        self.assertIn("material", profile.exhausted_attributes)
        self.assertNotIn("material", profile.no_preference_attributes)
        profile = update_profile(profile, "Actually linen instead of cotton", 3)
        self.assertNotIn("material", profile.exhausted_attributes)
        self.assertIn(("material", "linen", "include"), active(profile))

    def test_an_additional_preference_and_curly_apostrophe(self):
        for reply in ("I don't have an additional preference for material.",
                      "I don\u2019t have any further preference for material."):
            with self.subTest(reply=reply):
                profile = update_profile(new_profile("s", {}), "Must be cotton", 1)
                profile = update_profile(profile, reply, 2)
                self.assertIn("material", profile.exhausted_attributes)
                self.assertIn(("material", "cotton", "include"), active(profile))

    def test_no_preference_then_explicit_exception_is_retained(self):
        profile = update_profile(new_profile("s", {}), "Blue shoes", 1)
        profile = update_profile(profile, "No preference for color, but not red", 2)
        self.assertNotIn("color", profile.no_preference_attributes)
        self.assertIn(("color", "red", "exclude"), active(profile))
        self.assertFalse(any(c.attribute == "color" and c.polarity == "include" for c in profile.active_constraints))

    def test_coordinated_exclusions_do_not_turn_into_positive_materials(self):
        for conjunction in ("and", "or"):
            with self.subTest(conjunction=conjunction):
                profile = update_profile(new_profile("s", {}), f"Avoid leather {conjunction} wool", 1)
                self.assertEqual(active(profile), {("material", "leather", "exclude"), ("material", "wool", "exclude")})
                self.assertEqual(profile.query_terms, ())

    def test_other_positive_material_does_not_erase_exclusion(self):
        profile = update_profile(new_profile("s", {}), "Avoid leather", 1)
        profile = update_profile(profile, "Must be cotton", 2)
        self.assertIn(("material", "leather", "exclude"), active(profile))
        self.assertIn(("material", "cotton", "include"), active(profile))

    def test_new_explicit_same_value_replaces_opposite_polarity(self):
        profile = update_profile(new_profile("s", {}), "Avoid leather", 1)
        profile = update_profile(profile, "Actually I want leather", 2)
        self.assertNotIn(("material", "leather", "exclude"), active(profile))
        self.assertIn(("material", "leather", "include"), active(profile))

    def test_targeted_replacement_uses_only_new_side_and_retains_unrelated(self):
        profile = update_profile(new_profile("s", {}), "Comfortable red cotton shoes under 80", 1)
        profile = update_profile(profile, "Switch material from cotton to leather", 2)
        profile = update_profile(profile, "Blue instead of red", 3)
        self.assertIn(("material", "leather", "include"), active(profile))
        self.assertIn(("color", "blue", "include"), active(profile))
        self.assertIn(("style", "comfortable", "include"), active(profile))
        self.assertIn(("budget", "under 80", "include"), active(profile))
        self.assertFalse(any(c.attribute == "brand" for c in profile.active_constraints))
        self.assertNotIn("red", profile.query_terms)
        self.assertNotIn("cotton", profile.query_terms)

    def test_start_over_clears_hard_constraints_and_question_history(self):
        profile = update_profile(new_profile("s", {}), "Red boots under 80", 1)
        profile = replace(profile, asked_attributes=frozenset({"color"}), last_asked_attribute="color")
        profile = update_profile(profile, "Start over. I need a dress", 2)
        self.assertEqual(active(profile), {("category", "dress", "include")})
        self.assertFalse(profile.asked_attributes)
        self.assertIsNone(profile.last_asked_attribute)

    def test_uncommon_phrases_are_whole_and_replaceable(self):
        profile = update_profile(new_profile("s", {}), "Key requirement is reflective trim", 1)
        self.assertIn("reflective trim", profile.query_terms)
        profile = update_profile(profile, "Actually what matters is reversible lining", 2)
        self.assertIn("reversible lining", profile.query_terms)
        self.assertNotIn("reflective trim", profile.query_terms)

    def test_all_semicolon_requirement_clauses_are_preserved(self):
        profile = update_profile(new_profile("s", {}), "What matters is: reflective trim; reversible lining", 1)
        self.assertIn("reflective trim", profile.query_terms)
        self.assertIn("reversible lining", profile.query_terms)

    def test_shopping_category_context_is_preserved_without_hard_adjective_claims(self):
        for phrase in ("Women Dresses", "Boots Mid-Calf", "Fashion Necklaces", "Outdoor & Work Snow & Cold Weather"):
            with self.subTest(phrase=phrase):
                profile = update_profile(new_profile("s", {}), f"I'm looking for {phrase}, but I'm still exploring.", 1)
                context = [c for c in profile.active_constraints if c.attribute == "category" and c.value == phrase.lower()]
                self.assertTrue(context)
                self.assertTrue(all(c.strength == "soft" for c in context))
                self.assertIn(phrase.lower(), profile.query_terms)
                self.assertFalse(any(c.attribute == "use_case" and c.value == phrase.lower() for c in profile.active_constraints))

    def test_soft_category_anchor_survives_preference_override(self):
        profile = update_profile(new_profile("s", {}), "I'm looking for Watches Wrist Watches.", 1)
        profile = update_profile(profile, "Actually, ignore my earlier preference. What I need is: water resistant.", 2)
        self.assertIn(("category", "watches wrist watches", "include"), active(profile))
        profile = update_profile(profile, "Start over. I need a dress", 3)
        self.assertNotIn("watches wrist watches", profile.query_terms)

    def test_category_anchor_does_not_retain_cleared_color_or_material(self):
        profile = update_profile(new_profile("s", {}), "I'm looking for black cotton dresses.", 1)
        category_values = [c.value for c in profile.active_constraints if c.attribute == "category"]
        self.assertTrue(category_values)
        self.assertFalse(any("black" in value or "cotton" in value for value in category_values))
        profile = update_profile(profile, "No preference for color", 2)
        profile = update_profile(profile, "Switch material from cotton to silk", 3)
        self.assertFalse(any("black" in value or "cotton" in value for value in profile.query_terms))
        self.assertIn("silk", profile.query_terms)

    def test_excluding_leaf_deactivates_matching_positive_category_anchor(self):
        profile = update_profile(new_profile("s", {}), "I'm looking for Women Dresses, but I'm still exploring.", 1)
        profile = update_profile(profile, "No dresses", 2)
        self.assertIn(("category", "dress", "exclude"), active(profile))
        self.assertFalse(any(c.attribute == "category" and c.polarity == "include" for c in profile.active_constraints))
        self.assertNotIn("women dresses", profile.query_terms)

    def test_negative_shopping_tail_is_not_positive_category_context(self):
        profile = update_profile(new_profile("s", {}), "I'm looking for shoes not boots.", 1)
        self.assertIn(("category", "boots", "exclude"), active(profile))
        self.assertIn(("category", "shoes", "include"), active(profile))
        self.assertFalse(any("boots" in value for value in profile.query_terms))

    def test_unrelated_category_exclusion_keeps_anchor(self):
        profile = update_profile(new_profile("s", {}), "I'm looking for Women Dresses.", 1)
        profile = update_profile(profile, "No boots", 2)
        self.assertIn(("category", "women dresses", "include"), active(profile))

    def test_explicit_for_use_case_is_not_copied_into_category_anchor(self):
        profile = update_profile(new_profile("s", {}), "I'm looking for boots for work.", 1)
        self.assertIn(("use_case", "work", "include"), active(profile))
        profile = update_profile(profile, "No preference for use case", 2)
        self.assertFalse(any("work" in value for value in profile.query_terms))
        contextual = update_profile(new_profile("s", {}), "I'm looking for Outdoor & Work Snow & Cold Weather.", 1)
        self.assertIn(("category", "outdoor & work snow & cold weather", "include"), active(contextual))

    def test_deictic_reply_framing_never_becomes_product_requirement(self):
        profile = update_profile(new_profile("s", {}), "For that, what matters is: reflective trim; reversible lining.", 1)
        self.assertEqual(set(profile.query_terms), {"reflective trim", "reversible lining"})
        self.assertFalse(any(c.attribute == "use_case" for c in profile.active_constraints))

    def test_incidental_category_in_description_does_not_replace_shopping_category(self):
        profile = update_profile(new_profile("s", {}), "I'm looking for Athletic Walking.", 1)
        profile = update_profile(profile, "A key requirement is: A Lightweight Sneaker, Which Is Suitable For Running.", 2)
        categories = [c for c in profile.active_constraints if c.attribute == "category"]
        self.assertEqual([c.value for c in categories], ["athletic walking"])
        self.assertIn("a lightweight sneaker, which is suitable for running", profile.query_terms)

    def test_no_preference_judgment_tail_does_not_become_brand(self):
        profile = replace(new_profile("s", {}), last_asked_attribute="brand")
        profile = update_profile(profile, "I don't have a preference for brand; please use your judgment.", 1)
        self.assertIn("brand", profile.no_preference_attributes)
        self.assertFalse(profile.active_constraints)

    def test_need_is_prefix_is_not_in_requirement_value(self):
        profile = update_profile(new_profile("s", {}), "Actually, ignore my earlier preference. What I need is: Department: Women.", 1)
        self.assertIn("department: women", profile.query_terms)
        self.assertFalse(any(c.value.startswith("is:") for c in profile.active_constraints))
        self.assertTrue(all(c.strength == "hard" for c in profile.active_constraints))

    def test_decimal_measurements_and_long_valid_phrases_survive(self):
        detail = "Package Dimensions: 8.37 x 3.42 x 1.1 inches"
        profile = update_profile(new_profile("s", {}), "For that, what matters is: " + detail + ".", 1)
        self.assertIn(detail.lower(), profile.query_terms)
        phrase = "A reversible panel with an embroidered border and a concealed compartment offers a distinctive silhouette for everyday occasions while keeping the original textured finish visible."
        profile = update_profile(new_profile("s", {}), "A key requirement is: " + phrase, 1)
        self.assertIn(phrase[:-1].lower(), profile.query_terms)

    def test_request_for_clarification_is_not_a_negative_feature(self):
        profile = replace(new_profile("s", {}), last_asked_attribute="feature")
        profile = update_profile(profile, "Those options are not quite right yet. Ask me about one specific attribute.", 1)
        self.assertFalse(profile.active_constraints)

    def test_colon_and_short_answer_keep_unknown_values(self):
        profile = update_profile(new_profile("s", {}), "Material: eucalyptus fiber", 1)
        self.assertIn(("material", "eucalyptus fiber", "include"), active(profile))
        profile = replace(profile, last_asked_attribute="category")
        profile = update_profile(profile, "Ballet flats", 2)
        self.assertIn(("category", "ballet flats", "include"), active(profile))
        self.assertIn("ballet flats", profile.query_terms)

    def test_negative_style_and_use_case_are_not_positive_query_terms(self):
        profile = update_profile(new_profile("s", {}), "Not formal. Avoid hiking", 1)
        self.assertNotIn("formal", profile.query_terms)
        self.assertNotIn("hiking", profile.query_terms)

    def test_budget_bounds_keep_inclusivity_and_around_is_not_under(self):
        values = [c.value for c in extract_constraints("At most 80", 1) if c.attribute == "budget"]
        self.assertEqual(values, ["<= 80"])
        values = [c.value for c in extract_constraints("Budget around 80", 1) if c.attribute == "budget"]
        self.assertEqual(values, ["around 80"])

    def test_physical_measurements_are_not_money_bounds(self):
        for phrase in ("fits up to 8-inch wrist circumference", "under 3 pounds",
                       "between 10 and 12 inches", "around 2 kilograms",
                       "lasts up to 8 hours", "at least 4 stars", "rating at most 5",
                       "under 30%", "between 2 and 4 years", "up to 5 out of 5"):
            with self.subTest(phrase=phrase):
                self.assertFalse(any(c.attribute == "budget" for c in extract_constraints(phrase, 1)))

    def test_measurement_clause_is_retained_without_false_budget(self):
        detail = "Gold-tone 18mm stainless steel expansion band fits up to 8-inch wrist circumference"
        profile = update_profile(new_profile("s", {}), "For that, what matters is: color: green; " + detail + ".", 1)
        self.assertFalse(any(c.attribute == "budget" for c in profile.active_constraints))
        self.assertIn(detail.lower(), profile.query_terms)
        self.assertIn(("color", "green", "include"), active(profile))

    def test_real_money_bounds_and_plain_budget_shorthand_still_work(self):
        examples = {"under $50": "under 50", "at most 50": "<= 50",
                    "up to $8": "<= 8", "between $10 and $12": "between 10 and 12",
                    "budget under 50": "under 50", "around $30": "around 30"}
        for phrase, expected in examples.items():
            with self.subTest(phrase=phrase):
                self.assertIn(expected, [c.value for c in extract_constraints(phrase, 1) if c.attribute == "budget"])

    def test_measurement_answer_is_not_forced_into_budget_slot(self):
        profile = replace(new_profile("s", {}), last_asked_attribute="budget")
        profile = update_profile(profile, "up to 8-inch wrist circumference", 1)
        self.assertFalse(any(c.attribute == "budget" for c in profile.active_constraints))

    def test_browsing_uncertainty_is_not_a_negative_product_feature(self):
        profile = update_profile(new_profile("s", {}), "I'm not sure, still exploring", 1)
        self.assertEqual(profile.intent_mode, "browsing")
        self.assertFalse(profile.active_constraints)

    def test_identical_repeated_update_is_idempotent(self):
        profile = update_profile(new_profile("s", {}), "Red shoes", 1)
        self.assertEqual(update_profile(profile, "Red shoes", 1), profile)


if __name__ == "__main__":
    unittest.main()
