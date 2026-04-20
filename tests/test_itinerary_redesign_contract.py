import json

import pytest
from langchain_core.runnables import RunnableLambda

from nodes.itinerary_agent import (
    _run_itinerary_json,
    _validate_final_itinerary,
    itinerary_planner,
    prepare_itinerary_input,
    render_clean_itinerary_markdown,
    show_separate_itinerary_view,
)


VALID_PACKET = {
    "destination_knowledge": {
        "destination_overview": "Compact hill trip with town and nature clusters.",
        "key_place_clusters": [
            {
                "name": "Main Town",
                "why_it_matters": "Best base for food and transfers.",
                "typical_time_need": "1 day",
            }
        ],
        "how_to_reach": ["Train or fly to the gateway city, then road transfer."],
        "movement_within_destination": ["Use cabs for spread-out clusters."],
        "signature_experiences": ["River walk"],
        "local_food_highlights": ["Local thali"],
        "planning_cautions": ["Avoid late-night hill drives."],
        "pace_signal": "Balanced pacing fits best.",
        "citations": [{"title": "Destination source", "url": "https://example.com/destination"}],
    },
    "travel_essentials": {
        "documents_and_permissions": ["Carry government ID."],
        "packing_and_carry": ["Carry light layers."],
        "safety_and_health": ["Avoid late transfers."],
        "citations": [{"title": "Essentials source", "url": "https://example.com/essentials"}],
    },
    "warnings": ["Avoid late-night hill drives."],
    "citations": [
        {"title": "Destination source", "url": "https://example.com/destination"},
        {"title": "Essentials source", "url": "https://example.com/essentials"},
    ],
}


