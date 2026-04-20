import json

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    DESTINATION_RESEARCH_HUMAN_PROMPT,
    DESTINATION_RESEARCH_SYSTEM_PROMPT,
)
from llm import get_llm
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

    llm = get_llm().bind(reasoning=CURATOR_REASONING)
    response = (prompt | llm).invoke(
        {"travel_input": json.dumps(travel_input, indent=2)}
    )
    content = extract_text_content(response.content)
    shortlisted_destinations = load_json_payload(content)

    if not isinstance(shortlisted_destinations, list) or len(shortlisted_destinations) != 4:
        raise ValueError("The model must return exactly 4 destination groups.")

    updated_state = dict(state)
    updated_state["shortlisted_destinations"] = shortlisted_destinations
    updated_state["shortlist_attempt_count"] = max(int(state.get("shortlist_attempt_count") or 0), 1)
    return updated_state
