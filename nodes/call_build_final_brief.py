import json

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    FINAL_BRIEF_HUMAN_PROMPT,
    FINAL_BRIEF_SYSTEM_PROMPT,
)
from llm import get_llm
from nodes.call_destination_research import _extract_text_content


def call_build_final_brief(state: dict) -> dict:
    """Build the final read-only trip brief."""
    selected_destination = state.get("selected_destination")
    if not isinstance(selected_destination, dict):
        raise ValueError("Selected destination is required before building the final brief.")

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
            ("system", FINAL_BRIEF_SYSTEM_PROMPT),
            ("human", FINAL_BRIEF_HUMAN_PROMPT),
        ]
    )

    response = (prompt | get_llm().bind(reasoning={"effort": "medium"})).invoke(
        {
            "travel_input": json.dumps(travel_input, indent=2),
            "selected_destination": json.dumps(selected_destination, indent=2),
            "followup_answers": json.dumps(state.get("followup_answers", []), indent=2),
            "followup_custom_note": state.get("followup_custom_note", ""),
            "followup_change_request": state.get("followup_change_request", ""),
        }
    )

    final_brief = _extract_text_content(response.content).strip()
    if not final_brief:
        raise ValueError("The model returned an empty final brief.")

    updated_state = dict(state)
    updated_state["final_brief"] = final_brief
    return updated_state
