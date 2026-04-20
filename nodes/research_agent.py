import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.research_agent_prompts import (
    DESTINATION_RESEARCH_HUMAN_PROMPT,
    DESTINATION_RESEARCH_SYSTEM_PROMPT,
    PRACTICAL_TRAVEL_INFO_HUMAN_PROMPT,
    PRACTICAL_TRAVEL_INFO_SYSTEM_PROMPT,
)
from llm import get_research_llm
from nodes.call_destination_research import _extract_text_content, _load_json_payload
from nodes.research_cache import get_cached_payload, make_cache_key, set_cached_payload


RESEARCH_PACKET_CHAR_BUDGET = 16000
RESEARCH_REASONING = {"effort": "medium"}
RESEARCH_TOOLS = [{"type": "web_search"}]


def normalize_research_input(state: dict) -> dict:
    """Compact the finalized information-curator handoff for destination research."""
    selected_destination = state.get("selected_destination")
    if not isinstance(selected_destination, dict):
        raise ValueError("Selected destination is required before research.")

    followup_answers = _clean_followup_answers(state.get("followup_answers") or [])
    custom_note = _clean_text(state.get("followup_custom_note"))
    change_request = _clean_text(state.get("followup_change_request"))
    curator_summary = _build_curator_summary(
        selected_destination,
        followup_answers,
        custom_note,
        change_request,
    )

    research_input = {
        "destination": _format_destination(selected_destination),
        "selected_destination": _compact_destination(selected_destination),
        "trip": {
            "origin": _clean_text(state.get("origin")),
            "start_date": _clean_text(state.get("start_date")),
            "end_date": _clean_text(state.get("end_date")),
            "trip_days": _safe_int(state.get("trip_days"), 1),
            "trip_type": _clean_text(state.get("trip_type")),
            "budget_mode": _clean_text(state.get("budget_mode")),
            "budget_value": state.get("budget_value"),
        },
        "group_signals": {
            "member_count": _safe_int(state.get("member_count"), 1),
            "has_kids": bool(state.get("has_kids")),
            "has_seniors": bool(state.get("has_seniors")),
        },
        "interests": _infer_interests(selected_destination, followup_answers, custom_note, change_request),
        "pace": _infer_pace(followup_answers, custom_note, change_request),
        "preferences": {
            "followup_answers": followup_answers[:6],
            "custom_note": custom_note[:500],
            "change_request": change_request[:500],
        },
        "constraints": _infer_known_constraints(state, selected_destination, custom_note, change_request),
        "curator_summary": curator_summary[:1800],
        # Backward-compatible key retained for downstream consumers.
        "final_brief": curator_summary[:1800],
    }

    return {"research_input": _strip_empty(research_input)}


def build_destination_research(state: dict) -> dict:
    """Run one coherent destination intelligence pass."""
    research_input = _require_dict(state, "research_input")
    payload = _run_research_json(
        node_type="destination_research",
        system_prompt=DESTINATION_RESEARCH_SYSTEM_PROMPT,
        human_prompt=DESTINATION_RESEARCH_HUMAN_PROMPT,
        variables={"research_input": _to_json(research_input)},
        cache_payload={"research_input": research_input},
    )
    return {"destination_research": _normalize_destination_research(payload)}


def enrich_with_practical_travel_info(state: dict) -> dict:
    """Add compact practical travel intelligence in one pass."""
    research_input = _require_dict(state, "research_input")
    destination_research = _require_dict(state, "destination_research")
    payload = _run_research_json(
        node_type="practical_travel_info",
        system_prompt=PRACTICAL_TRAVEL_INFO_SYSTEM_PROMPT,
        human_prompt=PRACTICAL_TRAVEL_INFO_HUMAN_PROMPT,
        variables={
            "research_input": _to_json(_practical_input_projection(research_input)),
            "destination_research": _to_json(_destination_projection(destination_research)),
        },
        cache_payload={
            "research_input": _practical_input_projection(research_input),
            "destination_research": _destination_projection(destination_research),
        },
    )
    return {"practical_travel_info": _normalize_practical_travel_info(payload)}


