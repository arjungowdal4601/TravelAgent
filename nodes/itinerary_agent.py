from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.itinerary_agent_prompts import (
    ITINERARY_PLANNER_HUMAN_PROMPT,
    ITINERARY_PLANNER_SYSTEM_PROMPT,
    ITINERARY_REPAIR_HUMAN_PROMPT,
)
from llm import get_itinerary_llm
from services.research_agent_helpers import (
    extract_response_citations as _extract_response_citations,
)
from services.llm_response_parsing import extract_text_content, load_json_payload


PLANNER_REASONING = {"effort": "high"}
PLANNER_TOOLS = [{"type": "web_search"}]


def prepare_itinerary_input(state: dict) -> dict:
    """Create the planner input from validated fact-oriented research."""
    validation = state.get("research_validation") or {}
    if not validation.get("valid"):
        raise ValueError("Itinerary planning requires valid research_validation.")

    research_packet = _require_dict(state, "research_packet")

    research_input = state.get("research_input") if isinstance(state.get("research_input"), dict) else {}
    selected_destination = state.get("selected_destination") if isinstance(state.get("selected_destination"), dict) else {}
    trip = research_input.get("trip") if isinstance(research_input.get("trip"), dict) else {}
    group = research_input.get("group_signals") if isinstance(research_input.get("group_signals"), dict) else {}
    destination_name = _clean_text(research_input.get("destination"), _format_destination(selected_destination))
    source_refs = _compact_citations(research_packet.get("citations") or state.get("citations") or [])

    trip_summary = {
        "origin": _clean_text(trip.get("origin") or state.get("origin")),
        "start_date": _clean_text(trip.get("start_date") or state.get("start_date")),
        "end_date": _clean_text(trip.get("end_date") or state.get("end_date")),
        "trip_days": max(_safe_int(trip.get("trip_days") or state.get("trip_days"), 1), 1),
        "trip_type": _clean_text(trip.get("trip_type") or state.get("trip_type")),
        "budget_mode": _clean_text(trip.get("budget_mode") or state.get("budget_mode"), "standard"),
        "budget_value": trip.get("budget_value", state.get("budget_value")),
    }
    traveler_group = {
        "member_count": max(_safe_int(group.get("member_count") or state.get("member_count"), 1), 1),
        "has_kids": bool(group.get("has_kids") or state.get("has_kids")),
        "has_seniors": bool(group.get("has_seniors") or state.get("has_seniors")),
        "group_type": _group_label(group, state),
    }
    preferences = {
        "interests": _clean_str_list(research_input.get("interests") or []),
        "pace": _clean_text(research_input.get("pace"), "balanced"),
        "followup_answers": (research_input.get("preferences") or {}).get("followup_answers") or [],
        "custom_note": _clean_text((research_input.get("preferences") or {}).get("custom_note")),
        "change_request": _clean_text((research_input.get("preferences") or {}).get("change_request")),
    }
    destination = {
        "name": destination_name,
        "selected_destination": selected_destination,
    }
    warnings = _clean_str_list(state.get("research_warnings") or research_packet.get("warnings") or [])
    planner_context = _strip_empty(
        {
            "trip_summary": trip_summary,
            "traveler_group": traveler_group,
            "preferences": preferences,
            "destination": destination,
            "warnings": warnings,
            "source_refs": source_refs,
        }
    )

    itinerary_input = {
        "research_input": research_input,
        "planner_context": planner_context,
        "research_packet": research_packet,
        "trip_summary": trip_summary,
        "traveler_group": traveler_group,
        "preferences": preferences,
        "destination": destination,
        "warnings": warnings,
        "source_refs": source_refs,
    }

    return {
        "itinerary_input": _strip_empty(itinerary_input),
    }


