from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.itinerary_agent_prompts import (
    DAY_PLANNING_HUMAN_PROMPT,
    DAY_PLANNING_SYSTEM_PROMPT,
    LIVE_TRIP_CONTEXT_HUMAN_PROMPT,
    LIVE_TRIP_CONTEXT_SYSTEM_PROMPT,
)
from llm import get_itinerary_llm
from nodes.call_destination_research import _extract_text_content, _load_json_payload
from nodes.itinerary_artifacts import make_itinerary_run_id, write_itinerary_artifact
from nodes.research_agent import _extract_response_citations


PROJECTION_CHAR_BUDGET = 12000
MARKDOWN_STATE_CHAR_BUDGET = 16000
CURRENCY = "Rs. "


def prepare_itinerary_input(state: dict) -> dict:
    """Create one compact planner input from validated research and trip state."""
    validation = state.get("research_validation") or {}
    if not validation.get("valid"):
        raise ValueError("Itinerary planning requires valid research_validation.")

    research_packet = _require_dict(state, "research_packet")
    research_input = state.get("research_input") if isinstance(state.get("research_input"), dict) else {}
    selected_destination = state.get("selected_destination") if isinstance(state.get("selected_destination"), dict) else {}
    trip = research_input.get("trip") if isinstance(research_input.get("trip"), dict) else {}
    group = research_input.get("group_signals") if isinstance(research_input.get("group_signals"), dict) else {}

    destination_name = _clean_text(research_input.get("destination")) or _format_destination(selected_destination)
    source_refs = _compact_citations(research_packet.get("citations") or state.get("citations") or [])
    run_id = make_itinerary_run_id(
        {
            "destination": destination_name,
            "origin": trip.get("origin") or state.get("origin"),
            "start_date": trip.get("start_date") or state.get("start_date"),
            "end_date": trip.get("end_date") or state.get("end_date"),
        }
    )

    warnings = _clean_str_list(state.get("research_warnings") or [])
    if _clean_text(selected_destination.get("estimated_price_range")):
        warnings.append("Shortlist estimated_price_range is ignored for factual itinerary pricing.")

    itinerary_input = {
        "trip_summary": {
            "origin": _clean_text(trip.get("origin") or state.get("origin")),
            "start_date": _clean_text(trip.get("start_date") or state.get("start_date")),
            "end_date": _clean_text(trip.get("end_date") or state.get("end_date")),
            "trip_days": max(_safe_int(trip.get("trip_days") or state.get("trip_days"), 1), 1),
            "trip_type": _clean_text(trip.get("trip_type") or state.get("trip_type")),
            "member_count": max(_safe_int(group.get("member_count") or state.get("member_count"), 1), 1),
            "budget_mode": _clean_text(trip.get("budget_mode") or state.get("budget_mode"), "standard"),
            "budget_value": trip.get("budget_value", state.get("budget_value")),
        },
        "destination": {
            "name": destination_name,
            "summary": _clean_text(research_packet.get("destination_summary")),
            "duration_fit": _clean_text(research_packet.get("duration_fit")),
            "selected_places": _clean_str_list(selected_destination.get("places_covered") or []),
            "highlights": _clean_str_list(selected_destination.get("highlights") or []),
        },
        "traveler_group": {
            "member_count": max(_safe_int(group.get("member_count") or state.get("member_count"), 1), 1),
            "has_kids": bool(group.get("has_kids") or state.get("has_kids")),
            "has_seniors": bool(group.get("has_seniors") or state.get("has_seniors")),
        },
        "preferences": {
            "interests": _clean_str_list(research_input.get("interests") or []),
            "pace": _clean_text(research_input.get("pace"), "balanced"),
            "followup": research_input.get("custom_preferences") or {},
        },
        "area_clusters": _clean_dict_list(research_packet.get("area_clusters") or [])[:8],
        "must_do_places": _clean_dict_list(research_packet.get("must_do_places") or [])[:12],
        "optional_places": _clean_dict_list(research_packet.get("optional_places") or [])[:10],
        "best_food": _clean_str_list(research_packet.get("best_food") or [])[:8],
        "best_experiences": _clean_str_list(research_packet.get("best_experiences") or [])[:8],
        "best_activities": _clean_str_list(research_packet.get("best_activities") or [])[:8],
        "practical_notes": _clean_practical_notes(research_packet.get("practical_notes") or {}),
        "constraints": _dedupe(
            _clean_str_list(research_packet.get("constraints") or [])
            + _clean_str_list(research_input.get("constraints") or [])
        )[:10],
        "assumptions": _clean_str_list(research_packet.get("assumptions") or [])[:8],
        "warnings": _dedupe(warnings)[:8],
        "source_refs": source_refs[:12],
    }

    return {
        "itinerary_input": _strip_empty(itinerary_input, keep_empty_keys={"optional_places"}),
        "itinerary_run_id": run_id,
    }


def fetch_live_trip_context(state: dict) -> dict:
    """Fetch only the live context needed to make costs and timing practical."""
    itinerary_input = _require_dict(state, "itinerary_input")
    projection = _build_live_context_projection(itinerary_input)
    assert_projection_budget(projection, "live trip context")

    try:
        payload = _run_live_context_llm(projection)
    except Exception:
        payload = {}

    return {"trip_live_context": _normalize_live_context(payload, itinerary_input)}


def build_trip_skeleton(state: dict) -> dict:
    """Create a simple ordered day structure for sequential planning."""
    itinerary_input = _require_dict(state, "itinerary_input")
    live_context = state.get("trip_live_context") if isinstance(state.get("trip_live_context"), dict) else {}
    trip = itinerary_input.get("trip_summary") or {}
    group = itinerary_input.get("traveler_group") or {}
    trip_days = max(_safe_int(trip.get("trip_days"), 1), 1)
    start = _parse_date(_clean_text(trip.get("start_date")))
    primary_base = _best_stay_area(itinerary_input, live_context)

    days = []
    for index in range(trip_days):
        current = start + timedelta(days=index)
        if trip_days == 1:
            day_type = "arrival_departure_light"
            intensity = "light"
        elif index == 0:
            day_type = "arrival_light"
            intensity = "light"
        elif index == trip_days - 1:
            day_type = "departure_light"
            intensity = "light"
        else:
            day_type = "sightseeing"
            intensity = "easy" if group.get("has_kids") or group.get("has_seniors") else "balanced"

        days.append(
            {
                "day_id": f"D{index}",
                "day_index": index,
                "date": current.isoformat(),
                "title_placeholder": _title_placeholder(day_type, primary_base),
                "day_type": day_type,
                "base_area": primary_base,
                "day_intensity": intensity,
                "arrival_logistics_needed": index == 0,
                "return_logistics_needed": index == trip_days - 1,
            }
        )

    return {
        "trip_skeleton": {
            "trip_days": trip_days,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=trip_days - 1)).isoformat(),
            "day_slots": days,
            "base_area": primary_base,
        }
    }


def plan_days_sequentially(state: dict) -> dict:
    """Plan all days in order inside one graph node."""
    itinerary_input = _require_dict(state, "itinerary_input")
    live_context = state.get("trip_live_context") if isinstance(state.get("trip_live_context"), dict) else {}
    skeleton = _require_dict(state, "trip_skeleton")
    slots = _clean_dict_list(skeleton.get("day_slots") or [])
    assignments = _assign_places_to_slots(slots, itinerary_input)

    planned_days = []
    planned_place_names: list[str] = []
    for slot in slots:
        day_id = _clean_text(slot.get("day_id"))
        candidates = assignments.get(day_id, [])
        day_input = {
            "slot": slot,
            "destination": itinerary_input.get("destination") or {},
            "traveler_group": itinerary_input.get("traveler_group") or {},
            "preferences": itinerary_input.get("preferences") or {},
            "candidates": candidates,
            "food_ideas": _clean_str_list(itinerary_input.get("best_food") or [])[:4],
            "live_context": _compact_live_context_for_day(live_context, candidates),
            "logistics": _compact_logistics_for_day(live_context, slot, itinerary_input),
            "already_planned_places": planned_place_names,
            "rules": [
                "Keep arrival and departure days light.",
                "Arrival day must include origin-to-destination travel and hotel/base area check-in.",
                "Departure day must include checkout and return travel.",
                "Use hotel/base area unless a specific hotel is source-backed.",
                "Use short timed schedule bullets.",
                "Every day must include breakfast, lunch, dinner, and total spend.",
                "Do not output Not priced.",
            ],
        }
        assert_projection_budget(day_input, f"day planner {day_id}")

        try:
            raw_day = _run_day_planner_llm(day_input)
        except Exception:
            raw_day = {}

        day = _normalize_day_packet(raw_day, slot, candidates, itinerary_input, live_context)
        planned_days.append(day)
        planned_place_names.extend(_planned_place_names(day))

    return {"day_itinerary_packets": planned_days}