def aggregate_research_packet(state: dict) -> dict:
    """Combine destination and practical research into one compact packet."""
    destination_research = _require_dict(state, "destination_research")
    practical = _require_dict(state, "practical_travel_info")
    citations = _merge_citations(
        destination_research.get("citations") or [],
        practical.get("citations") or [],
    )

    packet = {
        "destination_summary": _clean_text(destination_research.get("destination_summary")),
        "duration_fit": _clean_text(destination_research.get("duration_fit")),
        "area_clusters": _clean_dict_list(destination_research.get("area_clusters") or []),
        "must_do_places": _clean_dict_list(destination_research.get("must_do_places") or []),
        "optional_places": _clean_dict_list(destination_research.get("optional_places") or []),
        "niche_or_extra_places": _clean_dict_list(destination_research.get("niche_or_extra_places") or []),
        "best_experiences": _clean_str_list(destination_research.get("best_experiences") or []),
        "best_food": _clean_str_list(destination_research.get("best_food") or []),
        "best_activities": _clean_str_list(destination_research.get("best_activities") or []),
        "weather_temperature": practical.get("weather_temperature") or {},
        "carry": _clean_str_list(practical.get("carry") or []),
        "practical_facts": _clean_str_list(practical.get("practical_facts") or []),
        "practical_notes": _build_practical_notes(practical),
        "constraints": _dedupe(
            _clean_str_list(destination_research.get("constraints") or [])
            + _clean_str_list(practical.get("practical_facts") or [])[:3]
        ),
        "warnings": _dedupe(
            _clean_str_list(destination_research.get("warnings") or [])
            + _clean_str_list(practical.get("warnings") or [])
            + _clean_str_list((practical.get("weather_temperature") or {}).get("warnings") or [])
        ),
        "assumptions": _clean_str_list(destination_research.get("assumptions") or []),
        "citations": citations,
    }
    packet = _compact_research_packet(packet, RESEARCH_PACKET_CHAR_BUDGET)

    return {
        "research_packet": packet,
        "citations": packet.get("citations") or citations,
        "research_warnings": _clean_str_list(packet.get("warnings") or []),
    }


def validate_research_packet(state: dict) -> dict:
    """Validate compactness and readiness for itinerary planning."""
    packet = state.get("research_packet")
    issues: list[str] = []
    repair_target = None

    if not isinstance(packet, dict):
        issues.append("research_packet is missing.")
        repair_target = "aggregate"
    else:
        if not _clean_text(packet.get("destination_summary")):
            issues.append("destination summary is missing.")
            repair_target = repair_target or "destination_research"
        if not _clean_text(packet.get("duration_fit")):
            issues.append("trip-duration fit is missing.")
            repair_target = repair_target or "destination_research"
        if not _clean_dict_list(packet.get("area_clusters") or []):
            issues.append("area/cluster coverage is missing.")
            repair_target = repair_target or "destination_research"
        if not _clean_dict_list(packet.get("must_do_places") or []):
            issues.append("must-do places are missing.")
            repair_target = repair_target or "destination_research"
        if "optional_places" not in packet:
            issues.append("optional-place distinction is missing.")
            repair_target = repair_target or "destination_research"
        if not isinstance(packet.get("practical_notes"), dict) or not packet.get("practical_notes"):
            issues.append("practical travel information is missing.")
            repair_target = repair_target or "practical_travel_info"
        if not packet.get("citations"):
            issues.append("citations are missing for factual research.")
            repair_target = repair_target or "destination_research"
        if len(json.dumps(packet, default=str)) > RESEARCH_PACKET_CHAR_BUDGET:
            issues.append("research packet is too large.")
            repair_target = repair_target or "aggregate"

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
    """Expose a compact debug-friendly destination research result."""
    validation = state.get("research_validation") or {}
    packet = state.get("research_packet")
    if not validation.get("valid"):
        raise ValueError("research_agent_output requires valid research_validation.")
    if not isinstance(packet, dict):
        raise ValueError("research_packet is required for research_agent_output.")

    return {
        "research_agent_output": {
            "destination_summary": packet.get("destination_summary"),
            "duration_fit": packet.get("duration_fit"),
            "must_do_count": len(_clean_dict_list(packet.get("must_do_places") or [])),
            "optional_count": len(_clean_dict_list(packet.get("optional_places") or [])),
            "practical_topics": sorted((packet.get("practical_notes") or {}).keys()),
            "citation_count": len(_clean_dict_list(packet.get("citations") or [])),
            "valid": True,
        }
    }