def itinerary_planner(state: dict) -> dict:
    """Use GPT-5 with web search to synthesize the final itinerary structure."""
    itinerary_input = _require_dict(state, "itinerary_input")
    planner_context = itinerary_input.get("planner_context") or _planner_context_from_itinerary_input(itinerary_input)
    research_packet = itinerary_input.get("research_packet") or {}

    payload = _run_itinerary_json(
        system_prompt=ITINERARY_PLANNER_SYSTEM_PROMPT,
        human_prompt=ITINERARY_PLANNER_HUMAN_PROMPT,
        variables={
            "research_input": _to_json(planner_context),
            "research_packet": _to_json(research_packet),
        },
    )
    final_itinerary = _normalize_final_itinerary(payload, itinerary_input)
    validation = _validate_final_itinerary(final_itinerary, itinerary_input)
    if not validation.get("valid"):
        repair_payload = _run_itinerary_json(
            system_prompt=ITINERARY_PLANNER_SYSTEM_PROMPT,
            human_prompt=ITINERARY_REPAIR_HUMAN_PROMPT,
            variables={
                "research_input": _to_json(planner_context),
                "research_packet": _to_json(research_packet),
                "previous_itinerary": _to_json(final_itinerary),
                "validation_issues": _to_json(validation.get("issues") or []),
            },
        )
        final_itinerary = _normalize_final_itinerary(repair_payload, itinerary_input)
        validation = _validate_final_itinerary(final_itinerary, itinerary_input)
    return {"final_itinerary": final_itinerary, "itinerary_validation": validation}