def aggregate_final_itinerary(state: dict) -> dict:
    """Build one compact structured final itinerary object."""
    itinerary_input = _require_dict(state, "itinerary_input")
    live_context = state.get("trip_live_context") if isinstance(state.get("trip_live_context"), dict) else {}
    days = sorted(
        _clean_dict_list(state.get("day_itinerary_packets") or []),
        key=lambda item: _safe_int(item.get("day_index"), 0),
    )
    trip = itinerary_input.get("trip_summary") or {}
    destination = itinerary_input.get("destination") or {}
    practical_notes = itinerary_input.get("practical_notes") or {}
    trip_notes = _trip_level_notes(itinerary_input, live_context)
    carry_list = _carry_list(practical_notes)
    documents = _documents(practical_notes)
    travel_logistics = _travel_logistics(live_context)
    stay_plan = _stay_plan(itinerary_input, live_context)
    local_transport = _local_transport_plan(live_context)
    cost_summary = _cost_summary(days, stay_plan, travel_logistics, local_transport)
    source_notes = _source_notes(itinerary_input, live_context)

    final_itinerary = {
        "trip_brief": {
            "destination": _clean_text(destination.get("name"), "Selected destination"),
            "origin": _clean_text(trip.get("origin")),
            "dates": f"{_clean_text(trip.get('start_date'))} to {_clean_text(trip.get('end_date'))}",
            "duration": f"{_safe_int(trip.get('trip_days'), len(days))} days",
            "travelers": _traveler_label(itinerary_input),
            "budget_mode": _clean_text(trip.get("budget_mode"), "standard"),
            "summary": _clean_text(destination.get("summary")),
        },
        "travel_logistics": travel_logistics,
        "stay_plan": stay_plan,
        "local_transport": local_transport,
        "days": days,
        "trip_notes": trip_notes,
        "carry_list": carry_list,
        "documents": documents,
        "do_and_dont": _do_and_dont(practical_notes),
        "cost_summary": cost_summary,
        "source_notes": source_notes,
    }
    validation = _validate_compact_itinerary(final_itinerary, itinerary_input)
    return {"final_itinerary": _strip_empty(final_itinerary, keep_empty_keys={"documents"}), "itinerary_validation": validation}


def render_clean_itinerary_markdown(state: dict) -> dict:
    """Render concise user-facing markdown from final_itinerary only."""
    itinerary = _require_dict(state, "final_itinerary")
    validation = state.get("itinerary_validation") or {}
    if validation and not validation.get("valid", True):
        raise ValueError(f"Cannot render itinerary markdown: {validation.get('issues')}")

    brief = itinerary.get("trip_brief") or {}
    lines = [
        "# Final Itinerary",
        "",
        "## Trip Summary",
        f"- Destination: {_clean_text(brief.get('destination'))}",
        f"- Dates: {_clean_text(brief.get('dates'))}",
        f"- Duration: {_clean_text(brief.get('duration'))}",
        f"- Origin: {_clean_text(brief.get('origin'))}",
        f"- Travelers: {_clean_text(brief.get('travelers'))}",
    ]

    lines.extend(_render_how_to_reach(itinerary.get("travel_logistics") or {}))
    lines.extend(_render_return_plan(itinerary.get("travel_logistics") or {}))
    lines.extend(_render_stay_plan(itinerary.get("stay_plan") or {}))
    lines.extend(_render_local_transport(itinerary.get("local_transport") or {}))

    lines.extend(["", "## Day-By-Day Itinerary"])
    for day in _clean_dict_list(itinerary.get("days") or []):
        lines.extend(_render_compact_day(day))

    cost_summary = itinerary.get("cost_summary") or {}
    lines.extend(["", "## Cost Summary"])
    lines.append(f"- Trip estimate: {_clean_text(cost_summary.get('trip_total_label'), 'Estimate unavailable')}")
    if _clean_text(cost_summary.get("daily_spend_label")):
        lines.append(f"- Daily itinerary spend: {_clean_text(cost_summary.get('daily_spend_label'))}")
    if _clean_text(cost_summary.get("stay_total_label")):
        lines.append(f"- Stay estimate: {_clean_text(cost_summary.get('stay_total_label'))}")
    if _clean_text(cost_summary.get("arrival_transport_label")):
        lines.append(f"- Arrival transport: {_clean_text(cost_summary.get('arrival_transport_label'))}")
    if _clean_text(cost_summary.get("return_transport_label")):
        lines.append(f"- Return transport: {_clean_text(cost_summary.get('return_transport_label'))}")
    for daily in _clean_dict_list(cost_summary.get("daily_totals") or []):
        lines.append(f"- {daily.get('day_label')}: {daily.get('total_label')}")
    basis = _clean_text(cost_summary.get("basis_note"))
    if basis:
        lines.append(f"- Basis: {basis}")

    lines.extend(["", "## Carry List"])
    lines.extend(_markdown_bullets(_clean_str_list(itinerary.get("carry_list") or [])))

    notes = _clean_str_list(itinerary.get("trip_notes") or [])
    if notes:
        lines.extend(["", "## Important Notes"])
        lines.extend(_markdown_bullets(notes))

    documents = _clean_str_list(itinerary.get("documents") or [])
    if documents:
        lines.extend(["", "## Documents"])
        lines.extend(_markdown_bullets(documents))

    do_and_dont = itinerary.get("do_and_dont") or {}
    if do_and_dont.get("do") or do_and_dont.get("dont"):
        lines.extend(["", "## Do And Don't"])
        if do_and_dont.get("do"):
            lines.append("Do:")
            lines.extend(_markdown_bullets(_clean_str_list(do_and_dont.get("do") or [])))
        if do_and_dont.get("dont"):
            lines.append("Don't:")
            lines.extend(_markdown_bullets(_clean_str_list(do_and_dont.get("dont") or [])))

    source_notes = _clean_dict_list(itinerary.get("source_notes") or [])
    if source_notes:
        lines.extend(["", "## Source Notes"])
        for ref in source_notes[:8]:
            title = _clean_text(ref.get("title"), _clean_text(ref.get("url"), "Source"))
            url = _clean_text(ref.get("url"))
            ref_type = _clean_text(ref.get("ref_type"))
            if url:
                suffix = f" ({ref_type})" if ref_type else ""
                lines.append(f"- [{title}]({url}){suffix}")

    markdown = "\n".join(lines).strip()
    result = {"final_itinerary_markdown": markdown}
    if len(markdown) > MARKDOWN_STATE_CHAR_BUDGET:
        run_id = _clean_text(state.get("itinerary_run_id"), "default")
        ref = write_itinerary_artifact(run_id, "final_itinerary.md", markdown)
        result["final_itinerary_markdown_ref"] = ref
        result["final_markdown_ref"] = ref
    return result


def show_separate_itinerary_view(state: dict) -> dict:
    """Mark that Streamlit can show the itinerary view."""
    if not _clean_text(state.get("final_itinerary_markdown")):
        raise ValueError("final_itinerary_markdown is required before showing the itinerary view.")
    if not isinstance(state.get("final_itinerary"), dict):
        raise ValueError("final_itinerary is required before showing the itinerary view.")
    return {"itinerary_view_ready": True}


def _run_live_context_llm(projection: dict[str, Any]) -> dict[str, Any]:
    return _run_itinerary_json(
        system_prompt=LIVE_TRIP_CONTEXT_SYSTEM_PROMPT,
        human_prompt=LIVE_TRIP_CONTEXT_HUMAN_PROMPT,
        variables={"itinerary_input": _to_json(projection)},
        use_web_search=True,
        reasoning_effort="medium",
    )


def _run_day_planner_llm(day_input: dict[str, Any]) -> dict[str, Any]:
    return _run_itinerary_json(
        system_prompt=DAY_PLANNING_SYSTEM_PROMPT,
        human_prompt=DAY_PLANNING_HUMAN_PROMPT,
        variables={"day_input": _to_json(day_input)},
        use_web_search=False,
        reasoning_effort="medium",
    )


def _run_itinerary_json(
    *,
    system_prompt: str,
    human_prompt: str,
    variables: dict[str, Any],
    use_web_search: bool,
    reasoning_effort: str,
) -> dict[str, Any]:
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    model = get_itinerary_llm()
    if use_web_search:
        model = model.bind_tools(
            [{"type": "web_search"}],
            tool_choice="web_search",
            reasoning={"effort": reasoning_effort},
        )
    else:
        model = model.bind(reasoning={"effort": reasoning_effort})
    response = (prompt | model).invoke(variables)
    text = _extract_text_content(response.content)
    payload = _load_json_payload(text)
    if not isinstance(payload, dict):
        raise ValueError("Itinerary node must return one JSON object.")
    citations = _compact_citations(_extract_response_citations(response.content) + _clean_dict_list(payload.get("source_refs") or []))
    if citations:
        payload["source_refs"] = citations
    return payload


