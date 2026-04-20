from constants.prompts.research_agent_prompts import (
    DESTINATION_KNOWLEDGE_HUMAN_PROMPT,
    DESTINATION_KNOWLEDGE_SYSTEM_PROMPT,
    TRAVEL_ESSENTIALS_HUMAN_PROMPT,
    TRAVEL_ESSENTIALS_SYSTEM_PROMPT,
)
from services import research_agent_helpers as helpers


_normalize_destination_knowledge = helpers.normalize_destination_knowledge
_normalize_travel_essentials = helpers.normalize_travel_essentials


def normalize_research_input(state: dict) -> dict:
    """Compact the finalized information-curator handoff for downstream research."""
    selected_destination = state.get("selected_destination")
    if not isinstance(selected_destination, dict):
        raise ValueError("Selected destination is required before research.")

    followup_answers = helpers.clean_followup_answers(state.get("followup_answers") or [])
    custom_note = helpers.clean_text(state.get("followup_custom_note"))
    change_request = helpers.clean_text(state.get("followup_change_request"))
    curator_summary = helpers.build_curator_summary(
        selected_destination,
        followup_answers,
        custom_note,
        change_request,
    )

    research_input = {
        "destination": helpers.format_destination(selected_destination),
        "selected_destination": helpers.compact_destination(selected_destination),
        "trip": {
            "origin": helpers.clean_text(state.get("origin")),
            "start_date": helpers.clean_text(state.get("start_date")),
            "end_date": helpers.clean_text(state.get("end_date")),
            "trip_days": max(helpers.safe_int(state.get("trip_days"), 1), 1),
            "trip_type": helpers.clean_text(state.get("trip_type")),
            "budget_mode": helpers.clean_text(state.get("budget_mode")),
            "budget_value": state.get("budget_value"),
        },
        "group_signals": {
            "member_count": max(helpers.safe_int(state.get("member_count"), 1), 1),
            "has_kids": bool(state.get("has_kids")),
            "has_seniors": bool(state.get("has_seniors")),
        },
        "interests": helpers.infer_interests(selected_destination, followup_answers, custom_note, change_request),
        "pace": helpers.infer_pace(followup_answers, custom_note, change_request),
        "preferences": {
            "followup_answers": followup_answers,
            "custom_note": custom_note,
            "change_request": change_request,
        },
        "constraints": helpers.infer_known_constraints(state, selected_destination, custom_note, change_request),
        "curator_summary": curator_summary,
        "final_brief": curator_summary,
    }

    return {"research_input": helpers.strip_empty(research_input)}


def destination_knowledge_agent(state: dict) -> dict:
    """Research compact destination facts without making planning decisions."""
    research_input = helpers.require_dict(state, "research_input")
    payload = helpers.run_research_json(
        node_type="destination_knowledge",
        system_prompt=DESTINATION_KNOWLEDGE_SYSTEM_PROMPT,
        human_prompt=DESTINATION_KNOWLEDGE_HUMAN_PROMPT,
        variables={"research_input": helpers.to_json(research_input)},
        cache_payload={"research_input": research_input},
    )
    return {"destination_knowledge": helpers.normalize_destination_knowledge(payload)}


def travel_essentials_agent(state: dict) -> dict:
    """Research compact practical execution guidance without sightseeing planning."""
    research_input = helpers.require_dict(state, "research_input")
    essentials_input = helpers.essentials_input_projection(research_input)
    payload = helpers.run_research_json(
        node_type="travel_essentials",
        system_prompt=TRAVEL_ESSENTIALS_SYSTEM_PROMPT,
        human_prompt=TRAVEL_ESSENTIALS_HUMAN_PROMPT,
        variables={"research_input": helpers.to_json(essentials_input)},
        cache_payload={"research_input": essentials_input},
    )
    return {"travel_essentials": helpers.normalize_travel_essentials(payload)}