def render_clean_itinerary_markdown(state: dict) -> dict:
    """Render concise user-facing markdown from the planner's structured output."""
    itinerary = _require_dict(state, "final_itinerary")
    validation = state.get("itinerary_validation") or {}
    if validation and not validation.get("valid", True):
        raise ValueError(f"Cannot render itinerary markdown: {validation.get('issues')}")

    summary = itinerary.get("trip_summary") or {}
    lines = [
        "# Final Itinerary",
        "",
        "## Trip Summary",
        f"- Destination: {_clean_text(summary.get('destination'), 'Selected destination')}",
        f"- Dates: {_clean_text(summary.get('dates'), 'Dates unavailable')}",
        f"- Duration: {_clean_text(summary.get('duration'), 'Duration unavailable')}",
        f"- Origin: {_clean_text(summary.get('origin'), 'Origin unavailable')}",
        f"- Trip type: {_clean_text(summary.get('trip_type'), 'Trip type unavailable')}",
        f"- Group type: {_clean_text(summary.get('group_type'), 'Travelers')}",
        f"- Budget mode: {_clean_text(summary.get('budget_mode'), 'standard')}",
        f"- Planning style: {_clean_text(summary.get('planning_style'), 'balanced')}",
    ]
    if _clean_text(summary.get("summary")):
        lines.append(f"- Summary: {_clean_text(summary.get('summary'))}")

    reach = itinerary.get("how_to_reach") or {}
    lines.extend(["", "## Recommended Route"])
    lines.append(f"- Route: {_clean_text(reach.get('recommended_route'), 'Route guidance unavailable')}")
    lines.extend(_render_route_legs(reach.get("route_legs") or []))
    if _clean_text(reach.get("why_this_route")):
        lines.append(f"- Why this route: {_clean_text(reach.get('why_this_route'))}")
    if _clean_text(reach.get("important_transit_note")):
        lines.append(f"- Important transit note: {_clean_text(reach.get('important_transit_note'))}")

    return_plan = itinerary.get("return_plan") or {}
    lines.extend(["", "## Return Plan"])
    lines.append(f"- Return route summary: {_clean_text(return_plan.get('route_summary'), 'Return route guidance unavailable')}")
    lines.extend(_render_route_legs(return_plan.get("route_legs") or []))
    if _clean_text(return_plan.get("departure_timing_note")):
        lines.append(f"- Departure timing note: {_clean_text(return_plan.get('departure_timing_note'))}")
    if _clean_text(return_plan.get("final_day_buffer_note")):
        lines.append(f"- Final-day buffer note: {_clean_text(return_plan.get('final_day_buffer_note'))}")

    stay = itinerary.get("stay_plan") or {}
    lines.extend(["", "## Stay Plan"])
    lines.extend(_markdown_bullets(_clean_str_list(stay.get("base_areas") or []), fallback="Base area guidance unavailable"))
    if _clean_text(stay.get("why_this_base_fits")):
        lines.append(f"- Why this base fits: {_clean_text(stay.get('why_this_base_fits'))}")
    if _clean_text(stay.get("stay_style_note")):
        lines.append(f"- Stay style note: {_clean_text(stay.get('stay_style_note'))}")

    transport = itinerary.get("local_transport") or {}
    lines.extend(["", "## Local Transport"])
    lines.append(f"- Summary: {_clean_text(transport.get('summary'), 'Local transport guidance unavailable')}")
    lines.extend(_markdown_bullets(_clean_str_list(transport.get("recommended_modes") or []), prefix="- Recommended mode"))
    lines.extend(_markdown_bullets(_clean_str_list(transport.get("transport_cautions") or []), prefix="- Caution"))

    lines.extend(["", "## Day-By-Day Itinerary"])
    for day in _clean_dict_list(itinerary.get("days") or []):
        lines.extend(_render_day(day))

    cost = itinerary.get("cost_summary") or {}
    lines.extend(["", "## Cost Summary"])
    lines.append(f"- Rough transport estimate: {_clean_text(cost.get('transport_estimate'), 'Estimate unavailable')}")
    lines.append(f"- Rough stay estimate: {_clean_text(cost.get('stay_estimate'), 'Estimate unavailable')}")
    lines.append(f"- Rough daily local estimate: {_clean_text(cost.get('local_daily_estimate'), 'Estimate unavailable')}")
    lines.append(f"- Total estimated range: {_clean_text(cost.get('total_estimated_range'), 'Estimate unavailable')}")
    lines.extend(_markdown_bullets(_clean_str_list(cost.get("assumptions") or []), prefix="- Assumption"))

    essentials = _dedupe_strings(
        _clean_str_list(itinerary.get("carry_list") or [])
        + _clean_str_list(itinerary.get("documents") or [])
        + _clean_str_list(itinerary.get("important_notes") or [])
        + _clean_str_list(itinerary.get("do_and_dont") or [])
    )
    lines.extend(["", "## Essentials"])
    lines.extend(
        _markdown_bullets(
            essentials[:18],
            fallback="Carry standard ID, booking confirmations, phone charger, and power bank.",
        )
    )

    source_notes = _compact_citations(itinerary.get("source_notes") or [])
    if source_notes:
        lines.extend(["", "## Sources"])
        for ref in source_notes[:10]:
            title = _clean_text(ref.get("title"), _clean_text(ref.get("url"), "Source"))
            url = _clean_text(ref.get("url"))
            if url:
                lines.append(f"- [{title}]({url})")

    markdown = "\n".join(lines).strip()
    return {"final_itinerary_markdown": markdown}


def show_separate_itinerary_view(state: dict) -> dict:
    """Mark that Streamlit can show the itinerary view."""
    if not _clean_text(state.get("final_itinerary_markdown")):
        raise ValueError("final_itinerary_markdown is required before showing the itinerary view.")
    if not isinstance(state.get("final_itinerary"), dict):
        raise ValueError("final_itinerary is required before showing the itinerary view.")
    return {"itinerary_view_ready": True}


def _planner_context_from_itinerary_input(itinerary_input: dict[str, Any]) -> dict[str, Any]:
    """Build the compact planner context sent alongside the research packet."""
    return _strip_empty(
        {
            "trip_summary": itinerary_input.get("trip_summary"),
            "traveler_group": itinerary_input.get("traveler_group"),
            "preferences": itinerary_input.get("preferences"),
            "destination": itinerary_input.get("destination"),
            "warnings": itinerary_input.get("warnings"),
            "source_refs": itinerary_input.get("source_refs"),
        }
    )