def _build_live_context_projection(itinerary_input: dict[str, Any]) -> dict[str, Any]:
    destination = itinerary_input.get("destination") or {}
    trip = itinerary_input.get("trip_summary") or {}
    return {
        "destination": destination,
        "trip": trip,
        "traveler_group": itinerary_input.get("traveler_group") or {},
        "budget_mode": trip.get("budget_mode"),
        "logistics_needed": {
            "origin_to_destination": {
                "origin": _clean_text(trip.get("origin")),
                "destination": _clean_text(destination.get("name")),
                "need": "best practical mode, route, time range, and cost range",
            },
            "return_to_origin": {
                "origin": _clean_text(destination.get("name")),
                "destination": _clean_text(trip.get("origin")),
                "need": "best practical return mode, pickup/departure point, time range, and cost range",
            },
            "stay": {
                "budget_mode": _clean_text(trip.get("budget_mode"), "standard"),
                "member_count": _safe_int(trip.get("member_count"), 1),
                "need": "best stay area and nightly room budget range; no hotel availability claims",
            },
            "local_fares": "short ride, day cab, and inter-area transfer fare ranges where useful",
        },
        "must_do_places": _place_names(_clean_dict_list(itinerary_input.get("must_do_places") or []))[:10],
        "optional_places": _place_names(_clean_dict_list(itinerary_input.get("optional_places") or []))[:8],
        "best_food": _clean_str_list(itinerary_input.get("best_food") or [])[:6],
        "area_clusters": _compact_clusters(itinerary_input.get("area_clusters") or []),
        "practical_notes": {
            key: _note_lines(value)[:3]
            for key, value in (itinerary_input.get("practical_notes") or {}).items()
            if key in {"money", "local_transport", "local_practicals", "documents"}
        },
    }


def _normalize_live_context(payload: dict[str, Any], itinerary_input: dict[str, Any]) -> dict[str, Any]:
    fallback_meals = _fallback_meal_context(itinerary_input)
    arrival_context = _normalize_transport_context(
        payload.get("origin_destination_transport_context"),
        _fallback_transport_context(itinerary_input, "arrival"),
    )
    return_context = _normalize_transport_context(
        payload.get("return_transport_context"),
        _fallback_transport_context(itinerary_input, "return"),
    )
    stay_context = _normalize_stay_context(payload.get("stay_cost_context"), _fallback_stay_context(itinerary_input))
    local_fares = _normalize_local_fares(payload.get("local_fare_context"), _fallback_local_fare_context(itinerary_input))
    local_transfer_context = _clean_dict_list(payload.get("local_transfer_cost_context") or [])[:8]
    if not local_transfer_context:
        local_transfer_context = [
            {
                "scope": fare.get("scope"),
                "cost_label": fare.get("cost_label"),
                "when_to_use": fare.get("when_to_use"),
                "source_status": fare.get("source_status", "estimated"),
                "source_ref": fare.get("source_ref"),
            }
            for fare in local_fares
        ][:8]
    context = {
        "origin_destination_transport_context": arrival_context,
        "return_transport_context": return_context,
        "stay_cost_context": stay_context,
        "local_fare_context": local_fares,
        "attraction_cost_context": _clean_dict_list(payload.get("attraction_cost_context") or [])[:12],
        "meal_cost_context": payload.get("meal_cost_context") if isinstance(payload.get("meal_cost_context"), dict) else {},
        "local_transfer_cost_context": local_transfer_context,
        "opening_time_context": _clean_dict_list(payload.get("opening_time_context") or [])[:12],
        "restaurant_context": _clean_dict_list(payload.get("restaurant_context") or [])[:10],
        "fallback_estimate_policy": _clean_text(
            payload.get("fallback_estimate_policy"),
            "Prices are estimated unless a source gives an exact fare or fee.",
        ),
        "source_refs": _collect_live_source_refs(payload, arrival_context, return_context, stay_context, local_fares),
    }
    meal_context = context["meal_cost_context"]
    context["meal_cost_context"] = {
        "breakfast": _cost_value(meal_context.get("breakfast"), fallback_meals["breakfast"]),
        "lunch": _cost_value(meal_context.get("lunch"), fallback_meals["lunch"]),
        "dinner": _cost_value(meal_context.get("dinner"), fallback_meals["dinner"]),
    }
    return context


