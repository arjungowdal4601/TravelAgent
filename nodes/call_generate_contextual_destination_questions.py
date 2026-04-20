import json

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    CONTEXTUAL_DESTINATION_QUESTIONS_HUMAN_PROMPT,
    CONTEXTUAL_DESTINATION_QUESTIONS_SYSTEM_PROMPT,
)
from llm import get_llm
from nodes.call_destination_research import _extract_text_content, _load_json_payload


def call_generate_contextual_destination_questions(state: dict) -> dict:
    """Generate destination-specific follow-up questions."""
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

    if not isinstance(raw_questions, list):
        raise ValueError("The model must return a JSON list of MCQ question objects.")

    questions = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue

        question = item.get("question")
        options = item.get("options")
        if not isinstance(question, str) or not isinstance(options, list):
            continue

        cleaned_question = question.strip()
        cleaned_options = []
        for option in options:
            if not isinstance(option, str):
                continue
            cleaned_option = option.strip()
            if cleaned_option and cleaned_option not in cleaned_options:
                cleaned_options.append(cleaned_option)

        if cleaned_question and len(cleaned_options) >= 3:
            questions.append(
                {
                    "question": cleaned_question,
                    "options": cleaned_options[:4],
                }
            )

    if len(questions) < 4:
        raise ValueError("The model must return exactly 4 usable MCQ follow-up questions.")

    updated_state = dict(state)
    updated_state["followup_questions"] = questions[:4]
    updated_state["current_followup_index"] = 0
    updated_state["followup_answers"] = []
    updated_state["followup_custom_note"] = ""
    updated_state["followup_change_request"] = ""
    return updated_state
