import json

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    DESTINATION_RESEARCH_WITH_USER_HINT_HUMAN_PROMPT,
    DESTINATION_RESEARCH_WITH_USER_HINT_SYSTEM_PROMPT,
)
from llm import get_llm
from nodes.call_destination_research import _extract_text_content, _load_json_payload


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

    llm = get_llm().bind(reasoning={"effort": "medium"})
    response = (prompt | llm).invoke(
        {
            "travel_input": json.dumps(travel_input, indent=2),
            "user_hint": state.get("user_hint", ""),
        }
    )
    content = _extract_text_content(response.content)
    shortlisted_destinations = _load_json_payload(content)

    if not isinstance(shortlisted_destinations, list) or len(shortlisted_destinations) != 4:
        raise ValueError("The model must return exactly 4 destination groups.")

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
