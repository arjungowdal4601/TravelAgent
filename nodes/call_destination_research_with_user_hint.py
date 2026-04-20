import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    DESTINATION_RESEARCH_WITH_USER_HINT_HUMAN_PROMPT,
    DESTINATION_RESEARCH_WITH_USER_HINT_SYSTEM_PROMPT,
)
from llm import get_llm
from nodes.call_destination_research import CURATOR_REASONING
from services.llm_response_parsing import extract_text_content, load_json_payload


MAX_REJECTED_CARDS_IN_PROMPT = 12


def call_destination_research_with_user_hint(state: dict) -> dict:
    """Shortlist 4 India destination groups using the user's rough preference."""
    travel_input = {
        "origin": state.get("origin"),
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
        "trip_days": state.get("trip_days"),
        "trip_type": state.get("trip_type"),
        "member_count": state.get("member_count"),
        "has_kids": state.get("has_kids"),
        "has_seniors": state.get("has_seniors"),
        "budget_mode": state.get("budget_mode"),
        "budget_value": state.get("budget_value"),
    }

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", DESTINATION_RESEARCH_WITH_USER_HINT_SYSTEM_PROMPT),
            ("human", DESTINATION_RESEARCH_WITH_USER_HINT_HUMAN_PROMPT),
        ]
    )

    llm = get_llm().bind(reasoning=CURATOR_REASONING)
    rejected_summaries = summarize_rejected_shortlists(state.get("rejected_shortlists") or [])
    shortlist_attempt_count = int(state.get("shortlist_attempt_count") or 2)
    response = (prompt | llm).invoke(
        {
            "travel_input": json.dumps(travel_input, indent=2),
            "user_hint": state.get("user_hint", ""),
            "rejected_shortlists": json.dumps(rejected_summaries, indent=2),
            "shortlist_attempt_count": shortlist_attempt_count,
        }
    )
    content = extract_text_content(response.content)
    shortlisted_destinations = load_json_payload(content)

    if not isinstance(shortlisted_destinations, list) or len(shortlisted_destinations) != 4:
        raise ValueError("The model must return exactly 4 destination groups.")
    validate_regenerated_shortlist(
        shortlisted_destinations,
        state.get("rejected_shortlists") or [],
        state.get("user_hint", ""),
    )

    updated_state = dict(state)
    updated_state["shortlisted_destinations"] = shortlisted_destinations
    updated_state["explained_shortlisted_destinations"] = []
    updated_state["shortlist_cards"] = []
    updated_state["shortlist_decision"] = None
    updated_state["selected_destination"] = None
    updated_state["followup_questions"] = []
    updated_state["current_followup_index"] = 0
    updated_state["followup_answers"] = []
    updated_state["followup_custom_note"] = ""
    updated_state["followup_change_request"] = ""
    updated_state["final_brief"] = None
    updated_state["final_action"] = None
    return updated_state


def summarize_rejected_shortlists(rejected_shortlists: Any) -> list[dict[str, Any]]:
    """Return compact rejected card summaries for the retry prompt."""
    summaries = []
    for card in _flatten_rejected_cards(rejected_shortlists):
        state_or_region = _clean_text(card.get("state_or_region"))
        title = _clean_text(card.get("card_title"))
        places = _clean_str_list(card.get("places_covered") or [])[:4]
        highlights = _clean_str_list(card.get("highlights") or [])[:4]
        summary = {
            "card_title": title,
            "state_or_region": state_or_region,
            "places_covered": places,
            "trip_feel": _clean_text(card.get("trip_feel")),
            "best_for": _clean_text(card.get("best_for")),
            "highlights": highlights,
        }
        compact = {key: value for key, value in summary.items() if value not in ("", [])}
        if compact:
            summaries.append(compact)
        if len(summaries) >= MAX_REJECTED_CARDS_IN_PROMPT:
            break
    return summaries


def validate_regenerated_shortlist(
    shortlisted_destinations: list[dict[str, Any]],
    rejected_shortlists: Any,
    user_hint: Any,
) -> None:
    """Reject retry shortlists that substantially repeat rejected suggestions."""
    rejected_cards = _flatten_rejected_cards(rejected_shortlists)
    if not rejected_cards:
        return

    repeated_cards = []
    hint = _normalize_text(user_hint)
    for candidate in shortlisted_destinations:
        if not isinstance(candidate, dict):
            continue
        for rejected in rejected_cards:
            if _hint_explicitly_allows_rejected_card(hint, rejected):
                continue
            if _cards_substantially_overlap(candidate, rejected):
                repeated_cards.append(candidate)
                break

    if len(repeated_cards) >= 2:
        repeated_labels = [
            _clean_text(card.get("card_title"))
            or _clean_text(card.get("state_or_region"))
            or "Repeated card"
            for card in repeated_cards[:3]
        ]
        raise ValueError(
            "Regenerated shortlist repeats rejected suggestions too closely: "
            + ", ".join(repeated_labels)
        )


def _cards_substantially_overlap(candidate: dict[str, Any], rejected: dict[str, Any]) -> bool:
    candidate_region = _normalize_text(candidate.get("state_or_region"))
    rejected_region = _normalize_text(rejected.get("state_or_region"))
    if candidate_region and candidate_region == rejected_region:
        return True

    candidate_title = _normalize_text(candidate.get("card_title"))
    rejected_title = _normalize_text(rejected.get("card_title"))
    if candidate_title and candidate_title == rejected_title:
        return True

    candidate_places = {_normalize_text(value) for value in _clean_str_list(candidate.get("places_covered") or [])}
    rejected_places = {_normalize_text(value) for value in _clean_str_list(rejected.get("places_covered") or [])}
    candidate_places.discard("")
    rejected_places.discard("")
    if not candidate_places or not rejected_places:
        return False

    overlap = candidate_places & rejected_places
    return len(overlap) >= min(2, len(candidate_places), len(rejected_places))


def _hint_explicitly_allows_rejected_card(normalized_hint: str, rejected: dict[str, Any]) -> bool:
    if not normalized_hint:
        return False

    candidates = [
        _normalize_text(rejected.get("state_or_region")),
        _normalize_text(rejected.get("card_title")),
    ]
    candidates.extend(_normalize_text(value) for value in _clean_str_list(rejected.get("places_covered") or []))

    return any(value and value in normalized_hint for value in candidates)


def _flatten_rejected_cards(rejected_shortlists: Any) -> list[dict[str, Any]]:
    if not isinstance(rejected_shortlists, list):
        return []
    cards = []
    for item in rejected_shortlists:
        if isinstance(item, dict):
            cards.append(item)
        elif isinstance(item, list):
            cards.extend(value for value in item if isinstance(value, dict))
    return cards


def _clean_text(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = " ".join(value.strip().split())
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


def _normalize_text(value: Any) -> str:
    text = _clean_text(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()
