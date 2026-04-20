import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    DESTINATION_RESEARCH_HUMAN_PROMPT,
    DESTINATION_RESEARCH_SYSTEM_PROMPT,
)
from llm import get_curator_search_llm, get_llm
from services.llm_response_parsing import extract_text_content, load_json_payload


CURATOR_REASONING = {"effort": "medium"}


def call_destination_research(state: dict) -> dict:
    """Shortlist exactly 4 India destination groups from the current graph state."""
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
            ("system", DESTINATION_RESEARCH_SYSTEM_PROMPT),
            ("human", DESTINATION_RESEARCH_HUMAN_PROMPT),
        ]
    )

    response = invoke_curator_prompt(prompt, {"travel_input": json.dumps(travel_input, indent=2)})
    content = extract_text_content(response.content)
    shortlisted_destinations = sanitize_shortlist_cards(load_json_payload(content))

    if not isinstance(shortlisted_destinations, list) or len(shortlisted_destinations) != 4:
        raise ValueError("The model must return exactly 4 destination groups.")

    updated_state = dict(state)
    updated_state["shortlisted_destinations"] = shortlisted_destinations
    updated_state["shortlist_attempt_count"] = max(int(state.get("shortlist_attempt_count") or 0), 1)
    return updated_state


def invoke_curator_prompt(prompt: ChatPromptTemplate, payload: dict[str, Any]) -> Any:
    """Run curator prompts with web grounding, falling back to the standard model."""
    try:
        return (prompt | get_curator_search_llm()).invoke(payload)
    except Exception:
        llm = get_llm().bind(reasoning=CURATOR_REASONING)
        return (prompt | llm).invoke(payload)


def sanitize_shortlist_cards(payload: Any) -> Any:
    """Remove source/citation leakage from model-generated card JSON."""
    if isinstance(payload, list):
        return [sanitize_shortlist_cards(item) for item in payload]
    if isinstance(payload, dict):
        return {key: sanitize_shortlist_cards(value) for key, value in payload.items()}
    if isinstance(payload, str):
        return _strip_source_noise(payload)
    return payload


def _strip_source_noise(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", "", text)
    cleaned = re.sub(r"www\.\S+", "", cleaned)
    cleaned = re.sub(r"【[^】]*】", "", cleaned)
    cleaned = re.sub(r"\[\s*(?:\d+|source|citation|ref|reference)\s*\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:source|citation|url)\s*:\s*\S+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -;,.")