def _run_itinerary_json(*, system_prompt: str, human_prompt: str, variables: dict[str, Any]) -> dict[str, Any]:
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    model = get_itinerary_llm().bind_tools(
        PLANNER_TOOLS,
        tool_choice="web_search",
        reasoning=PLANNER_REASONING,
    )
    response = (prompt | model).invoke(variables)
    text = extract_text_content(response.content)
    payload = load_json_payload(text)
    if not isinstance(payload, dict):
        raise ValueError("Itinerary planner must return one JSON object.")
    citations = _compact_citations(
        _extract_response_citations(response.content) + _clean_dict_list(payload.get("source_notes") or payload.get("source_refs") or [])
    )
    if citations:
        payload["source_notes"] = citations
    return payload


def _normalize_final_itinerary(payload: dict[str, Any], itinerary_input: dict[str, Any]) -> dict[str, Any]:
    trip = itinerary_input.get("trip_summary") if isinstance(itinerary_input.get("trip_summary"), dict) else {}
    group = itinerary_input.get("traveler_group") if isinstance(itinerary_input.get("traveler_group"), dict) else {}
    destination = itinerary_input.get("destination") if isinstance(itinerary_input.get("destination"), dict) else {}
    research_input = itinerary_input.get("research_input") if isinstance(itinerary_input.get("research_input"), dict) else {}
    prefs = itinerary_input.get("preferences") if isinstance(itinerary_input.get("preferences"), dict) else {}
    source_notes = _compact_citations(payload.get("source_notes") or [])
    source_notes.extend(_compact_citations(itinerary_input.get("source_refs") or []))

    summary = payload.get("trip_summary") if isinstance(payload.get("trip_summary"), dict) else {}
    normalized = {
        "trip_summary": {
            "destination": _clean_text(summary.get("destination"), _clean_text(destination.get("name"), _clean_text(research_input.get("destination"), "Selected destination"))),
            "dates": _clean_text(summary.get("dates"), _dates_label(trip)),
            "duration": _clean_text(summary.get("duration"), f"{max(_safe_int(trip.get('trip_days'), 1), 1)} days"),
            "origin": _clean_text(summary.get("origin"), _clean_text(trip.get("origin"))),
            "trip_type": _clean_text(summary.get("trip_type"), _clean_text(trip.get("trip_type"))),
            "group_type": _clean_text(summary.get("group_type"), _clean_text(group.get("group_type"), "Travelers")),
            "budget_mode": _clean_text(summary.get("budget_mode"), _clean_text(trip.get("budget_mode"), "standard")),
            "planning_style": _clean_text(summary.get("planning_style"), _clean_text(prefs.get("pace"), "balanced")),
            "summary": _clean_text(summary.get("summary")),
        },
        "how_to_reach": _normalize_string_object(
            payload.get("how_to_reach"),
            {
                "recommended_route": "",
                "route_legs": [],
                "why_this_route": "",
                "important_transit_note": "",
            },
        ),
        "return_plan": _normalize_string_object(
            payload.get("return_plan"),
            {
                "route_summary": "",
                "route_legs": [],
                "departure_timing_note": "",
                "final_day_buffer_note": "",
            },
        ),
        "stay_plan": _normalize_string_object(
            payload.get("stay_plan"),
            {
                "base_areas": [],
                "why_this_base_fits": "",
                "stay_style_note": "",
            },
        ),
        "local_transport": _normalize_string_object(
            payload.get("local_transport"),
            {
                "summary": "",
                "recommended_modes": [],
                "transport_cautions": [],
            },
        ),
        "days": _normalize_days(payload.get("days") or []),
        "cost_summary": _normalize_string_object(
            payload.get("cost_summary"),
            {
                "transport_estimate": "",
                "stay_estimate": "",
                "local_daily_estimate": "",
                "total_estimated_range": "",
                "assumptions": [],
            },
        ),
        "carry_list": _clean_str_list(payload.get("carry_list") or [])[:10],
        "important_notes": _clean_str_list(payload.get("important_notes") or [])[:10],
        "documents": _clean_str_list(payload.get("documents") or [])[:8],
        "do_and_dont": _clean_str_list(payload.get("do_and_dont") or [])[:10],
        "source_notes": _compact_citations(source_notes)[:12],
    }
    return _strip_empty(normalized, keep_empty_keys={"documents"})


