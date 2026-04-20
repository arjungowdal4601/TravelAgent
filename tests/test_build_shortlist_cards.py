import copy

import pytest

from nodes.await_shortlist_decision import await_shortlist_decision
from nodes.build_shortlist_cards import build_shortlist_cards
from nodes.call_destination_research_with_user_hint import (
    summarize_rejected_shortlists,
    validate_regenerated_shortlist,
)
from nodes.routing import route_shortlist_decision


def _base_state(shortlisted_destinations: list[dict]) -> dict:
    return {
        "origin": "Origin City, Origin State",
        "trip_days": 5,
        "shortlisted_destinations": shortlisted_destinations,
    }


def test_build_shortlist_cards_preserves_fields_and_adds_extras() -> None:
    state = _base_state(
        [
            {
                "card_title": "Northern Ridge Slow Escape",
                "state_or_region": "Northern Ridge",
                "trip_feel": "Cool weather with scenic drives",
                "places_covered": ["Pine Town", "Valley Point", "Old Hamlet", "River Bend", "Forest Edge"],
                "highlights": ["Mountain cafes", "River valleys", "Cable car", "Village walks", "Viewpoints", "Snow play"],
                "best_for": "Couples and relaxed groups",
                "pace": "relaxed",
                "duration_fit": "Comfortable for 5-6 days",
                "why_it_fits": "Good access from major metros",
                "estimated_price_range": "INR 45k-70k",
            },
            {
                "card_title": "Beach and Water Sports",
                "state_or_region": "Western Coast",
                "trip_feel": "Easy beach holiday",
                "places_covered": ["North Bay", "Cliff Cove", "South Sands"],
                "highlights": ["Sunset points", "Seafood", "Scooter rides"],
                "best_for": "Friends and couples",
                "pace": "balanced",
                "duration_fit": "Best for 4-5 days",
                "why_it_fits": "Simple logistics and transfers",
                "estimated_price_range": "INR 35k-65k",
            },
            {
                "card_title": "Royal Heritage Arc",
                "state_or_region": "Desert Heritage Belt",
                "trip_feel": "Culture-first journey",
                "places_covered": ["Pink Fort City", "Lake Palace Town", "Blue Hill Fort"],
                "highlights": ["Palaces", "Fort views", "Bazaars"],
                "best_for": "Families",
                "pace": "fast-paced",
                "duration_fit": "Tight but doable in 5 days",
                "why_it_fits": "Good train and flight links",
                "estimated_price_range": "INR 50k-85k",
            },
            {
                "card_title": "Tea Hills Retreat",
                "state_or_region": "Green Tea Highlands",
                "trip_feel": "Green landscapes and quiet stays",
                "places_covered": ["Tea Valley", "Spice Lake"],
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
    assert cards[0]["card_title"] == "Northern Ridge Slow Escape"
    assert cards[0]["trip_feel"] == "Cool weather with scenic drives"
    assert cards[0]["pace"] == "relaxed"
    assert len(cards[0]["places_covered"]) == 4
    assert len(cards[0]["highlights"]) == 5
    assert output["explained_shortlisted_destinations"] == cards


def test_build_shortlist_cards_uses_fallbacks_when_new_fields_missing() -> None:
    state = _base_state(
        [
            {
                "state_or_region": "River Hills",
                "places_covered": ["Rapid Town", "Mist Ridge"],
                "highlights": ["River walks", "Hill views"],
                "best_for": "Family trips",
                "duration_fit": "Good for 4-5 days",
                "why_it_fits": "Short drives and pleasant weather",
                "estimated_price_range": "INR 30k-55k",
            },
            {
                "state_or_region": "Eastern Mountain Ring",
                "places_covered": ["Monastery Base"],
                "highlights": ["Monasteries"],
                "best_for": "Couples",
                "duration_fit": "Best in 5 days",
                "why_it_fits": "Compact mountain itinerary",
                "estimated_price_range": "INR 50k-80k",
            },
            {
                "state_or_region": "Island Chain",
                "places_covered": ["Harbor Town"],
                "highlights": ["Beaches"],
                "best_for": "Relaxed vacations",
                "duration_fit": "Best in 5-6 days",
                "why_it_fits": "Direct flights available",
                "estimated_price_range": "INR 65k-95k",
            },
            {
                "state_or_region": "Central Heritage Plains",
                "places_covered": ["Lake Capital"],
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
    assert first_card["card_title"] == "River Hills - Family trips"
    assert first_card["trip_feel"] == "Short drives and pleasant weather"
    assert first_card["pace"] == "balanced"


def test_build_shortlist_cards_requires_exactly_four_items() -> None:
    state = _base_state([{"state_or_region": "Goa"}])
    with pytest.raises(ValueError):
        build_shortlist_cards(state)


def test_route_shortlist_decision_paths_remain_stable() -> None:
    assert route_shortlist_decision({"shortlist_decision": "selected"}) == "call_generate_contextual_destination_questions"
    assert route_shortlist_decision({"shortlist_decision": "rejected"}) == "ask_half_baked_plan"


def test_build_shortlist_cards_preserves_custom_hint_match_fields() -> None:
    state = _base_state(
        [
            {
                "card_title": f"Intent Trip {index}",
                "state_or_region": f"Intent Region {index}",
                "places_covered": [f"Intent Place {index}"],
                "highlights": ["Aligned mood", "Practical access", "Distinct cluster"],
                "best_for": "Custom preference",
                "duration_fit": "Fits the trip",
                "why_it_fits": "Matches the hint.",
                "estimated_price_range": "INR 40k-60k",
                "intent_match_reason": "Matches the custom destination feel.",
                "difference_from_rejected": "Uses a new cluster.",
            }
            for index in range(4)
        ]
    )

    cards = build_shortlist_cards(state)["shortlist_cards"]

    assert cards[0]["intent_match_reason"] == "Matches the custom destination feel."
    assert cards[0]["difference_from_rejected"] == "Uses a new cluster."


def test_rejecting_shortlist_stores_negative_feedback(monkeypatch) -> None:
    cards = [
        {"card_title": "Rejected One", "state_or_region": "Old Region", "places_covered": ["Old Place"]},
        {"card_title": "Rejected Two", "state_or_region": "Second Old Region", "places_covered": ["Second Old Place"]},
    ]
    monkeypatch.setattr("nodes.await_shortlist_decision.interrupt", lambda _: {"action": "reject"})

    output = await_shortlist_decision({"shortlist_cards": cards, "shortlist_attempt_count": 1})

    assert output["shortlist_decision"] == "rejected"
    assert output["rejected_shortlists"] == [cards]
    assert output["shortlist_attempt_count"] == 2


def test_rejected_shortlist_summary_is_compact() -> None:
    summaries = summarize_rejected_shortlists(
        [
            [
                {
                    "card_title": "Rejected Concept",
                    "state_or_region": "Rejected Region",
                    "places_covered": ["Old Place", "Second Place", "Third Place", "Fourth Place", "Fifth Place"],
                    "highlights": ["One", "Two", "Three", "Four", "Five"],
                }
            ]
        ]
    )

    assert summaries == [
        {
            "card_title": "Rejected Concept",
            "state_or_region": "Rejected Region",
            "places_covered": ["Old Place", "Second Place", "Third Place", "Fourth Place"],
            "highlights": ["One", "Two", "Three", "Four"],
        }
    ]


def test_regenerated_shortlist_rejects_repeated_cards() -> None:
    rejected = [
        [
            {"card_title": "Old Coast", "state_or_region": "Old Coast", "places_covered": ["North Beach", "South Beach"]},
            {"card_title": "Old Hills", "state_or_region": "Old Hills", "places_covered": ["Peak Town", "Lake Bend"]},
        ]
    ]
    regenerated = [
        {"card_title": "Old Coast", "state_or_region": "Old Coast", "places_covered": ["North Beach", "South Beach"]},
        {"card_title": "Old Hills Again", "state_or_region": "Old Hills", "places_covered": ["Peak Town", "Lake Bend"]},
        {"card_title": "New Forest", "state_or_region": "New Forest", "places_covered": ["Cedar Camp"]},
        {"card_title": "New Plateau", "state_or_region": "New Plateau", "places_covered": ["Mesa Base"]},
    ]

    with pytest.raises(ValueError):
        validate_regenerated_shortlist(regenerated, rejected, "quiet forest stay")


def test_regenerated_shortlist_allows_explicitly_requested_rejected_region() -> None:
    rejected = [
        [
            {"card_title": "Old Coast", "state_or_region": "Old Coast", "places_covered": ["North Beach", "South Beach"]},
            {"card_title": "Old Hills", "state_or_region": "Old Hills", "places_covered": ["Peak Town", "Lake Bend"]},
        ]
    ]
    regenerated = [
        {"card_title": "Old Coast Slow", "state_or_region": "Old Coast", "places_covered": ["North Beach"]},
        {"card_title": "Old Coast Active", "state_or_region": "Old Coast", "places_covered": ["South Beach"]},
        {"card_title": "Old Coast Food", "state_or_region": "Old Coast", "places_covered": ["Harbor Market"]},
        {"card_title": "Old Coast Calm", "state_or_region": "Old Coast", "places_covered": ["Lagoon Walk"]},
    ]

    validate_regenerated_shortlist(regenerated, rejected, "focus on Old Coast only")
