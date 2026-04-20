import json

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    CONTEXTUAL_DESTINATION_QUESTIONS_HUMAN_PROMPT,
    CONTEXTUAL_DESTINATION_QUESTIONS_SYSTEM_PROMPT,
)
from llm import get_llm
from nodes.call_destination_research import _extract_text_content, _load_json_payload


def _clean_text(value, fallback: str = "") -> str:
    """Normalize possibly-missing text fields from LLM output."""
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip()
    return cleaned or fallback


def _normalize_options(raw_options) -> list[str]:
    """Clean and deduplicate select options while preserving order."""
    cleaned_options: list[str] = []
    for option in raw_options or []:
        if not isinstance(option, str):
            continue
        cleaned_option = option.strip()
        if cleaned_option and cleaned_option not in cleaned_options:
            cleaned_options.append(cleaned_option)
    return cleaned_options


def _normalize_followup_questions(raw_questions) -> list[dict]:
    """Normalize mixed-type follow-up questions to a consistent UI contract."""
    if not isinstance(raw_questions, list):
        raise ValueError("The model must return a JSON list of follow-up question objects.")

    normalized_questions: list[dict] = []

    for item in raw_questions:
        if not isinstance(item, dict):
            continue

        question = _clean_text(item.get("question"))
        if not question:
            continue

        input_type = _clean_text(item.get("input_type")).lower()

        # Backward compatibility for older prompt outputs with only options.
        if not input_type:
            if isinstance(item.get("options"), list):
                input_type = "single_select"
            else:
                input_type = "text"

        why_this_matters = _clean_text(
            item.get("why_this_matters"),
            "Helps tailor the final brief.",
        )

        if input_type in {"single_select", "multi_select"}:
            options = _normalize_options(item.get("options"))
            if len(options) < 2:
                continue
            normalized_questions.append(
                {
                    "question": question,
                    "input_type": input_type,
                    "options": options[:6],
                    "why_this_matters": why_this_matters,
                }
            )
            continue

        if input_type == "text":
            placeholder = _clean_text(
                item.get("placeholder"),
                "Share your preference",
            )
            normalized_questions.append(
                {
                    "question": question,
                    "input_type": "text",
                    "placeholder": placeholder,
                    "why_this_matters": why_this_matters,
                }
            )

    if len(normalized_questions) < 4:
        raise ValueError("The model must return at least 4 usable follow-up questions.")

    return normalized_questions[:6]


def call_generate_contextual_destination_questions(state: dict) -> dict:
    """Generate destination-specific mixed-type follow-up questions."""
    selected_destination = state.get("selected_destination")
    if not isinstance(selected_destination, dict):
        raise ValueError("Selected destination is required before generating questions.")

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
            ("system", CONTEXTUAL_DESTINATION_QUESTIONS_SYSTEM_PROMPT),
            ("human", CONTEXTUAL_DESTINATION_QUESTIONS_HUMAN_PROMPT),
        ]
    )

    response = (prompt | get_llm().bind(reasoning={"effort": "medium"})).invoke(
        {
            "travel_input": json.dumps(travel_input, indent=2),
            "selected_destination": json.dumps(selected_destination, indent=2),
        }
    )
    content = _extract_text_content(response.content)
    raw_questions = _load_json_payload(content)
    questions = _normalize_followup_questions(raw_questions)

    updated_state = dict(state)
    updated_state["followup_questions"] = questions
    updated_state["current_followup_index"] = 0
    updated_state["followup_answers"] = []
    updated_state["followup_custom_note"] = ""
    updated_state["followup_change_request"] = ""
    return updated_state
