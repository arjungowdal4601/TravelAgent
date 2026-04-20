import copy

import pytest

from nodes.build_shortlist_cards import build_shortlist_cards
from nodes.routing import route_shortlist_decision


def _base_state(shortlisted_destinations: list[dict]) -> dict:
    return {
        "origin": "Bengaluru, Karnataka",
        "trip_days": 5,
        "shortlisted_destinations": shortlisted_destinations,
    }


def test_build_shortlist_cards_preserves_fields_and_adds_extras() -> None:
    state = _base_state(
        [
            {
                "card_title": "Himalayan Slow Escape",
                "state_or_region": "Himachal Pradesh",
                "trip_feel": "Cool weather with scenic drives",
                "places_covered": ["Manali", "Solang", "Naggar", "Kasol", "Jibhi"],
                "highlights": ["Mountain cafes", "River valleys", "Cable car", "Village walks", "Viewpoints", "Snow play"],
                "best_for": "Couples and relaxed groups",
                "pace": "relaxed",
                "duration_fit": "Comfortable for 5-6 days",
                "why_it_fits": "Good access from major metros",
                "estimated_price_range": "INR 45k-70k",
            },
            {
                "card_title": "Beach and Water Sports",
                "state_or_region": "Goa",
                "trip_feel": "Easy beach holiday",
                "places_covered": ["Candolim", "Anjuna", "Palolem"],
                "highlights": ["Sunset points", "Seafood", "Scooter rides"],
                "best_for": "Friends and couples",
                "pace": "balanced",
                "duration_fit": "Best for 4-5 days",
                "why_it_fits": "Simple logistics and transfers",
                "estimated_price_range": "INR 35k-65k",
            },
            {
                "card_title": "Royal Heritage Arc",
                "state_or_region": "Rajasthan",
                "trip_feel": "Culture-first journey",
                "places_covered": ["Jaipur", "Udaipur", "Jodhpur"],
                "highlights": ["Palaces", "Fort views", "Bazaars"],
                "best_for": "Families",
                "pace": "fast-paced",
                "duration_fit": "Tight but doable in 5 days",
                "why_it_fits": "Good train and flight links",
                "estimated_price_range": "INR 50k-85k",
            },
            {
                "card_title": "Tea Hills Retreat",
                "state_or_region": "Kerala",
                "trip_feel": "Green landscapes and quiet stays",
                "places_covered": ["Munnar", "Thekkady"],
                "highlights": ["Tea gardens", "Wildlife edge", "Spice trails"],
                "best_for": "Nature-loving families",
                "pace": "balanced",
                "duration_fit": "Ideal for 4-5 days",
                "why_it_fits": "Works well for mixed age groups",
                "estimated_price_range": "INR 40k-75k",
            },
        ]
    )

    output = build_shortlist_cards(copy.deepcopy(state))

    cards = output["shortlist_cards"]
    assert len(cards) == 4
    assert cards[0]["card_title"] == "Himalayan Slow Escape"
    assert cards[0]["trip_feel"] == "Cool weather with scenic drives"
    assert cards[0]["pace"] == "relaxed"
    assert len(cards[0]["places_covered"]) == 4
    assert len(cards[0]["highlights"]) == 5
    assert output["explained_shortlisted_destinations"] == cards


def test_build_shortlist_cards_uses_fallbacks_when_new_fields_missing() -> None:
    state = _base_state(
        [
            {
                "state_or_region": "Uttarakhand",
                "places_covered": ["Rishikesh", "Mussoorie"],
                "highlights": ["River walks", "Hill views"],
                "best_for": "Family trips",
                "duration_fit": "Good for 4-5 days",
                "why_it_fits": "Short drives and pleasant weather",
                "estimated_price_range": "INR 30k-55k",
            },
            {
                "state_or_region": "Sikkim",
                "places_covered": ["Gangtok"],
                "highlights": ["Monasteries"],
                "best_for": "Couples",
                "duration_fit": "Best in 5 days",
                "why_it_fits": "Compact mountain itinerary",
                "estimated_price_range": "INR 50k-80k",
            },
            {
                "state_or_region": "Andaman",
                "places_covered": ["Port Blair"],
                "highlights": ["Beaches"],
                "best_for": "Relaxed vacations",
                "duration_fit": "Best in 5-6 days",
                "why_it_fits": "Direct flights available",
                "estimated_price_range": "INR 65k-95k",
            },
            {
                "state_or_region": "Madhya Pradesh",
                "places_covered": ["Bhopal"],
                "highlights": ["Heritage"],
                "best_for": "Culture-focused trips",
                "duration_fit": "Good in 4 days",
                "why_it_fits": "Train-friendly access",
                "estimated_price_range": "INR 25k-45k",
            },
        ]
    )

    output = build_shortlist_cards(copy.deepcopy(state))
    first_card = output["shortlist_cards"][0]
    assert first_card["card_title"] == "Uttarakhand - Family trips"
    assert first_card["trip_feel"] == "Short drives and pleasant weather"
    assert first_card["pace"] == "balanced"


def test_build_shortlist_cards_requires_exactly_four_items() -> None:
    state = _base_state([{"state_or_region": "Goa"}])
    with pytest.raises(ValueError):
        build_shortlist_cards(state)


def test_route_shortlist_decision_paths_remain_stable() -> None:
    assert route_shortlist_decision({"shortlist_decision": "selected"}) == "call_generate_contextual_destination_questions"
    assert route_shortlist_decision({"shortlist_decision": "rejected"}) == "ask_half_baked_plan"