def research_aggregator(state: dict) -> dict:
    """Merge destination knowledge and travel essentials into one compact packet."""
    destination_knowledge = helpers.require_dict(state, "destination_knowledge")
    travel_essentials = helpers.require_dict(state, "travel_essentials")
    citations = helpers.merge_citations(
        destination_knowledge.get("citations") or [],
        travel_essentials.get("citations") or [],
    )
    warnings = helpers.dedupe(
        helpers.clean_str_list(destination_knowledge.get("planning_cautions") or [])
        + helpers.clean_str_list(travel_essentials.get("safety_and_health") or [])[:3]
        + helpers.clean_str_list(travel_essentials.get("special_trip_notes") or [])[:3]
    )

    packet = {
        "destination_knowledge": destination_knowledge,
        "travel_essentials": travel_essentials,
        "warnings": warnings[:10],
        "citations": citations,
    }
    return {
        "research_packet": packet,
        "citations": packet.get("citations") or citations,
        "research_warnings": helpers.clean_str_list(packet.get("warnings") or []),
    }


def validate_research_packet(state: dict) -> dict:
    """Validate fact-oriented research readiness for itinerary planning."""
    packet = state.get("research_packet")
    issues: list[str] = []
    repair_target = None

    if not isinstance(packet, dict):
        issues.append("research_packet is missing.")
        repair_target = "aggregate"
    else:
        destination = packet.get("destination_knowledge") if isinstance(packet.get("destination_knowledge"), dict) else {}
        essentials = packet.get("travel_essentials") if isinstance(packet.get("travel_essentials"), dict) else {}

        if not helpers.clean_text(destination.get("destination_overview")):
            issues.append("destination overview is missing.")
            repair_target = repair_target or "destination_knowledge"
        if not helpers.clean_dict_list(destination.get("key_place_clusters") or []):
            issues.append("key place cluster coverage is missing.")
            repair_target = repair_target or "destination_knowledge"
        if not (
            helpers.clean_str_list(destination.get("how_to_reach") or [])
            or helpers.clean_str_list(destination.get("movement_within_destination") or [])
        ):
            issues.append("reach or local movement guidance is missing.")
            repair_target = repair_target or "destination_knowledge"
        if not helpers.has_practical_coverage(essentials):
            issues.append("travel essentials coverage is missing.")
            repair_target = repair_target or "travel_essentials"
        if not helpers.clean_citations(packet.get("citations") or []):
            issues.append("citations are missing for factual research.")
            repair_target = repair_target or "destination_knowledge"
    previous_validation = state.get("research_validation") or {}
    repair_attempts = dict(previous_validation.get("repair_attempts") or {})
    if issues and repair_target:
        repair_attempts[repair_target] = repair_attempts.get(repair_target, 0) + 1
        if repair_attempts[repair_target] > 1:
            repair_target = None

    return {
        "research_validation": {
            "valid": not issues,
            "issues": issues,
            "repair_target": repair_target,
            "repair_attempts": repair_attempts,
        }
    }


def research_agent_output(state: dict) -> dict:
    """Expose a compact debug-friendly research result."""
    validation = state.get("research_validation") or {}
    packet = state.get("research_packet")
    if not validation.get("valid"):
        raise ValueError("research_agent_output requires valid research_validation.")
    if not isinstance(packet, dict):
        raise ValueError("research_packet is required for research_agent_output.")

    destination = packet.get("destination_knowledge") if isinstance(packet.get("destination_knowledge"), dict) else {}
    essentials = packet.get("travel_essentials") if isinstance(packet.get("travel_essentials"), dict) else {}
    essentials_topics = [
        field for field in helpers.TRAVEL_ESSENTIALS_LIST_FIELDS if helpers.clean_str_list(essentials.get(field) or [])
    ]

    return {
        "research_agent_output": {
            "destination_overview": destination.get("destination_overview"),
            "cluster_count": len(helpers.clean_dict_list(destination.get("key_place_clusters") or [])),
            "essentials_topics": essentials_topics,
            "citation_count": len(helpers.clean_citations(packet.get("citations") or [])),
            "valid": True,
        }
    }


