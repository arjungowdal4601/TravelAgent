from nodes.research_agent import (
    _normalize_destination_knowledge,
    _normalize_travel_essentials,
    research_agent_output,
    research_aggregator,
    validate_research_packet,
)
from nodes.routing import route_research_validation


def _valid_destination_knowledge() -> dict:
    return _normalize_destination_knowledge(
        {
            "destination_overview": "Compact mountain destination with spread-out clusters.",
            "key_place_clusters": [
                {
                    "name": "Main town",
                    "why_it_matters": "Best base for food and transfers.",
                    "typical_time_need": "1 day",
                }
            ],
            "how_to_reach": ["Fly or train to the nearest gateway, then use a road transfer."],
            "movement_within_destination": ["Use local cabs for spread-out sights."],
            "signature_experiences": ["Riverfront walks"],
            "local_food_highlights": ["Local thali"],
            "planning_cautions": ["Road travel can be slow in peak season."],
            "pace_signal": "Balanced pacing fits best.",
            "citations": [{"title": "Tourism board", "url": "https://example.com/destination"}],
        }
    )


def _valid_travel_essentials() -> dict:
    return _normalize_travel_essentials(
        {
            "documents_and_permissions": ["Carry government ID for hotel check-in."],
            "packing_and_carry": ["Carry a light jacket."],
            "local_dos": ["Start road transfers early."],
            "local_donts": [],
            "safety_and_health": ["Avoid late hill-road transfers."],
            "money_and_payments": ["Keep some cash for smaller vendors."],
            "connectivity_and_access": ["Connectivity can vary outside town."],
            "special_trip_notes": ["Build buffers around transfers."],
            "citations": [{"title": "Travel advisory", "url": "https://example.com/essentials"}],
        }
    )


def test_research_packet_v2_does_not_require_planning_buckets() -> None:
    state = {
        "destination_knowledge": _valid_destination_knowledge(),
        "travel_essentials": _valid_travel_essentials(),
    }

    aggregated = research_aggregator(state)
    packet = aggregated["research_packet"]

    assert "must_do_places" not in packet
    assert "optional_places" not in packet
    assert packet["citations"]

    validation = validate_research_packet(aggregated)["research_validation"]
    assert validation["valid"] is True

    output = research_agent_output({**aggregated, "research_validation": validation})
    assert output["research_agent_output"]["cluster_count"] == 1
    assert output["research_agent_output"]["citation_count"] == 2


def test_research_validation_routes_new_repair_targets() -> None:
    invalid = {
        "research_packet": {
            "destination_knowledge": {
                "key_place_clusters": [{"name": "Town"}],
                "how_to_reach": ["Road transfer"],
            },
            "travel_essentials": _valid_travel_essentials(),
            "citations": [{"title": "Source", "url": "https://example.com"}],
        }
    }

    validation = validate_research_packet(invalid)["research_validation"]

    assert validation["valid"] is False
    assert validation["repair_target"] == "destination_knowledge"
    assert route_research_validation({"research_validation": validation}) == "destination_knowledge_agent"


def test_travel_essentials_can_omit_irrelevant_empty_sections() -> None:
    essentials = _normalize_travel_essentials(
        {
            "documents_and_permissions": [],
            "packing_and_carry": ["Carry sunscreen."],
            "local_dos": [],
            "local_donts": [],
            "citations": [{"title": "Source", "url": "https://example.com"}],
        }
    )

    assert "documents_and_permissions" not in essentials
    assert essentials["packing_and_carry"] == ["Carry sunscreen."]