def _normalize_transport_context(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    cost_label = _clean_text(data.get("cost_label"))
    if "not priced" in cost_label.lower():
        cost_label = ""
    result = {
        "recommended_mode": _clean_text(data.get("recommended_mode"), fallback.get("recommended_mode")),
        "route": _clean_text(data.get("route"), fallback.get("route")),
        "pickup_point": _clean_text(data.get("pickup_point"), fallback.get("pickup_point")),
        "dropoff_point": _clean_text(data.get("dropoff_point"), fallback.get("dropoff_point")),
        "time_label": _clean_text(data.get("time_label"), fallback.get("time_label")),
        "cost_label": cost_label or _clean_text(fallback.get("cost_label")),
        "source_status": _clean_text(data.get("source_status"), fallback.get("source_status") or "estimated"),
        "note": _clean_text(data.get("note"), fallback.get("note")),
        "source_ref": data.get("source_ref") if isinstance(data.get("source_ref"), dict) else fallback.get("source_ref"),
    }
    return _strip_empty(result)


def _normalize_stay_context(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    nightly = _clean_text(data.get("nightly_cost_label") or data.get("cost_label"))
    if "not priced" in nightly.lower():
        nightly = ""
    result = {
        "base_area": _clean_text(data.get("base_area"), fallback.get("base_area")),
        "stay_type": _clean_text(data.get("stay_type"), fallback.get("stay_type")),
        "room_basis": _clean_text(data.get("room_basis"), fallback.get("room_basis")),
        "nightly_cost_label": nightly or _clean_text(fallback.get("nightly_cost_label")),
        "source_status": _clean_text(data.get("source_status"), fallback.get("source_status") or "estimated"),
        "note": _clean_text(data.get("note"), fallback.get("note")),
        "source_ref": data.get("source_ref") if isinstance(data.get("source_ref"), dict) else fallback.get("source_ref"),
    }
    return _strip_empty(result)


def _normalize_local_fares(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fares = _clean_dict_list(value or [])
    if not fares:
        fares = fallback
    normalized = []
    for fare in fares[:6]:
        cost_label = _clean_text(fare.get("cost_label") or fare.get("label"))
        if not cost_label or "not priced" in cost_label.lower():
            continue
        normalized.append(
            _strip_empty(
                {
                    "scope": _clean_text(fare.get("scope"), "local ride"),
                    "cost_label": cost_label,
                    "when_to_use": _clean_text(fare.get("when_to_use"), "Use when it saves time or avoids long walks."),
                    "source_status": _clean_text(fare.get("source_status"), "estimated"),
                    "source_ref": fare.get("source_ref") if isinstance(fare.get("source_ref"), dict) else None,
                }
            )
        )
    return normalized or fallback


def _fallback_transport_context(itinerary_input: dict[str, Any], direction: str) -> dict[str, Any]:
    trip = itinerary_input.get("trip_summary") or {}
    destination = itinerary_input.get("destination") or {}
    origin = _clean_text(trip.get("origin"), "Origin")
    destination_name = _clean_text(destination.get("name"), "destination")
    if direction == "return":
        route = f"{destination_name} to {origin}"
        pickup = f"{destination_name} hotel/base area"
        dropoff = origin
        note = "Keep a clear checkout and departure buffer."
    else:
        route = f"{origin} to {destination_name}"
        pickup = origin
        dropoff = f"{destination_name} base area"
        note = "Verify final departure timing before booking."
    return {
        "recommended_mode": "best practical mode",
        "route": route,
        "pickup_point": pickup,
        "dropoff_point": dropoff,
        "time_label": "Varies by chosen route",
        "cost_label": _money(3000, 12000) + " per person",
        "source_status": "estimated",
        "note": note,
    }


def _fallback_stay_context(itinerary_input: dict[str, Any]) -> dict[str, Any]:
    trip = itinerary_input.get("trip_summary") or {}
    member_count = max(_safe_int(trip.get("member_count"), 1), 1)
    room_count = max((member_count + 1) // 2, 1)
    low, high = _nightly_room_range(_clean_text(trip.get("budget_mode"), "standard"))
    if room_count > 1:
        low *= room_count
        high *= room_count
    return {
        "base_area": _primary_base_area(itinerary_input),
        "stay_type": "clean hotel or homestay",
        "room_basis": f"{room_count} room{'s' if room_count != 1 else ''}",
        "nightly_cost_label": _money(low, high) + " per night",
        "source_status": "estimated",
        "note": "Area and budget only; live hotel availability is not integrated.",
    }


def _fallback_local_fare_context(itinerary_input: dict[str, Any]) -> list[dict[str, Any]]:
    multiplier = _budget_multiplier(_clean_text((itinerary_input.get("trip_summary") or {}).get("budget_mode"), "standard"))
    return [
        {
            "scope": "short local auto/cab",
            "cost_label": _money(int(150 * multiplier), int(500 * multiplier)),
            "when_to_use": "Short hops around the base area.",
            "source_status": "estimated",
        },
        {
            "scope": "local sightseeing cab",
            "cost_label": _money(int(1500 * multiplier), int(4000 * multiplier)),
            "when_to_use": "Half-day or day use for clustered sightseeing.",
            "source_status": "estimated",
        },
        {
            "scope": "inter-area transfer",
            "cost_label": _money(int(3000 * multiplier), int(8000 * multiplier)),
            "when_to_use": "Longer point-to-point transfers outside the base area.",
            "source_status": "estimated",
        },
    ]


def _collect_live_source_refs(
    payload: dict[str, Any],
    arrival_context: dict[str, Any],
    return_context: dict[str, Any],
    stay_context: dict[str, Any],
    local_fares: list[dict[str, Any]],
) -> list[dict[str, str]]:
    refs = _compact_citations(payload.get("source_refs") or [])
    nested_refs = [
        arrival_context.get("source_ref"),
        return_context.get("source_ref"),
        stay_context.get("source_ref"),
    ]
    nested_refs.extend(fare.get("source_ref") for fare in local_fares)
    refs.extend(_compact_citations([ref for ref in nested_refs if isinstance(ref, dict)]))
    return _compact_citations(refs)[:12]


def _assign_places_to_slots(slots: list[dict[str, Any]], itinerary_input: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    must = _clean_dict_list(itinerary_input.get("must_do_places") or [])
    optional = _clean_dict_list(itinerary_input.get("optional_places") or [])
    group = itinerary_input.get("traveler_group") or {}
    easy = bool(group.get("has_kids") or group.get("has_seniors"))
    assignments = {_clean_text(slot.get("day_id")): [] for slot in slots}

    sightseeing_slots = [slot for slot in slots if _clean_text(slot.get("day_type")) == "sightseeing"] or slots
    capacities = {}
    for slot in slots:
        day_type = _clean_text(slot.get("day_type"))
        if "light" in day_type and len(slots) > 2:
            capacities[_clean_text(slot.get("day_id"))] = 1 if day_type == "arrival_light" and len(sightseeing_slots) == 0 else 0
        else:
            capacities[_clean_text(slot.get("day_id"))] = 2 if easy else 3

    def place_items(items: list[dict[str, Any]], purpose: str) -> None:
        index = 0
        for item in items:
            placed = False
            for _ in range(len(sightseeing_slots)):
                slot = sightseeing_slots[index % len(sightseeing_slots)]
                index += 1
                day_id = _clean_text(slot.get("day_id"))
                if len(assignments[day_id]) < capacities.get(day_id, 0):
                    enriched = dict(item)
                    enriched["purpose"] = purpose
                    assignments[day_id].append(enriched)
                    placed = True
                    break
            if not placed:
                break

    place_items(must, "must_do")
    place_items(optional, "optional")
    return assignments


def _normalize_day_packet(
    payload: dict[str, Any],
    slot: dict[str, Any],
    candidates: list[dict[str, Any]],
    itinerary_input: dict[str, Any],
    live_context: dict[str, Any],
) -> dict[str, Any]:
    fallback = _fallback_day(slot, candidates, itinerary_input, live_context)
    if not isinstance(payload, dict):
        return fallback

    day = dict(fallback)
    day["title"] = _clean_text(payload.get("title"), fallback["title"])[:80]
    day["base_area"] = _clean_text(payload.get("base_area"), fallback["base_area"])
    schedule = _clean_dict_list(payload.get("schedule") or [])
    if schedule:
        day["schedule"] = _normalize_schedule(schedule, fallback["schedule"])
    meals = _clean_dict_list(payload.get("meals") or [])
    if meals:
        day["meals"] = _normalize_meals(meals, day["schedule"], fallback["meals"])
    spend = payload.get("estimated_spend") if isinstance(payload.get("estimated_spend"), dict) else {}
    day["estimated_spend"] = _normalize_spend(spend, fallback["estimated_spend"])
    day["important_note"] = _single_day_note(payload.get("important_note"), fallback.get("important_note"))
    refs = _compact_citations(payload.get("source_refs") or []) + _clean_dict_list(fallback.get("source_refs") or [])
    day["source_refs"] = _compact_citations(refs)[:6]
    day["planned_places"] = _planned_place_names(day)
    return day


def _fallback_day(
    slot: dict[str, Any],
    candidates: list[dict[str, Any]],
    itinerary_input: dict[str, Any],
    live_context: dict[str, Any],
) -> dict[str, Any]:
    day_id = _clean_text(slot.get("day_id"))
    day_type = _clean_text(slot.get("day_type"))
    base_area = _clean_text(slot.get("base_area"), _primary_base_area(itinerary_input))
    schedule: list[dict[str, Any]]
    activities = candidates[:1] if "light" in day_type else candidates[:3]
    arrival = live_context.get("origin_destination_transport_context") if isinstance(live_context.get("origin_destination_transport_context"), dict) else {}
    return_trip = live_context.get("return_transport_context") if isinstance(live_context.get("return_transport_context"), dict) else {}
    origin = _clean_text((itinerary_input.get("trip_summary") or {}).get("origin"), "origin")
    destination = _clean_text((itinerary_input.get("destination") or {}).get("name"), "destination")

    if day_type == "arrival_light" or day_type == "arrival_departure_light":
        schedule = [
            _schedule_item("08:00", "breakfast", f"Breakfast before leaving {origin}", origin, _meal_label(live_context, "breakfast")),
            _schedule_item(
                "09:00",
                "transfer",
                f"Travel from {origin} to {destination} by {_clean_text(arrival.get('recommended_mode'), 'best practical mode')}",
                _clean_text(arrival.get("route"), f"{origin} to {destination}"),
                _clean_text(arrival.get("cost_label")),
            ),
            _schedule_item("12:30", "lunch", "Lunch en route or near arrival point", base_area, _meal_label(live_context, "lunch")),
            _schedule_item("15:00", "transfer", "Arrive, transfer to hotel/base area, and check in", base_area, _short_local_fare_label(live_context)),
            _schedule_item("17:00", "buffer", "Rest or easy orientation near hotel/base area", base_area, ""),
            _schedule_item("19:30", "dinner", "Dinner near hotel/base area", base_area, _meal_label(live_context, "dinner")),
        ]
    elif day_type == "departure_light":
        schedule = [
            _schedule_item("08:30", "breakfast", "Breakfast near hotel/base area", base_area, _meal_label(live_context, "breakfast")),
            _schedule_item("10:00", "buffer", "Checkout from hotel/base area and keep luggage ready", base_area, ""),
            _schedule_item("12:30", "lunch", "Lunch en route", base_area, _meal_label(live_context, "lunch")),
            _schedule_item(
                "13:30",
                "transfer",
                f"Start return journey to {origin} by {_clean_text(return_trip.get('recommended_mode'), 'best practical mode')}",
                _clean_text(return_trip.get("route"), f"{destination} to {origin}"),
                _clean_text(return_trip.get("cost_label")) or _transfer_label(live_context),
            ),
            _schedule_item("19:30", "dinner", "Dinner after return or near stopover", base_area, _meal_label(live_context, "dinner")),
        ]
    else:
        schedule = [
            _schedule_item("08:00", "breakfast", "Breakfast near hotel/base area", base_area, _meal_label(live_context, "breakfast")),
        ]
        visit_times = ["09:30", "14:30", "16:30"]
        for index, place in enumerate(activities):
            if index == 1:
                schedule.append(_schedule_item("12:45", "lunch", "Lunch break", base_area, _meal_label(live_context, "lunch")))
            schedule.append(
                _schedule_item(
                    visit_times[index],
                    "visit" if place.get("purpose") == "must_do" else "activity",
                    _place_name(place) or "Planned stop",
                    _clean_text(place.get("area") or place.get("cluster") or base_area),
                    _activity_cost_label(live_context, place),
                )
            )
        if not any(item.get("type") == "lunch" for item in schedule):
            schedule.append(_schedule_item("12:45", "lunch", "Lunch break", base_area, _meal_label(live_context, "lunch")))
        schedule.extend(
            [
                _schedule_item("17:45", "buffer", "Rest buffer", base_area, ""),
                _schedule_item("19:30", "dinner", "Dinner near hotel/base area", base_area, _meal_label(live_context, "dinner")),
            ]
        )

    meals = _extract_meals(schedule, live_context)
    estimated_spend = _estimated_spend_for_day(slot, schedule, itinerary_input, live_context)
    title = _fallback_day_title(slot, activities, base_area)
    note = _single_day_note("", _best_day_note(day_type, itinerary_input, activities))
    source_refs = _compact_citations(live_context.get("source_refs") or [])[:4]

    return {
        "day_id": day_id,
        "day_index": _safe_int(slot.get("day_index"), 0),
        "date": _clean_text(slot.get("date")),
        "title": title,
        "day_type": day_type,
        "base_area": base_area,
        "schedule": schedule,
        "meals": meals,
        "estimated_spend": estimated_spend,
        "important_note": note,
        "source_refs": source_refs,
        "planned_places": [_place_name(item) for item in activities if _place_name(item)],
    }


def _estimated_spend_for_day(
    slot: dict[str, Any],
    schedule: list[dict[str, Any]],
    itinerary_input: dict[str, Any],
    live_context: dict[str, Any],
) -> dict[str, Any]:
    trip = itinerary_input.get("trip_summary") or {}
    members = max(_safe_int(trip.get("member_count"), 1), 1)
    mode = _clean_text(trip.get("budget_mode"), "standard")
    multiplier = _budget_multiplier(mode)
    major_count = len([item for item in schedule if item.get("type") in {"visit", "activity"}])
    day_type = _clean_text(slot.get("day_type"))

    per_person = {
        "breakfast": (int(120 * multiplier), int(280 * multiplier)),
        "lunch": (int(250 * multiplier), int(600 * multiplier)),
        "dinner": (int(350 * multiplier), int(850 * multiplier)),
    }
    meal_totals = {meal: (low * members, high * members) for meal, (low, high) in per_person.items()}
    local_default = (300, 900) if "light" in day_type else (int(900 * multiplier), int(2500 * multiplier))
    local_travel = _range_from_label(_short_local_fare_label(live_context), local_default)
    entry_activity = (major_count * members * int(100 * multiplier), major_count * members * int(500 * multiplier))
    misc_buffer = (int(250 * multiplier), int(900 * multiplier))
    major_transport = (0, 0)
    major_transport_label = ""
    if "arrival" in day_type:
        major_transport_label = _clean_text((live_context.get("origin_destination_transport_context") or {}).get("cost_label"))
    elif "departure" in day_type:
        major_transport_label = _clean_text((live_context.get("return_transport_context") or {}).get("cost_label"))
    if major_transport_label:
        major_transport = _range_from_label(major_transport_label, (0, 0), member_count=members)

    low_total = (
        sum(value[0] for value in meal_totals.values())
        + local_travel[0]
        + entry_activity[0]
        + misc_buffer[0]
        + major_transport[0]
    )
    high_total = (
        sum(value[1] for value in meal_totals.values())
        + local_travel[1]
        + entry_activity[1]
        + misc_buffer[1]
        + major_transport[1]
    )

    spend = {
        "breakfast": _cost_value(_meal_context(live_context, "breakfast"), _cost_dict(_money(*meal_totals["breakfast"]))),
        "lunch": _cost_value(_meal_context(live_context, "lunch"), _cost_dict(_money(*meal_totals["lunch"]))),
        "dinner": _cost_value(_meal_context(live_context, "dinner"), _cost_dict(_money(*meal_totals["dinner"]))),
        "local_travel": _cost_dict(_money(*local_travel)),
        "entry_activity": _cost_dict(_money(*entry_activity)),
        "misc_buffer": _cost_dict(_money(*misc_buffer)),
        "total": {**_cost_dict(_money(low_total, high_total)), "min": low_total, "max": high_total},
    }
    if major_transport_label:
        spend["major_transport"] = {
            **_cost_dict(major_transport_label),
            "min": major_transport[0],
            "max": major_transport[1],
        }
    return spend


def _validate_compact_itinerary(final_itinerary: dict[str, Any], itinerary_input: dict[str, Any]) -> dict[str, Any]:
    issues = []
    expected_days = _safe_int((itinerary_input.get("trip_summary") or {}).get("trip_days"), 0)
    days = _clean_dict_list(final_itinerary.get("days") or [])
    if expected_days and len(days) != expected_days:
        issues.append(f"day count {len(days)} does not match trip_days {expected_days}.")
    if not isinstance(final_itinerary.get("travel_logistics"), dict) or not (final_itinerary.get("travel_logistics") or {}).get("arrival"):
        issues.append("arrival travel logistics are missing.")
    if not isinstance(final_itinerary.get("stay_plan"), dict) or not (final_itinerary.get("stay_plan") or {}).get("nightly_cost_label"):
        issues.append("stay plan cost range is missing.")
    if not isinstance(final_itinerary.get("local_transport"), dict) or not _clean_dict_list((final_itinerary.get("local_transport") or {}).get("fare_ranges") or []):
        issues.append("local transport fare context is missing.")
    for day in days:
        if not _clean_dict_list(day.get("schedule") or []):
            issues.append(f"{day.get('day_id')} has no schedule.")
        if not _clean_dict_list(day.get("meals") or []):
            issues.append(f"{day.get('day_id')} has no meals.")
        total = ((day.get("estimated_spend") or {}).get("total") or {}).get("label")
        if not _clean_text(total) or "not priced" in _clean_text(total).lower():
            issues.append(f"{day.get('day_id')} has missing spend.")
        text = json.dumps(day, default=str).lower()
        if "another hotel" in text or "rooftop" in text:
            issues.append(f"{day.get('day_id')} contains vague hotel wording.")
    return {
        "valid": not issues,
        "issues": issues,
        "repair_targets": [],
        "repair_attempts": {},
    }


def _render_compact_day(day: dict[str, Any]) -> list[str]:
    day_number = _safe_int(day.get("day_index"), 0) + 1
    lines = [
        "",
        f"### Day {day_number} - {_clean_text(day.get('title'), 'Day Plan')}",
        f"- Date: {_clean_text(day.get('date'))}",
        f"- Type: {_clean_text(day.get('day_type')).replace('_', ' ')}",
        f"- Base: {_clean_text(day.get('base_area'))}",
    ]
    for item in _clean_dict_list(day.get("schedule") or []):
        cost = _clean_text(item.get("cost"))
        suffix = f" ({cost})" if cost else ""
        lines.append(f"- {item.get('time')} {item.get('label')}{suffix}")
    total = ((day.get("estimated_spend") or {}).get("total") or {}).get("label")
    status = ((day.get("estimated_spend") or {}).get("total") or {}).get("source_status")
    status_label = f" ({status})" if status else ""
    lines.append(f"- Spend: {_clean_text(total)}{status_label}")
    note = _clean_text(day.get("important_note"))
    if note:
        lines.append(f"- Note: {note}")
    return lines


def _render_how_to_reach(travel_logistics: dict[str, Any]) -> list[str]:
    arrival = travel_logistics.get("arrival") if isinstance(travel_logistics.get("arrival"), dict) else {}
    if not arrival:
        return []
    lines = ["", "## How To Reach"]
    route = _clean_text(arrival.get("route"))
    mode = _clean_text(arrival.get("recommended_mode"))
    if route or mode:
        lines.append(f"- Recommended: {route or 'Origin to destination'} by {mode or 'best practical mode'}")
    if _clean_text(arrival.get("time_label")):
        lines.append(f"- Time: {_clean_text(arrival.get('time_label'))}")
    if _clean_text(arrival.get("cost_label")):
        lines.append(f"- Estimate: {_clean_text(arrival.get('cost_label'))} ({_clean_text(arrival.get('source_status'), 'estimated')})")
    if _clean_text(arrival.get("note")):
        lines.append(f"- Note: {_clean_text(arrival.get('note'))}")
    return lines


def _render_return_plan(travel_logistics: dict[str, Any]) -> list[str]:
    return_trip = travel_logistics.get("return") if isinstance(travel_logistics.get("return"), dict) else {}
    if not return_trip:
        return []
    lines = ["", "## Return Plan"]
    route = _clean_text(return_trip.get("route"))
    mode = _clean_text(return_trip.get("recommended_mode"))
    if route or mode:
        lines.append(f"- Recommended: {route or 'Destination to origin'} by {mode or 'best practical mode'}")
    if _clean_text(return_trip.get("pickup_point")):
        lines.append(f"- Start from: {_clean_text(return_trip.get('pickup_point'))}")
    if _clean_text(return_trip.get("time_label")):
        lines.append(f"- Time: {_clean_text(return_trip.get('time_label'))}")
    if _clean_text(return_trip.get("cost_label")):
        lines.append(f"- Estimate: {_clean_text(return_trip.get('cost_label'))} ({_clean_text(return_trip.get('source_status'), 'estimated')})")
    if _clean_text(return_trip.get("note")):
        lines.append(f"- Note: {_clean_text(return_trip.get('note'))}")
    return lines


def _render_stay_plan(stay_plan: dict[str, Any]) -> list[str]:
    if not stay_plan:
        return []
    lines = ["", "## Stay Plan"]
    lines.append(f"- Base: {_clean_text(stay_plan.get('base_area'), 'Best practical base area')}")
    lines.append(f"- Stay type: {_clean_text(stay_plan.get('stay_type'), 'hotel/base area stay')}")
    lines.append(f"- Room basis: {_clean_text(stay_plan.get('room_basis'), 'room basis to be confirmed')}")
    lines.append(f"- Nights: {_safe_int(stay_plan.get('nights'), 0)}")
    lines.append(f"- Room estimate: {_clean_text(stay_plan.get('nightly_cost_label'), 'Estimate unavailable')} ({_clean_text(stay_plan.get('source_status'), 'estimated')})")
    lines.append(f"- Stay estimate: {_clean_text(stay_plan.get('total_stay_label'), 'Estimate unavailable')} total")
    note = _clean_text(stay_plan.get("note"))
    if note:
        lines.append(f"- Note: {note}")
    return lines


def _render_local_transport(local_transport: dict[str, Any]) -> list[str]:
    fares = _clean_dict_list(local_transport.get("fare_ranges") or [])
    if not fares:
        return []
    lines = ["", "## Local Transport"]
    summary = _clean_text(local_transport.get("summary"))
    if summary:
        lines.append(f"- Plan: {summary}")
    for fare in fares[:4]:
        scope = _clean_text(fare.get("scope"), "local fare")
        cost = _clean_text(fare.get("cost_label"), "Estimate varies")
        when = _clean_text(fare.get("when_to_use"))
        suffix = f" - {when}" if when else ""
        lines.append(f"- {scope}: {cost}{suffix}")
    return lines


def _normalize_schedule(schedule: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for item in schedule[:8]:
        time = _clean_text(item.get("time"))
        label = _clean_text(item.get("label"))
        if not time or not label:
            continue
        item_type = _clean_text(item.get("type"), "activity")
        if item_type not in {"breakfast", "visit", "lunch", "transfer", "activity", "dinner", "buffer"}:
            item_type = "activity"
        cleaned.append(
            {
                "time": time[:5],
                "type": item_type,
                "label": _sanitize_itinerary_text(label)[:100],
                "area": _clean_text(item.get("area") or item.get("location"))[:80],
                "cost": _clean_text(item.get("cost"))[:60],
            }
        )
    meal_types = {item.get("type") for item in cleaned}
    if not {"breakfast", "lunch", "dinner"}.issubset(meal_types):
        return fallback
    return cleaned


def _normalize_meals(
    meals: list[dict[str, Any]],
    schedule: list[dict[str, Any]],
    fallback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cleaned = []
    for meal in meals[:3]:
        meal_name = _clean_text(meal.get("meal")).lower()
        if meal_name not in {"breakfast", "lunch", "dinner"}:
            continue
        cleaned.append(
            {
                "meal": meal_name,
                "time": _clean_text(meal.get("time"))[:5],
                "label": _sanitize_itinerary_text(_clean_text(meal.get("label"), meal_name.title()))[:80],
                "cost": _clean_text(meal.get("cost"))[:60],
            }
        )
    if {meal.get("meal") for meal in cleaned} == {"breakfast", "lunch", "dinner"}:
        return cleaned
    return _extract_meals(schedule, {}) or fallback


def _normalize_spend(spend: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(fallback)
    for key in ["breakfast", "lunch", "dinner", "local_travel", "entry_activity", "misc_buffer", "major_transport", "total"]:
        value = _cost_value(spend.get(key), fallback.get(key) or {})
        if value.get("label") and "not priced" not in value["label"].lower():
            if key in {"total", "major_transport"}:
                value["min"] = (fallback.get(key) or {}).get("min")
                value["max"] = (fallback.get(key) or {}).get("max")
            normalized[key] = value
    return normalized


def _trip_level_notes(itinerary_input: dict[str, Any], live_context: dict[str, Any]) -> list[str]:
    notes = []
    practical = itinerary_input.get("practical_notes") or {}
    for key in ["weather", "money", "local_transport", "connectivity", "safety"]:
        note_lines = _note_lines(practical.get(key) or {})
        if key == "money" and len(note_lines) > 1:
            notes.append(note_lines[1])
        else:
            notes.extend(note_lines[:1])
    notes.extend(_clean_str_list(itinerary_input.get("warnings") or [])[:2])
    policy = _clean_text(live_context.get("fallback_estimate_policy"))
    if policy:
        notes.append(policy)
    return _dedupe(notes)[:7]


def _carry_list(practical_notes: dict[str, Any]) -> list[str]:
    carry = ["Government ID", "Booking confirmations", "Phone charger", "Power bank"]
    carry.extend(_note_field_lines(practical_notes.get("packing") or {}, ["guidance", "facts"])[:5])
    return _dedupe(carry)[:8]


def _documents(practical_notes: dict[str, Any]) -> list[str]:
    return _dedupe(_note_field_lines(practical_notes.get("documents") or {}, ["facts", "guidance"]))[:5]


def _do_and_dont(practical_notes: dict[str, Any]) -> dict[str, list[str]]:
    do_items = []
    dont_items = []
    for key in ["local_practicals", "cultural"]:
        do_items.extend(_note_field_lines(practical_notes.get(key) or {}, ["guidance"])[:2])
    for key in ["safety", "cultural", "adventure"]:
        dont_items.extend(_note_field_lines(practical_notes.get(key) or {}, ["warnings"])[:2])
    return {"do": _dedupe(do_items)[:5], "dont": _dedupe(dont_items)[:5]}


def _travel_logistics(live_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "arrival": _strip_empty(live_context.get("origin_destination_transport_context") or {}),
        "return": _strip_empty(live_context.get("return_transport_context") or {}),
    }


def _stay_plan(itinerary_input: dict[str, Any], live_context: dict[str, Any]) -> dict[str, Any]:
    trip = itinerary_input.get("trip_summary") or {}
    stay_context = live_context.get("stay_cost_context") if isinstance(live_context.get("stay_cost_context"), dict) else {}
    fallback = _fallback_stay_context(itinerary_input)
    nights = max(_safe_int(trip.get("trip_days"), 1) - 1, 0)
    nightly_label = _clean_text(stay_context.get("nightly_cost_label"), fallback.get("nightly_cost_label"))
    nightly_low, nightly_high = _range_from_label(nightly_label, _range_from_label(fallback.get("nightly_cost_label"), (0, 0)))
    total_label = _money(nightly_low * nights, nightly_high * nights) if nights else _money(0, 0)
    return _strip_empty(
        {
            "base_area": _clean_text(stay_context.get("base_area"), fallback.get("base_area")),
            "stay_type": _clean_text(stay_context.get("stay_type"), fallback.get("stay_type")),
            "room_basis": _clean_text(stay_context.get("room_basis"), fallback.get("room_basis")),
            "nightly_cost_label": nightly_label,
            "nights": nights,
            "total_stay_label": total_label,
            "total_stay_min": nightly_low * nights,
            "total_stay_max": nightly_high * nights,
            "source_status": _clean_text(stay_context.get("source_status"), fallback.get("source_status") or "estimated"),
            "check_in_out": "Standard hotel check-in/check-out timing; verify with the property before booking.",
            "note": _clean_text(stay_context.get("note"), fallback.get("note")),
            "source_ref": stay_context.get("source_ref") if isinstance(stay_context.get("source_ref"), dict) else fallback.get("source_ref"),
        }
    )


def _local_transport_plan(live_context: dict[str, Any]) -> dict[str, Any]:
    fares = _clean_dict_list(live_context.get("local_fare_context") or live_context.get("local_transfer_cost_context") or [])
    return {
        "summary": "Use autos/cabs for short hops and a day cab for spread-out sightseeing or inter-area routes.",
        "fare_ranges": fares[:5],
    }


def _cost_summary(
    days: list[dict[str, Any]],
    stay_plan: dict[str, Any],
    travel_logistics: dict[str, Any],
    local_transport: dict[str, Any],
) -> dict[str, Any]:
    low = 0
    high = 0
    daily = []
    major_low = 0
    major_high = 0
    for day in days:
        total = (day.get("estimated_spend") or {}).get("total") or {}
        low += _safe_int(total.get("min"), 0)
        high += _safe_int(total.get("max"), 0)
        major = (day.get("estimated_spend") or {}).get("major_transport") or {}
        major_low += _safe_int(major.get("min"), 0)
        major_high += _safe_int(major.get("max"), 0)
        daily.append(
            {
                "day_id": day.get("day_id"),
                "day_label": f"Day {_safe_int(day.get('day_index'), 0) + 1}",
                "total_label": _clean_text(total.get("label"), _money(0, 0)),
                "source_status": _clean_text(total.get("source_status"), "estimated"),
            }
        )
    stay_low = _safe_int(stay_plan.get("total_stay_min"), 0)
    stay_high = _safe_int(stay_plan.get("total_stay_max"), 0)
    total_low = low + stay_low
    total_high = high + stay_high
    arrival = (travel_logistics.get("arrival") or {}) if isinstance(travel_logistics.get("arrival"), dict) else {}
    return_trip = (travel_logistics.get("return") or {}) if isinstance(travel_logistics.get("return"), dict) else {}
    return {
        "trip_total_label": _money(total_low, total_high),
        "daily_totals": daily,
        "daily_spend_label": _money(low, high),
        "stay_total_label": _clean_text(stay_plan.get("total_stay_label"), _money(stay_low, stay_high)),
        "major_transport_label": _money(major_low, major_high) if major_high else "Included where shown in arrival/return day spend",
        "arrival_transport_label": _clean_text(arrival.get("cost_label")),
        "return_transport_label": _clean_text(return_trip.get("cost_label")),
        "local_transport_ranges": _clean_dict_list(local_transport.get("fare_ranges") or [])[:3],
        "basis_note": "Estimates include daily meals/activities/local movement, stay budget, and arrival/return transport where available.",
    }


def _source_notes(itinerary_input: dict[str, Any], live_context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _compact_citations(itinerary_input.get("source_refs") or [])
    refs.extend(_compact_citations(live_context.get("source_refs") or []))
    nested_refs = []
    for key in ["origin_destination_transport_context", "return_transport_context", "stay_cost_context"]:
        value = live_context.get(key)
        if isinstance(value, dict) and isinstance(value.get("source_ref"), dict):
            nested_refs.append(value.get("source_ref"))
    for fare in _clean_dict_list(live_context.get("local_fare_context") or []):
        if isinstance(fare.get("source_ref"), dict):
            nested_refs.append(fare.get("source_ref"))
    refs.extend(_compact_citations(nested_refs))
    return _compact_citations(refs)[:10]


def _fallback_meal_context(itinerary_input: dict[str, Any]) -> dict[str, dict[str, Any]]:
    trip = itinerary_input.get("trip_summary") or {}
    members = max(_safe_int(trip.get("member_count"), 1), 1)
    multiplier = _budget_multiplier(_clean_text(trip.get("budget_mode"), "standard"))
    return {
        "breakfast": _cost_dict(_money(int(120 * multiplier * members), int(280 * multiplier * members))),
        "lunch": _cost_dict(_money(int(250 * multiplier * members), int(600 * multiplier * members))),
        "dinner": _cost_dict(_money(int(350 * multiplier * members), int(850 * multiplier * members))),
    }


def _meal_context(live_context: dict[str, Any], meal: str) -> dict[str, Any]:
    meal_context = live_context.get("meal_cost_context") if isinstance(live_context.get("meal_cost_context"), dict) else {}
    return meal_context.get(meal) if isinstance(meal_context.get(meal), dict) else {}


def _cost_value(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        label = _clean_text(value.get("label") or value.get("cost_label"))
        if label and "not priced" not in label.lower():
            return {
                "label": label,
                "source_status": _clean_text(value.get("source_status"), "estimated"),
                "source_ref": value.get("source_ref") if isinstance(value.get("source_ref"), dict) else None,
            }
    return dict(fallback)


def _cost_dict(label: str) -> dict[str, Any]:
    return {"label": label, "source_status": "estimated", "source_ref": None}


def _meal_label(live_context: dict[str, Any], meal: str) -> str:
    return _clean_text(_meal_context(live_context, meal).get("label"), "")


def _transfer_label(live_context: dict[str, Any]) -> str:
    items = _clean_dict_list(live_context.get("local_transfer_cost_context") or [])
    if items:
        return _clean_text(items[0].get("cost_label") or items[0].get("label"))
    return ""


def _short_local_fare_label(live_context: dict[str, Any]) -> str:
    fares = _clean_dict_list(live_context.get("local_fare_context") or live_context.get("local_transfer_cost_context") or [])
    for fare in fares:
        scope = _clean_text(fare.get("scope")).lower()
        if "short" in scope or "auto" in scope or "cab" in scope:
            return _clean_text(fare.get("cost_label") or fare.get("label"))
    if fares:
        return _clean_text(fares[0].get("cost_label") or fares[0].get("label"))
    return ""


def _activity_cost_label(live_context: dict[str, Any], place: dict[str, Any]) -> str:
    name = _normalize_name(_place_name(place))
    for item in _clean_dict_list(live_context.get("attraction_cost_context") or []):
        if name and name in _normalize_name(item.get("name")):
            return _clean_text(item.get("cost_label") or item.get("label"))
    return ""


def _compact_live_context_for_day(live_context: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    names = {_normalize_name(_place_name(item)) for item in candidates}
    return {
        "meal_cost_context": live_context.get("meal_cost_context") or {},
        "local_transfer_cost_context": _clean_dict_list(live_context.get("local_transfer_cost_context") or [])[:3],
        "attraction_cost_context": [
            item
            for item in _clean_dict_list(live_context.get("attraction_cost_context") or [])
            if not names or _normalize_name(item.get("name")) in names
        ][:5],
        "opening_time_context": [
            item
            for item in _clean_dict_list(live_context.get("opening_time_context") or [])
            if not names or _normalize_name(item.get("name")) in names
        ][:5],
        "restaurant_context": _clean_dict_list(live_context.get("restaurant_context") or [])[:4],
        "source_refs": _compact_citations(live_context.get("source_refs") or [])[:5],
    }


def _compact_logistics_for_day(
    live_context: dict[str, Any],
    slot: dict[str, Any],
    itinerary_input: dict[str, Any],
) -> dict[str, Any]:
    day_type = _clean_text(slot.get("day_type"))
    logistics = {
        "stay_base_area": _best_stay_area(itinerary_input, live_context),
        "stay_cost_context": live_context.get("stay_cost_context") or {},
        "local_fare_context": _clean_dict_list(live_context.get("local_fare_context") or [])[:3],
    }
    if "arrival" in day_type:
        logistics["arrival_transport"] = live_context.get("origin_destination_transport_context") or {}
    if "departure" in day_type:
        logistics["return_transport"] = live_context.get("return_transport_context") or {}
    return _strip_empty(logistics)


def _extract_meals(schedule: list[dict[str, Any]], live_context: dict[str, Any]) -> list[dict[str, Any]]:
    meals = []
    for item in schedule:
        item_type = _clean_text(item.get("type")).lower()
        if item_type in {"breakfast", "lunch", "dinner"}:
            meals.append(
                {
                    "meal": item_type,
                    "time": _clean_text(item.get("time")),
                    "label": _clean_text(item.get("label"), item_type.title()),
                    "cost": _clean_text(item.get("cost")) or _meal_label(live_context, item_type),
                }
            )
    return meals


def _single_day_note(primary: Any, fallback: Any = "") -> str:
    for value in [primary, fallback]:
        text = _sanitize_itinerary_text(_clean_text(value))
        if text:
            return text[:120]
    return ""


def _best_day_note(day_type: str, itinerary_input: dict[str, Any], activities: list[dict[str, Any]]) -> str:
    if "arrival" in day_type:
        return "Keep arrival day light and avoid extra detours."
    if "departure" in day_type:
        return "Keep a clear departure buffer."
    if len(activities) > 2:
        return "Keep the rest buffer protected."
    return ""


def _fallback_day_title(slot: dict[str, Any], activities: list[dict[str, Any]], base_area: str) -> str:
    names = [_place_name(item) for item in activities if _place_name(item)]
    day_type = _clean_text(slot.get("day_type")).replace("_", " ").title()
    if names:
        return " & ".join(names[:2])
    if "arrival" in _clean_text(slot.get("day_type")):
        return f"Arrival In {base_area}"
    if "departure" in _clean_text(slot.get("day_type")):
        return f"Departure From {base_area}"
    return day_type


def _schedule_item(time: str, item_type: str, label: str, area: str, cost: str) -> dict[str, str]:
    item = {"time": time, "type": item_type, "label": label, "area": area}
    if cost:
        item["cost"] = cost
    return item


def _planned_place_names(day: dict[str, Any]) -> list[str]:
    return [
        _clean_text(item.get("label"))
        for item in _clean_dict_list(day.get("schedule") or [])
        if item.get("type") in {"visit", "activity"} and _clean_text(item.get("label"))
    ]


def _place_names(values: list[dict[str, Any]]) -> list[str]:
    return [_place_name(item) for item in values if _place_name(item)]


def _compact_clusters(values: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": _clean_text(item.get("name") or item.get("area")),
            "places": _clean_str_list(item.get("places") or [])[:5],
        }
        for item in _clean_dict_list(values or [])[:6]
    ]


def _primary_base_area(itinerary_input: dict[str, Any]) -> str:
    clusters = _clean_dict_list(itinerary_input.get("area_clusters") or [])
    if clusters:
        return _clean_text(clusters[0].get("name") or clusters[0].get("area"), "Selected base")
    selected_places = _clean_str_list((itinerary_input.get("destination") or {}).get("selected_places") or [])
    if selected_places:
        return selected_places[0]
    return _clean_text((itinerary_input.get("destination") or {}).get("name"), "Selected base")


def _best_stay_area(itinerary_input: dict[str, Any], live_context: dict[str, Any]) -> str:
    stay_context = live_context.get("stay_cost_context") if isinstance(live_context.get("stay_cost_context"), dict) else {}
    return _clean_text(stay_context.get("base_area"), _primary_base_area(itinerary_input))


def _title_placeholder(day_type: str, base_area: str) -> str:
    if "arrival" in day_type:
        return f"Arrival in {base_area}"
    if "departure" in day_type:
        return f"Departure from {base_area}"
    return f"Explore {base_area}"


def _traveler_label(itinerary_input: dict[str, Any]) -> str:
    group = itinerary_input.get("traveler_group") or {}
    count = max(_safe_int(group.get("member_count"), 1), 1)
    tags = []
    if group.get("has_kids"):
        tags.append("kids")
    if group.get("has_seniors"):
        tags.append("seniors")
    suffix = f" ({', '.join(tags)})" if tags else ""
    return f"{count} traveler{'s' if count != 1 else ''}{suffix}"


def _budget_multiplier(mode: str) -> float:
    mode = _clean_text(mode).lower()
    if mode == "luxury":
        return 2.4
    if mode == "premium":
        return 1.6
    if mode == "custom":
        return 1.2
    return 1.0


def _nightly_room_range(mode: str) -> tuple[int, int]:
    mode = _clean_text(mode).lower()
    if mode == "luxury":
        return (10000, 25000)
    if mode == "premium":
        return (5000, 10000)
    if mode == "custom":
        return (4000, 8000)
    return (2500, 5000)


def _money(low: int, high: int) -> str:
    low = max(int(low), 0)
    high = max(int(high), low)
    return f"{CURRENCY}{low:,}-{CURRENCY}{high:,}"


def _range_from_label(label: Any, fallback: tuple[int, int], member_count: int = 1) -> tuple[int, int]:
    text = _clean_text(label)
    if not text or "not priced" in text.lower():
        return fallback
    numbers = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", text)]
    if not numbers:
        return fallback
    if len(numbers) == 1:
        low = high = numbers[0]
    else:
        low, high = min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
    if "per person" in text.lower() or "/person" in text.lower() or "pp" in text.lower():
        low *= max(member_count, 1)
        high *= max(member_count, 1)
    return (low, high)


def _format_destination(selected_destination: dict[str, Any]) -> str:
    region = _clean_text(selected_destination.get("state_or_region"), "Selected destination")
    places = _clean_str_list(selected_destination.get("places_covered") or [])
    return f"{region} ({', '.join(places)})" if places else region


def _note_lines(note: dict[str, Any]) -> list[str]:
    if not isinstance(note, dict):
        return []
    return _dedupe(
        [_clean_text(note.get("summary"))]
        + _note_field_lines(note, ["facts", "guidance", "warnings"])
    )


def _note_field_lines(note: dict[str, Any], fields: list[str]) -> list[str]:
    values = []
    if not isinstance(note, dict):
        return values
    for field in fields:
        values.extend(_clean_str_list(note.get(field) or []))
    return _dedupe(values)


def _clean_practical_notes(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for key, item in value.items():
        if isinstance(item, dict):
            cleaned[_clean_text(key)] = _strip_empty(
                {
                    "summary": _clean_text(item.get("summary")),
                    "facts": _clean_str_list(item.get("facts") or [])[:4],
                    "guidance": _clean_str_list(item.get("guidance") or [])[:4],
                    "warnings": _clean_str_list(item.get("warnings") or [])[:3],
                    "citations": _compact_citations(item.get("citations") or [])[:4],
                }
            )
    return cleaned


def _compact_citations(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    refs = []
    seen_urls = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        url = _clean_text(value.get("url"))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        refs.append(
            {
                "title": _clean_text(value.get("title"), url),
                "url": url,
                "ref_type": _clean_text(value.get("ref_type"), "research"),
            }
        )
    return refs


def _place_name(item: dict[str, Any]) -> str:
    return _clean_text(item.get("name") or item.get("title") or item.get("place_name") or item.get("activity"))


def _normalize_name(value: Any) -> str:
    return _clean_text(value).casefold()


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today()


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _sanitize_itinerary_text(value: Any) -> str:
    text = _clean_text(value)
    replacements = {
        "another hotel": "hotel/base area",
        "another Hotel": "hotel/base area",
        "rooftop": "hotel/base area restaurant",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _clean_str_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        text = _clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _clean_dict_list(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        if not isinstance(value, dict):
            continue
        item = _strip_empty(value)
        if item:
            cleaned.append(item)
    return cleaned


def _strip_empty(value: Any, keep_empty_keys: set[str] | None = None) -> Any:
    keep_empty_keys = keep_empty_keys or set()
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            stripped = _strip_empty(item, keep_empty_keys)
            if key in keep_empty_keys or stripped not in (None, "", [], {}):
                cleaned[key] = stripped
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            stripped = _strip_empty(item, keep_empty_keys)
            if stripped not in (None, "", [], {}):
                cleaned_list.append(stripped)
        return cleaned_list
    return value


def _dedupe(values: list[str]) -> list[str]:
    cleaned = []
    for value in values:
        text = _clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _markdown_bullets(values: list[str], fallback: str | None = None) -> list[str]:
    cleaned = _clean_str_list(values)
    if not cleaned and fallback:
        return [f"- {fallback}"]
    return [f"- {value}" for value in cleaned]


def _to_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def assert_projection_budget(projection: dict[str, Any], label: str, limit: int = PROJECTION_CHAR_BUDGET) -> int:
    size = len(json.dumps(projection, sort_keys=True, default=str))
    if size > limit:
        raise ValueError(f"{label} projection is too large: {size} chars > {limit}.")
    return size


def _require_dict(state: dict, key: str) -> dict[str, Any]:
    value = state.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} is required before itinerary planning can continue.")
    return value


# Compatibility wrappers for imports from the previous itinerary architecture.
def compact_research_for_itinerary(state: dict) -> dict:
    itinerary_input = _require_dict(state, "itinerary_input")
    return {
        "source_registry": {
            f"R{index + 1}": ref
            for index, ref in enumerate(_compact_citations(itinerary_input.get("source_refs") or []))
        }
    }


def decide_stay_base_plan(state: dict) -> dict:
    itinerary_input = _require_dict(state, "itinerary_input")
    return {"stay_base_plan": {"primary_base_area": _primary_base_area(itinerary_input)}}


def decide_transport_plan(state: dict) -> dict:
    return {
        "transport_plan": {"local_movement_strategy": {"summary": "Use local transport suited to the day plan."}},
        "booking_cost_notes": {"exact_booking_costs_available": False, "booking_refs": [], "cost_refs": []},
    }


def create_day_planning_tasks(state: dict) -> dict:
    skeleton = _require_dict(state, "trip_skeleton")
    return {"day_planning_tasks": _clean_dict_list(skeleton.get("day_slots") or [])}


def plan_itinerary_day(state: dict) -> dict:
    task = state.get("day_planning_task") if isinstance(state.get("day_planning_task"), dict) else {}
    slot = task or {"day_id": "D0", "day_index": 0, "date": "", "day_type": "sightseeing", "base_area": "Selected base"}
    itinerary_input = state.get("itinerary_input") if isinstance(state.get("itinerary_input"), dict) else {"trip_summary": {"member_count": 1, "budget_mode": "standard"}}
    day = _fallback_day(slot, [], itinerary_input, {})
    return {"day_itinerary_packets": [day]}


def aggregate_day_itineraries(state: dict) -> dict:
    return {
        "day_itinerary_packets": sorted(
            _clean_dict_list(state.get("day_itinerary_packets") or []),
            key=lambda item: _safe_int(item.get("day_index"), 0),
        )
    }


def create_final_section_tasks(state: dict) -> dict:
    return {"itinerary_section_tasks": []}


def build_final_itinerary_section(state: dict) -> dict:
    return {"itinerary_sections": []}


def aggregate_final_sections(state: dict) -> dict:
    return {"itinerary_sections": _clean_dict_list(state.get("itinerary_sections") or [])}


def validate_itinerary(state: dict) -> dict:
    itinerary = state.get("final_itinerary") if isinstance(state.get("final_itinerary"), dict) else {}
    itinerary_input = state.get("itinerary_input") if isinstance(state.get("itinerary_input"), dict) else {}
    return {"itinerary_validation": _validate_compact_itinerary(itinerary, itinerary_input)}


def repair_selected_day_or_central_node(state: dict) -> dict:
    return {"itinerary_repair_plan": {"target_type": "exhausted", "day_ids": [], "attempt": 0}}


def render_itinerary_markdown(state: dict) -> dict:
    return render_clean_itinerary_markdown(state)


def build_day_worker_input(day_task: dict[str, Any]) -> dict[str, Any]:
    return dict(day_task)


def build_final_aggregation_input(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "trip_summary": (state.get("itinerary_input") or {}).get("trip_summary") or {},
        "day_count": len(_clean_dict_list(state.get("day_itinerary_packets") or [])),
    }


def build_validation_input(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "trip_days": ((state.get("itinerary_input") or {}).get("trip_summary") or {}).get("trip_days"),
        "day_count": len(_clean_dict_list(state.get("day_itinerary_packets") or [])),
    }