def _run_research_json(
    *,
    node_type: str,
    system_prompt: str,
    human_prompt: str,
    variables: dict[str, Any],
    cache_payload: dict[str, Any],
) -> dict[str, Any]:
    cache_key = make_cache_key(node_type, cache_payload)
    cached = get_cached_payload(node_type, cache_key)
    if cached is not None:
        return cached

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", human_prompt),
        ]
    )
    model = get_research_llm().bind_tools(
        RESEARCH_TOOLS,
        tool_choice="auto",
        reasoning=RESEARCH_REASONING,
    )
    response = (prompt | model).invoke(variables)
    text = _extract_text_content(response.content)
    payload = _load_json_payload(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{node_type} research must return one JSON object.")

    citations = _merge_citations(
        _extract_response_citations(response.content),
        payload.get("citations") or [],
        payload.get("source_refs") or [],
    )
    payload["citations"] = citations
    set_cached_payload(node_type, cache_key, payload)
    return payload


def _normalize_destination_research(payload: dict[str, Any]) -> dict[str, Any]:
    return _strip_empty(
        {
            "destination_summary": _trim_text(payload.get("destination_summary"), 700),
            "duration_fit": _trim_text(payload.get("duration_fit"), 450),
            "area_clusters": _compact_research_items(payload.get("area_clusters") or [], item_limit=6, text_limit=180),
            "must_do_places": _compact_research_items(payload.get("must_do_places") or [], item_limit=8, text_limit=180),
            "optional_places": _compact_research_items(payload.get("optional_places") or [], item_limit=7, text_limit=160),
            "niche_or_extra_places": _compact_research_items(payload.get("niche_or_extra_places") or [], item_limit=4, text_limit=140),
            "best_experiences": _trim_str_list(payload.get("best_experiences") or [], limit=7, text_limit=140),
            "best_food": _trim_str_list(payload.get("best_food") or [], limit=7, text_limit=120),
            "best_activities": _trim_str_list(payload.get("best_activities") or [], limit=7, text_limit=140),
            "constraints": _trim_str_list(payload.get("constraints") or [], limit=7, text_limit=160),
            "warnings": _trim_str_list(payload.get("warnings") or [], limit=5, text_limit=160),
            "assumptions": _trim_str_list(payload.get("assumptions") or [], limit=5, text_limit=160),
            "citations": _clean_citations(payload.get("citations") or [])[:10],
        },
        keep_empty_keys={"optional_places"},
    )


def _normalize_practical_travel_info(payload: dict[str, Any]) -> dict[str, Any]:
    weather = payload.get("weather_temperature") if isinstance(payload.get("weather_temperature"), dict) else {}
    return _strip_empty(
        {
            "weather_temperature": {
                "summary": _trim_text(weather.get("summary"), 350),
                "facts": _trim_str_list(weather.get("facts") or [], limit=4, text_limit=140),
                "warnings": _trim_str_list(weather.get("warnings") or [], limit=3, text_limit=140),
            },
            "carry": _trim_str_list(payload.get("carry") or [], limit=8, text_limit=120),
            "practical_facts": _trim_str_list(payload.get("practical_facts") or [], limit=8, text_limit=150),
            "local_transport": _trim_str_list(payload.get("local_transport") or [], limit=5, text_limit=150),
            "money": _trim_str_list(payload.get("money") or [], limit=4, text_limit=140),
            "documents": _trim_str_list(payload.get("documents") or [], limit=4, text_limit=140),
            "safety": _trim_str_list(payload.get("safety") or [], limit=5, text_limit=150),
            "connectivity": _trim_str_list(payload.get("connectivity") or [], limit=3, text_limit=130),
            "culture": _trim_str_list(payload.get("culture") or [], limit=3, text_limit=130),
            "warnings": _trim_str_list(payload.get("warnings") or [], limit=5, text_limit=150),
            "citations": _clean_citations(payload.get("citations") or [])[:10],
        }
    )


def _build_practical_notes(practical: dict[str, Any]) -> dict[str, Any]:
    weather = practical.get("weather_temperature") if isinstance(practical.get("weather_temperature"), dict) else {}
    notes = {
        "weather": {
            "summary": _clean_text(weather.get("summary")),
            "facts": _clean_str_list(weather.get("facts") or []),
            "warnings": _clean_str_list(weather.get("warnings") or []),
        },
        "packing": {
            "summary": "Carry guidance for the selected destination and dates.",
            "guidance": _clean_str_list(practical.get("carry") or []),
        },
        "local_practicals": {
            "summary": "Practical on-ground notes.",
            "facts": _clean_str_list(practical.get("practical_facts") or []),
        },
        "local_transport": {
            "summary": "Local movement guidance.",
            "guidance": _clean_str_list(practical.get("local_transport") or []),
        },
        "money": {
            "summary": "Money and payment guidance.",
            "guidance": _clean_str_list(practical.get("money") or []),
        },
        "documents": {
            "summary": "Documents, permits, or ID checks.",
            "guidance": _clean_str_list(practical.get("documents") or []),
        },
        "safety": {
            "summary": "Safety, health, or access notes.",
            "guidance": _clean_str_list(practical.get("safety") or []),
            "warnings": _clean_str_list(practical.get("warnings") or []),
        },
        "connectivity": {
            "summary": "Connectivity notes.",
            "guidance": _clean_str_list(practical.get("connectivity") or []),
        },
        "cultural": {
            "summary": "Local culture or etiquette notes.",
            "guidance": _clean_str_list(practical.get("culture") or []),
        },
    }
    return {
        key: _strip_empty(value)
        for key, value in notes.items()
        if _strip_empty(value) not in ({}, [], None, "")
    }


def _practical_input_projection(research_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "destination": research_input.get("destination"),
        "trip": research_input.get("trip"),
        "group_signals": research_input.get("group_signals"),
        "interests": research_input.get("interests"),
        "pace": research_input.get("pace"),
        "constraints": research_input.get("constraints"),
        "preferences": research_input.get("preferences"),
    }


def _destination_projection(destination_research: dict[str, Any]) -> dict[str, Any]:
    return {
        "destination_summary": destination_research.get("destination_summary"),
        "duration_fit": destination_research.get("duration_fit"),
        "area_clusters": destination_research.get("area_clusters"),
        "must_do_places": destination_research.get("must_do_places"),
        "optional_places": destination_research.get("optional_places"),
        "best_activities": destination_research.get("best_activities"),
        "constraints": destination_research.get("constraints"),
        "warnings": destination_research.get("warnings"),
    }


def _compact_research_packet(packet: dict[str, Any], budget: int) -> dict[str, Any]:
    compact = _strip_empty(packet, keep_empty_keys={"optional_places", "documents"})
    if _json_size(compact) <= budget:
        return compact

    for item_limit, text_limit, citation_limit in [(5, 180, 8), (4, 130, 5), (3, 90, 3)]:
        compact = _strip_empty(
            {
                "destination_summary": _trim_text(packet.get("destination_summary"), text_limit * 3),
                "duration_fit": _trim_text(packet.get("duration_fit"), text_limit * 2),
                "area_clusters": _compact_research_items(packet.get("area_clusters") or [], item_limit=item_limit, text_limit=text_limit),
                "must_do_places": _compact_research_items(packet.get("must_do_places") or [], item_limit=item_limit + 1, text_limit=text_limit),
                "optional_places": _compact_research_items(packet.get("optional_places") or [], item_limit=item_limit, text_limit=text_limit),
                "niche_or_extra_places": _compact_research_items(packet.get("niche_or_extra_places") or [], item_limit=2, text_limit=text_limit),
                "best_experiences": _trim_str_list(packet.get("best_experiences") or [], limit=item_limit, text_limit=text_limit),
                "best_food": _trim_str_list(packet.get("best_food") or [], limit=item_limit, text_limit=text_limit),
                "best_activities": _trim_str_list(packet.get("best_activities") or [], limit=item_limit, text_limit=text_limit),
                "weather_temperature": _compact_nested_value(packet.get("weather_temperature") or {}, item_limit=3, text_limit=text_limit),
                "carry": _trim_str_list(packet.get("carry") or [], limit=item_limit + 1, text_limit=text_limit),
                "practical_facts": _trim_str_list(packet.get("practical_facts") or [], limit=item_limit, text_limit=text_limit),
                "practical_notes": _compact_nested_value(packet.get("practical_notes") or {}, item_limit=4, text_limit=text_limit),
                "constraints": _trim_str_list(packet.get("constraints") or [], limit=item_limit, text_limit=text_limit),
                "warnings": _trim_str_list(packet.get("warnings") or [], limit=item_limit, text_limit=text_limit),
                "assumptions": _trim_str_list(packet.get("assumptions") or [], limit=item_limit, text_limit=text_limit),
                "citations": _compact_citations(packet.get("citations") or [], limit=citation_limit, title_limit=text_limit, url_limit=320),
            },
            keep_empty_keys={"optional_places", "documents"},
        )
        if _json_size(compact) <= budget:
            return compact
    return compact


def _compact_research_items(values: Any, *, item_limit: int, text_limit: int) -> list[dict[str, Any]]:
    if not isinstance(values, list) or item_limit <= 0:
        return []
    priority_keys = ["name", "title", "area", "places", "why", "include_if", "time_need", "notes"]
    compacted = []
    for value in values[:item_limit]:
        if not isinstance(value, dict):
            text = _trim_text(value, text_limit)
            if text:
                compacted.append({"name": text})
            continue
        item = {}
        for key in priority_keys:
            if key in value:
                compact_value = _compact_nested_value(value[key], item_limit=4, text_limit=text_limit)
                if compact_value not in (None, "", [], {}):
                    item[key] = compact_value
        if item:
            compacted.append(item)
    return compacted


def _compact_nested_value(value: Any, *, item_limit: int, text_limit: int) -> Any:
    if isinstance(value, dict):
        compact = {}
        for key, item in list(value.items())[:item_limit]:
            compact_value = _compact_nested_value(item, item_limit=item_limit, text_limit=text_limit)
            if compact_value not in (None, "", [], {}):
                compact[key] = compact_value
        return compact
    if isinstance(value, list):
        return [
            compact_value
            for compact_value in (
                _compact_nested_value(item, item_limit=item_limit, text_limit=text_limit)
                for item in value[:item_limit]
            )
            if compact_value not in (None, "", [], {})
        ]
    return _trim_text(value, text_limit)


def _extract_response_citations(content: Any) -> list[dict[str, str]]:
    citations = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        for annotation in value.get("annotations") or []:
            if not isinstance(annotation, dict):
                continue
            url = _clean_text(annotation.get("url"))
            if url:
                citations.append(
                    {
                        "title": _clean_text(annotation.get("title"), url),
                        "url": url,
                    }
                )
        for key, nested in value.items():
            if key != "annotations":
                visit(nested)

    visit(content)
    return _clean_citations(citations)


def _merge_citations(*citation_groups: Any) -> list[dict[str, str]]:
    merged = []
    seen_urls = set()
    for group in citation_groups:
        for citation in _clean_citations(group):
            url = citation["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(citation)
    return merged[:20]


def _compact_citations(values: Any, *, limit: int, title_limit: int, url_limit: int) -> list[dict[str, str]]:
    citations = []
    for citation in _clean_citations(values)[: max(0, limit)]:
        url = _trim_text(citation.get("url"), url_limit)
        if not url:
            continue
        citations.append(
            {
                "title": _trim_text(citation.get("title"), title_limit) or url,
                "url": url,
            }
        )
    return citations


def _clean_citations(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    citations = []
    seen_urls = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        url = _clean_text(value.get("url"))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        citations.append(
            {
                "title": _clean_text(value.get("title"), url),
                "url": url,
            }
        )
    return citations


def _infer_interests(
    selected_destination: dict[str, Any],
    followup_answers: list[dict[str, Any]],
    custom_note: str,
    change_request: str,
) -> list[str]:
    values = []
    values.extend(_clean_str_list(selected_destination.get("highlights") or []))
    values.extend(_clean_str_list(selected_destination.get("places_covered") or []))
    for answer in followup_answers:
        answer_value = answer.get("answer", "")
        if isinstance(answer_value, list):
            values.extend(_clean_str_list(answer_value))
        else:
            values.append(answer_value)
    values.extend([custom_note, change_request])

    text = " ".join(_clean_str_list(values)).lower()
    interests = []
    keyword_groups = {
        "food": ["food", "cafe", "restaurant", "local cuisine", "street food"],
        "nature": ["nature", "scenic", "mountain", "beach", "forest", "lake", "waterfall"],
        "culture": ["culture", "heritage", "temple", "monastery", "museum", "local"],
        "adventure": ["adventure", "trek", "hike", "rafting", "diving", "safari"],
        "relaxation": ["relax", "peace", "slow", "luxury", "resort"],
        "shopping": ["shopping", "market", "souvenir"],
    }
    for interest, keywords in keyword_groups.items():
        if any(keyword in text for keyword in keywords):
            interests.append(interest)
    return interests or _clean_str_list(selected_destination.get("highlights") or [])[:4]


def _infer_pace(followup_answers: list[dict[str, Any]], custom_note: str, change_request: str) -> str:
    text = _to_json({"answers": followup_answers, "custom_note": custom_note, "change_request": change_request}).lower()
    if _contains_any(text, ["avoid overly packed", "not too packed", "avoid packed", "slow", "relaxed", "peaceful", "comfort", "easy"]):
        return "relaxed"
    if _contains_any(text, ["packed", "fast", "cover more", "explore more", "active"]):
        return "active"
    return "balanced"


def _infer_known_constraints(
    state: dict,
    selected_destination: dict[str, Any],
    custom_note: str,
    change_request: str,
) -> list[str]:
    constraints = []
    if state.get("has_kids"):
        constraints.append("Kid-friendly pacing matters.")
    if state.get("has_seniors"):
        constraints.append("Senior-friendly pacing and access matter.")
    if state.get("budget_mode"):
        constraints.append(f"Budget signal: {state.get('budget_mode')}.")
    if selected_destination.get("duration_fit"):
        constraints.append(str(selected_destination["duration_fit"]))
    for text in [custom_note, change_request]:
        if _contains_any(text.lower(), ["avoid", "must", "need", "prefer", "can't", "cannot"]):
            constraints.append(text[:240])
    return _dedupe(_clean_str_list(constraints))


def _format_destination(selected_destination: dict[str, Any]) -> str:
    region = _clean_text(selected_destination.get("state_or_region"), "Selected destination")
    places = _clean_str_list(selected_destination.get("places_covered") or [])
    return f"{region} ({', '.join(places)})" if places else region


def _compact_destination(selected_destination: dict[str, Any]) -> dict[str, Any]:
    return {
        "state_or_region": _clean_text(selected_destination.get("state_or_region")),
        "places_covered": _clean_str_list(selected_destination.get("places_covered") or []),
        "highlights": _clean_str_list(selected_destination.get("highlights") or []),
        "best_for": _clean_text(selected_destination.get("best_for")),
        "duration_fit": _clean_text(selected_destination.get("duration_fit")),
        "why_it_fits": _clean_text(selected_destination.get("why_it_fits")),
    }


def _clean_followup_answers(values: list[Any]) -> list[dict[str, Any]]:
    answers = []
    for value in values:
        if not isinstance(value, dict):
            continue
        question = _clean_text(value.get("question"))
        input_type = _clean_text(value.get("input_type"), "single_select")
        raw_answer = value.get("answer")
        if isinstance(raw_answer, list):
            answer_list = _trim_str_list(raw_answer, limit=6, text_limit=120)
            answer_value: str | list[str] = answer_list
        else:
            answer_value = _trim_text(raw_answer, 240)

        has_answer = bool(answer_value) if isinstance(answer_value, list) else bool(_clean_text(answer_value))
        if question or has_answer:
            answers.append(
                {
                    "question": question[:240],
                    "input_type": input_type[:32],
                    "answer": answer_value,
                }
            )
    return answers


def _build_curator_summary(
    selected_destination: dict[str, Any],
    followup_answers: list[dict[str, Any]],
    custom_note: str,
    change_request: str,
) -> str:
    """Build a compact deterministic curator summary for research handoff."""
    region = _clean_text(selected_destination.get("state_or_region"), "Selected destination")
    places = _clean_str_list(selected_destination.get("places_covered") or [])
    destination_line = f"Destination: {region}"
    if places:
        destination_line += f" ({', '.join(places[:4])})"

    lines = [destination_line]
    if followup_answers:
        lines.append("Follow-up preferences:")
    for answer in followup_answers:
        question = _clean_text(answer.get("question"))
        answer_value = answer.get("answer")
        if isinstance(answer_value, list):
            answer_text = ", ".join(_clean_str_list(answer_value))
        else:
            answer_text = _clean_text(answer_value)
        if question or answer_text:
            lines.append(f"- {question}: {answer_text or 'No preference selected'}")
    if custom_note:
        lines.append(f"Extra preference: {custom_note}")
    if change_request:
        lines.append(f"Final correction: {change_request}")

    return "\n".join(lines)


def _trim_str_list(values: Any, *, limit: int, text_limit: int) -> list[str]:
    if limit <= 0:
        return []
    return [_trim_text(value, text_limit) for value in _clean_str_list(values)[:limit]]


def _trim_text(value: Any, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _json_size(value: Any) -> int:
    return len(json.dumps(value, default=str))


def _clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


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


def _contains_any(text: str, keywords: list[str]) -> bool:
    for keyword in keywords:
        if keyword.isalpha():
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                return True
        elif keyword in text:
            return True
    return False


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _require_dict(state: dict, key: str) -> dict[str, Any]:
    value = state.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} is required before research can continue.")
    return value


def _to_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)