VALID_FINAL = {
    "trip_summary": {
        "destination": "River Hills: Main Town",
        "dates": "2026-05-10 to 2026-05-11",
        "duration": "2 days",
        "origin": "Origin City, Origin State",
        "trip_type": "family",
        "group_type": "4 travelers with kids",
        "budget_mode": "standard",
        "planning_style": "balanced",
        "summary": "A short balanced river-and-town break.",
    },
    "how_to_reach": {
        "recommended_route": "Use the nearest major airport from Origin City, fly to Gateway Airport, then take a pre-booked cab to Main Town.",
        "route_legs": [
            {
                "from": "Origin City",
                "to": "Nearest Major Airport",
                "mode": "pre-booked cab",
                "duration_hint": "short city transfer",
                "booking_or_pickup_note": "Leave with airport buffer.",
            },
            {
                "from": "Nearest Major Airport",
                "to": "Gateway Airport",
                "mode": "flight",
                "duration_hint": "same-day connection",
                "booking_or_pickup_note": "Choose an arrival before late afternoon.",
            },
            {
                "from": "Gateway Airport",
                "to": "Main Town hotel",
                "mode": "pre-booked cab",
                "duration_hint": "road transfer",
                "booking_or_pickup_note": "Use hotel or verified operator pickup.",
            },
        ],
        "why_this_route": "It minimizes road fatigue for a short family trip.",
        "important_transit_note": "Verify transfer time before booking.",
    },
    "return_plan": {
        "route_summary": "Start from Main Town hotel, return to Gateway Airport by cab, then fly back to the origin-side airport.",
        "route_legs": [
            {
                "from": "Main Town hotel",
                "to": "Gateway Airport",
                "mode": "pre-booked cab",
                "duration_hint": "road transfer",
                "booking_or_pickup_note": "Start early.",
            },
            {
                "from": "Gateway Airport",
                "to": "Nearest Major Airport",
                "mode": "flight",
                "duration_hint": "same-day return",
                "booking_or_pickup_note": "Keep a buffer before onward local transfer.",
            },
        ],
        "departure_timing_note": "Start early on the final day.",
        "final_day_buffer_note": "Keep a buffer for road delays.",
    },
    "stay_plan": {
        "base_areas": ["Main town"],
        "why_this_base_fits": "It keeps food and transfers simple.",
        "stay_style_note": "Choose a family-friendly hotel near the base area.",
    },
    "local_transport": {
        "summary": "Use cabs for transfers and short autos where practical.",
        "recommended_modes": ["Cab", "Auto"],
        "transport_cautions": ["Avoid late hill-road transfers."],
    },
    "days": [
        {
            "day_number": 1,
            "city_or_base": "Main Town",
            "day_type": "arrival",
            "theme": "Arrival and easy local orientation",
            "transfer_plan": "Arrive at Gateway Airport and transfer to Main Town hotel.",
            "places": [{"name": "Riverfront Promenade", "area": "Main Town", "why_today": "Easy first evening after travel."}],
            "schedule_blocks": [
                {
                    "time_of_day": "afternoon",
                    "place_or_transfer": "Gateway Airport to Main Town hotel",
                    "activity": "Private transfer and check-in",
                    "pace_note": "Keep the travel day light.",
                },
                {
                    "time_of_day": "evening",
                    "place_or_transfer": "Riverfront Promenade",
                    "activity": "Short walk if everyone is fresh",
                    "pace_note": "Skip if arrival is delayed.",
                },
            ],
            "extra_time_nearby_places": [{"name": "Old Bridge Viewpoint", "area": "Main Town", "why_it_fits": "Close to the hotel zone."}],
            "food_suggestion": "Simple local dinner near base.",
            "estimated_spend": "Rs. 4,000-7,000",
            "day_note": "Keep it light after travel.",
        },
        {
            "day_number": 2,
            "city_or_base": "Main Town",
            "day_type": "departure",
            "theme": "Short sightseeing and return",
            "transfer_plan": "Checkout and return to Gateway Airport.",
            "places": [{"name": "Hill View Garden", "area": "Main Town edge", "why_today": "Short morning stop before return transfer."}],
            "schedule_blocks": [
                {
                    "time_of_day": "morning",
                    "place_or_transfer": "Hill View Garden",
                    "activity": "Brief viewpoint visit",
                    "pace_note": "Keep bags ready before leaving.",
                },
                {
                    "time_of_day": "afternoon",
                    "place_or_transfer": "Main Town hotel to Gateway Airport",
                    "activity": "Return transfer",
                    "pace_note": "Do not add distant sightseeing.",
                },
            ],
            "extra_time_nearby_places": [{"name": "Craft Lane", "area": "Main Town", "why_it_fits": "Works only if the flight is late."}],
            "food_suggestion": "Breakfast near stay.",
            "estimated_spend": "Rs. 5,000-8,000",
            "day_note": "Start early.",
        },
    ],
    "cost_summary": {
        "transport_estimate": "Rs. 10,000-18,000",
        "stay_estimate": "Rs. 4,000-8,000",
        "local_daily_estimate": "Rs. 3,000-5,000",
        "total_estimated_range": "Rs. 20,000-35,000",
        "assumptions": ["Excludes flights."],
    },
    "carry_list": ["Government ID", "Light jacket"],
    "important_notes": ["Verify road conditions."],
    "documents": ["Government ID"],
    "do_and_dont": ["Do start transfers early", "Don't overpack the first day"],
    "source_notes": [{"title": "Destination source", "url": "https://example.com/destination"}],
}


def _state() -> dict:
    return {
        "research_validation": {"valid": True},
        "research_packet": VALID_PACKET,
        "research_input": {
            "destination": "River Hills: Main Town",
            "trip": {
                "origin": "Origin City, Origin State",
                "start_date": "2026-05-10",
                "end_date": "2026-05-11",
                "trip_days": 2,
                "trip_type": "family",
                "budget_mode": "standard",
            },
            "group_signals": {"member_count": 4, "has_kids": True, "has_seniors": False},
            "preferences": {"followup_answers": []},
            "pace": "balanced",
        },
        "selected_destination": {"state_or_region": "River Hills", "places_covered": ["Main Town"]},
    }


def test_prepare_itinerary_input_uses_research_packet_v2_without_planning_buckets() -> None:
    output = prepare_itinerary_input(_state())
    itinerary_input = output["itinerary_input"]

    assert itinerary_input["research_packet"] == VALID_PACKET
    assert itinerary_input["planner_context"]["trip_summary"]["trip_days"] == 2
    assert "must_do_places" not in itinerary_input
    assert "optional_places" not in itinerary_input
    assert itinerary_input["source_refs"]