def _normalize_string_object(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    normalized = {}
    for key, fallback_value in fallback.items():
        value = raw.get(key, fallback_value)
        if key == "recommended_route" and not _clean_text(value):
            value = raw.get("best_practical_route", fallback_value)
        if key == "why_this_route" and not _clean_text(value):
            value = raw.get("suggested_arrival_strategy", fallback_value)
        if key == "route_legs":
            normalized[key] = _normalize_route_legs(value)
            continue
        if isinstance(fallback_value, list):
            normalized[key] = _clean_str_list(value or [])[:10]
        else:
            normalized[key] = _clean_text(value)
    return normalized


def _normalize_route_legs(values: Any) -> list[dict[str, str]]:
    legs = []
    for item in _clean_dict_list(values or []):
        leg = _strip_empty(
            {
                "from": _clean_text(item.get("from")),
                "to": _clean_text(item.get("to")),
                "mode": _clean_text(item.get("mode")),
                "duration_hint": _clean_text(item.get("duration_hint")),
                "booking_or_pickup_note": _clean_text(item.get("booking_or_pickup_note")),
            }
        )
        if leg:
            legs.append(leg)
    return legs[:8]


def _normalize_place_items(values: Any, reason_key: str) -> list[dict[str, str]]:
    places = []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []

    for value in values:
        if isinstance(value, str):
            place = {"name": _clean_text(value)}
        elif isinstance(value, dict):
            place = {
                "name": _clean_text(value.get("name")),
                "area": _clean_text(value.get("area")),
                reason_key: _clean_text(value.get(reason_key) or value.get("why_today") or value.get("why_it_fits")),
            }
        else:
            continue
        compact = _strip_empty(place)
        if compact:
            places.append(compact)
    return places[:8]


def _normalize_schedule_blocks(values: Any) -> list[dict[str, str]]:
    blocks = []
    for item in _clean_dict_list(values or []):
        block = _strip_empty(
            {
                "time_of_day": _clean_text(item.get("time_of_day")),
                "place_or_transfer": _clean_text(item.get("place_or_transfer")),
                "activity": _clean_text(item.get("activity")),
                "pace_note": _clean_text(item.get("pace_note")),
            }
        )
        if block:
            blocks.append(block)
    return blocks[:8]


def _normalize_days(values: Any) -> list[dict[str, Any]]:
    days = []
    for index, item in enumerate(_clean_dict_list(values)):
        day = {
            "day_number": max(_safe_int(item.get("day_number"), index + 1), 1),
            "city_or_base": _clean_text(item.get("city_or_base")),
            "day_type": _clean_text(item.get("day_type")),
            "theme": _clean_text(item.get("theme")),
            "transfer_plan": _clean_text(item.get("transfer_plan") or item.get("arrival_or_transfer")),
            "places": _normalize_place_items(item.get("places") or [], "why_today"),
            "schedule_blocks": _normalize_schedule_blocks(item.get("schedule_blocks") or []),
            "extra_time_nearby_places": _normalize_place_items(item.get("extra_time_nearby_places") or [], "why_it_fits"),
            "main_plan": _clean_str_list(item.get("main_plan") or [])[:8],
            "food_suggestion": _clean_text(item.get("food_suggestion")),
            "estimated_spend": _clean_text(item.get("estimated_spend")),
            "day_note": _clean_text(item.get("day_note")),
        }
        days.append(_strip_empty(day))
    return days


def _validate_final_itinerary(final_itinerary: dict[str, Any], itinerary_input: dict[str, Any]) -> dict[str, Any]:
    issues = []
    trip = itinerary_input.get("trip_summary") if isinstance(itinerary_input.get("trip_summary"), dict) else {}
    expected_days = max(_safe_int(trip.get("trip_days"), 1), 1)

    for section in ["trip_summary", "how_to_reach", "return_plan", "stay_plan", "local_transport", "cost_summary"]:
        if not isinstance(final_itinerary.get(section), dict) or not final_itinerary.get(section):
            issues.append(f"{section} is missing.")

    reach = final_itinerary.get("how_to_reach") if isinstance(final_itinerary.get("how_to_reach"), dict) else {}
    if not _clean_text(reach.get("recommended_route")):
        issues.append("recommended route is missing.")
    if not _normalize_route_legs(reach.get("route_legs") or []):
        issues.append("recommended route legs are missing.")
    if _has_route_choice_language(
        " ".join(
            [str(reach.get("recommended_route") or ""), str(reach.get("why_this_route") or "")]
            + [
                " ".join(str(value) for value in leg.values())
                for leg in _clean_dict_list(reach.get("route_legs") or [])
            ]
        )
    ):
        issues.append("recommended route presents multiple competing travel choices.")

    return_plan = final_itinerary.get("return_plan") if isinstance(final_itinerary.get("return_plan"), dict) else {}
    if not _normalize_route_legs(return_plan.get("route_legs") or []):
        issues.append("return route legs are missing.")

    days = _clean_dict_list(final_itinerary.get("days") or [])
    if len(days) != expected_days:
        issues.append(f"day count must be {expected_days}, got {len(days)}.")
    for index, day in enumerate(days):
        day_issues = _validate_day_grounding(day, index + 1)
        issues.extend(day_issues)

    if not _compact_citations(final_itinerary.get("source_notes") or []):
        issues.append("source notes are missing.")

    return {"valid": not issues, "issues": issues}


def _validate_day_grounding(day: dict[str, Any], day_number: int) -> list[str]:
    issues = []
    places = _normalize_place_items(day.get("places") or [], "why_today")
    schedule_blocks = _normalize_schedule_blocks(day.get("schedule_blocks") or [])
    main_plan = _clean_str_list(day.get("main_plan") or [])
    transfer_plan = _clean_text(day.get("transfer_plan"))
    day_type = _clean_text(day.get("day_type")).lower()

    has_transfer_or_rest_purpose = (
        any(keyword in day_type for keyword in ["arrival", "transfer", "rest", "buffer", "departure"])
        or _mentions_transfer_or_rest(transfer_plan)
        or any(_mentions_transfer_or_rest(" ".join(block.values())) for block in schedule_blocks)
        or any(_mentions_transfer_or_rest(item) for item in main_plan)
    )

    if not places and not schedule_blocks and not transfer_plan and not main_plan:
        issues.append(f"day {day_number} has no concrete plan.")
        return issues

    if not places and not has_transfer_or_rest_purpose:
        issues.append(f"day {day_number} must include named places or a concrete transfer/rest purpose.")

    if places and all(_is_generic_place_name(place.get("name")) for place in places):
        issues.append(f"day {day_number} places are too generic.")

    if not places and _contains_generic_day_filler(" ".join(main_plan + [transfer_plan])):
        issues.append(f"day {day_number} uses generic day filler without named places.")

    return issues


def _has_route_choice_language(text: str) -> bool:
    normalized = f" {_clean_text(text).lower()} "
    choice_patterns = [
        r"\boption\s+\d+\b",
        r"\barrival option\b",
        r"\beither\b",
        r"\bif fares\b",
        r"\bif timings\b",
        r"\bif schedules\b",
        r"\bflight\s+or\s+train\b",
        r"\btrain\s+or\s+flight\b",
        r"\bair\s+or\s+rail\b",
        r"\broad\s+or\s+rail\b",
    ]
    return any(re.search(pattern, normalized) for pattern in choice_patterns)


def _mentions_transfer_or_rest(text: str) -> bool:
    normalized = _clean_text(text).lower()
    keywords = [
        "arrive",
        "arrival",
        "depart",
        "departure",
        "checkout",
        "check-out",
        "check in",
        "check-in",
        "transfer",
        "drive",
        "flight",
        "train",
        "airport",
        "station",
        "rest",
        "buffer",
        "recovery",
    ]
    return any(keyword in normalized for keyword in keywords)


def _contains_generic_day_filler(text: str) -> bool:
    normalized = _clean_text(text).lower()
    generic_patterns = [
        "heritage block",
        "photo stop",
        "orientation drive",
        "orientation loop",
        "local sightseeing",
        "shopping stop",
        "city tour",
        "market stroll",
        "easy evening",
        "gentle drive",
        "old-city drive",
    ]
    return any(pattern in normalized for pattern in generic_patterns)


def _is_generic_place_name(value: Any) -> bool:
    normalized = _clean_text(value).lower()
    if not normalized:
        return True
    generic_names = {
        "heritage block",
        "photo stop",
        "orientation drive",
        "orientation loop",
        "local sightseeing",
        "shopping stop",
        "city tour",
        "market stroll",
        "old city",
        "old-city",
        "viewpoint",
        "nearby place",
    }
    return normalized in generic_names


def _render_day(day: dict[str, Any]) -> list[str]:
    number = max(_safe_int(day.get("day_number"), 1), 1)
    lines = ["", f"### Day {number}"]
    if _clean_text(day.get("city_or_base")):
        lines.append(f"- City/base: {_clean_text(day.get('city_or_base'))}")
    if _clean_text(day.get("day_type")):
        lines.append(f"- Day type: {_clean_text(day.get('day_type'))}")
    if _clean_text(day.get("theme")):
        lines.append(f"- Theme: {_clean_text(day.get('theme'))}")
    if _clean_text(day.get("transfer_plan")):
        lines.append(f"- Transfer plan: {_clean_text(day.get('transfer_plan'))}")
    places = _normalize_place_items(day.get("places") or [], "why_today")
    if places:
        lines.append("- Places:")
        for place in places:
            detail = _format_place_detail(place, "why_today")
            lines.append(f"  - {detail}")
    schedule_blocks = _normalize_schedule_blocks(day.get("schedule_blocks") or [])
    if schedule_blocks:
        lines.append("- Plan:")
        for block in schedule_blocks:
            time_of_day = _clean_text(block.get("time_of_day"), "Plan")
            target = _clean_text(block.get("place_or_transfer"))
            activity = _clean_text(block.get("activity"))
            pace_note = _clean_text(block.get("pace_note"))
            description = " - ".join(part for part in [target, activity, pace_note] if part)
            lines.append(f"  - {time_of_day.title()}: {description}")
    elif (plan := _clean_str_list(day.get("main_plan") or [])):
        lines.append("- Main plan:")
        lines.extend([f"  - {item}" for item in plan])
    extras = _normalize_place_items(day.get("extra_time_nearby_places") or [], "why_it_fits")
    if extras:
        lines.append("- Extra time nearby:")
        for place in extras:
            detail = _format_place_detail(place, "why_it_fits")
            lines.append(f"  - {detail}")
    if _clean_text(day.get("food_suggestion")):
        lines.append(f"- Food suggestion: {_clean_text(day.get('food_suggestion'))}")
    if _clean_text(day.get("estimated_spend")):
        lines.append(f"- Spend estimate: {_clean_text(day.get('estimated_spend'))}")
    if _clean_text(day.get("day_note")):
        lines.append(f"- Day note: {_clean_text(day.get('day_note'))}")
    return lines


def _render_route_legs(values: Any) -> list[str]:
    lines = []
    for index, leg in enumerate(_normalize_route_legs(values), start=1):
        from_value = _clean_text(leg.get("from"), "Start")
        to_value = _clean_text(leg.get("to"), "End")
        mode = _clean_text(leg.get("mode"), "transfer")
        duration = _clean_text(leg.get("duration_hint"))
        note = _clean_text(leg.get("booking_or_pickup_note"))
        detail = f"{from_value} to {to_value}: {mode}"
        if duration:
            detail += f" ({duration})"
        if note:
            detail += f" - {note}"
        lines.append(f"- Leg {index}: {detail}")
    return lines


def _format_place_detail(place: dict[str, Any], reason_key: str) -> str:
    name = _clean_text(place.get("name"), "Place")
    area = _clean_text(place.get("area"))
    reason = _clean_text(place.get(reason_key))
    detail = name
    if area:
        detail += f" ({area})"
    if reason:
        detail += f" - {reason}"
    return detail


def _dates_label(trip: dict[str, Any]) -> str:
    start = _clean_text(trip.get("start_date"))
    end = _clean_text(trip.get("end_date"))
    if start and end:
        return f"{start} to {end}"
    return start or end


def _group_label(group: dict[str, Any], state: dict[str, Any]) -> str:
    member_count = max(_safe_int(group.get("member_count") or state.get("member_count"), 1), 1)
    has_kids = bool(group.get("has_kids") or state.get("has_kids"))
    has_seniors = bool(group.get("has_seniors") or state.get("has_seniors"))
    labels = [f"{member_count} traveler" + ("s" if member_count != 1 else "")]
    if has_kids:
        labels.append("with kids")
    if has_seniors:
        labels.append("with seniors")
    return ", ".join(labels)


def _format_destination(selected_destination: dict[str, Any]) -> str:
    region = _clean_text(selected_destination.get("state_or_region") or selected_destination.get("card_title"), "Selected destination")
    places = _clean_str_list(selected_destination.get("places_covered") or [])
    return f"{region}: {', '.join(places)}" if places else region


def _compact_citations(values: Any) -> list[dict[str, str]]:
    compacted = []
    seen_urls = set()
    for item in _clean_dict_list(values or []):
        url = _clean_text(item.get("url"))
        if not url:
            continue
        url_key = url.lower().strip()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        compacted.append({"title": _clean_text(item.get("title"), url), "url": url})
    return compacted


def _markdown_bullets(values: list[str], fallback: str | None = None, prefix: str = "-") -> list[str]:
    if not values:
        return [f"- {fallback}"] if fallback else []
    if prefix == "-":
        return [f"- {value}" for value in values]
    return [f"{prefix}: {value}" for value in values]


def _clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        cleaned = value.strip()
    else:
        cleaned = str(value).strip()
    cleaned = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", cleaned)
    cleaned = re.sub(
        r"\s*\((?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^)]*)?\)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = " ".join(cleaned.split())
    return cleaned or fallback


def _clean_str_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    cleaned = []
    seen = set()
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned


def _dedupe_strings(values: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned


def _clean_dict_list(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        if isinstance(value, dict):
            item = _strip_empty(value)
            if isinstance(item, dict) and item:
                cleaned.append(item)
    return cleaned


def _strip_empty(value: Any, keep_empty_keys: set[str] | None = None) -> Any:
    keep_empty_keys = keep_empty_keys or set()
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = _strip_empty(item, keep_empty_keys)
            if key in keep_empty_keys or normalized not in ({}, [], None, ""):
                cleaned[key] = normalized
        return cleaned
    if isinstance(value, list):
        return [item for raw in value if (item := _strip_empty(raw, keep_empty_keys)) not in ({}, [], None, "")]
    return value


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _require_dict(state: dict, key: str) -> dict[str, Any]:
    value = state.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} is required before itinerary planning can continue.")
    return value


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