def test_itinerary_planner_accepts_one_json_object(monkeypatch) -> None:
    class Response:
        content = json.dumps(VALID_FINAL)

    class FakeModel:
        def bind_tools(self, *_args, **_kwargs):
            return RunnableLambda(lambda _input: Response())

        def bind(self, *_args, **_kwargs):
            return RunnableLambda(lambda _input: Response())

    monkeypatch.setattr("nodes.itinerary_agent.get_itinerary_llm", lambda: FakeModel())

    prepared = prepare_itinerary_input(_state())
    output = itinerary_planner(prepared)

    assert output["itinerary_validation"]["valid"] is True
    assert output["final_itinerary"]["days"][0]["day_number"] == 1


def test_itinerary_planner_sends_compact_planner_context(monkeypatch) -> None:
    captured_variables = {}

    def fake_run_itinerary_json(*, system_prompt, human_prompt, variables):
        captured_variables.update(variables)
        return VALID_FINAL

    monkeypatch.setattr("nodes.itinerary_agent._run_itinerary_json", fake_run_itinerary_json)

    prepared = prepare_itinerary_input(_state())
    output = itinerary_planner(prepared)
    planner_context = json.loads(captured_variables["research_input"])

    assert output["itinerary_validation"]["valid"] is True
    assert "trip_summary" in planner_context
    assert "traveler_group" in planner_context
    assert "trip" not in planner_context
    assert "research_packet" not in planner_context


def test_itinerary_parser_rejects_non_object(monkeypatch) -> None:
    class Response:
        content = "[]"

    class FakeModel:
        def bind_tools(self, *_args, **_kwargs):
            return RunnableLambda(lambda _input: Response())

        def bind(self, *_args, **_kwargs):
            return RunnableLambda(lambda _input: Response())

    monkeypatch.setattr("nodes.itinerary_agent.get_itinerary_llm", lambda: FakeModel())

    with pytest.raises(ValueError):
        _run_itinerary_json(system_prompt="system", human_prompt="human {value}", variables={"value": "x"})


def test_render_clean_itinerary_markdown_has_required_sections() -> None:
    state = {
        "final_itinerary": VALID_FINAL,
        "itinerary_validation": {"valid": True, "issues": []},
    }

    markdown = render_clean_itinerary_markdown(state)["final_itinerary_markdown"]

    for heading in [
        "# Final Itinerary",
        "## Trip Summary",
        "## Recommended Route",
        "## Return Plan",
        "## Stay Plan",
        "## Local Transport",
        "## Day-By-Day Itinerary",
        "## Cost Summary",
        "## Essentials",
        "## Sources",
    ]:
        assert heading in markdown

    ready = show_separate_itinerary_view({**state, "final_itinerary_markdown": markdown})
    assert ready == {"itinerary_view_ready": True}


def test_itinerary_validation_rejects_multiple_route_choices() -> None:
    invalid = json.loads(json.dumps(VALID_FINAL))
    invalid["how_to_reach"]["recommended_route"] = "Either fly or train depending on fares."

    validation = _validate_final_itinerary(invalid, prepare_itinerary_input(_state())["itinerary_input"])

    assert validation["valid"] is False
    assert "recommended route presents multiple competing travel choices." in validation["issues"]


def test_itinerary_validation_rejects_generic_day_without_places() -> None:
    invalid = json.loads(json.dumps(VALID_FINAL))
    invalid["days"][0]["places"] = []
    invalid["days"][0]["schedule_blocks"] = []
    invalid["days"][0]["transfer_plan"] = ""
    invalid["days"][0]["day_type"] = "sightseeing"
    invalid["days"][0]["main_plan"] = ["Morning heritage block", "Shopping stop"]

    validation = _validate_final_itinerary(invalid, prepare_itinerary_input(_state())["itinerary_input"])

    assert validation["valid"] is False
    assert any("generic day filler" in issue for issue in validation["issues"])


def test_itinerary_rendering_keeps_sources_out_of_daily_text() -> None:
    itinerary = json.loads(json.dumps(VALID_FINAL))
    itinerary["days"][0]["places"][0]["why_today"] = "Easy start. (example.org)"
    itinerary["days"][0]["schedule_blocks"][1]["activity"] = "Short walk [source](https://example.org/path)"

    markdown = render_clean_itinerary_markdown(
        {"final_itinerary": itinerary, "itinerary_validation": {"valid": True, "issues": []}}
    )["final_itinerary_markdown"]

    day_section = markdown.split("## Sources")[0]
    assert "example.org" not in day_section
    assert "[source](" not in day_section
