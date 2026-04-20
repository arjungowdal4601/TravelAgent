from langgraph.types import interrupt


def _clean_text(value, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip()
    return cleaned or fallback


def _clean_str_list(values) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _format_answer(answer_value) -> str | list[str]:
    if isinstance(answer_value, list):
        return _clean_str_list(answer_value)
    return _clean_text(answer_value, "No preference selected")


def _build_followup_confirmation_payload(state: dict) -> dict:
    selected_destination = state.get("selected_destination") or {}
    answers = state.get("followup_answers") or []
    followup_answers = []

    for index, answer in enumerate(answers, start=1):
        if not isinstance(answer, dict):
            continue
        followup_answers.append(
            {
                "index": index,
                "question": _clean_text(answer.get("question"), f"Question {index}"),
                "input_type": _clean_text(answer.get("input_type"), "single_select"),
                "answer": _format_answer(answer.get("answer")),
            }
        )

    return {
        "type": "followup_confirmation",
        "selected_destination": {
            "card_title": _clean_text(selected_destination.get("card_title")),
            "state_or_region": _clean_text(selected_destination.get("state_or_region"), "Selected destination"),
            "places_covered": _clean_str_list(selected_destination.get("places_covered") or []),
        },
        "followup_answers": followup_answers,
        "followup_custom_note": _clean_text(
            state.get("followup_custom_note"),
            "No extra preference provided.",
        ),
        "question": "Do you want to change anything mentioned here?",
        "actions": ["continue", "start_over"],
    }


def _merge_final_correction(existing_change_request: str, new_change_request: str) -> str:
    existing = _clean_text(existing_change_request)
    correction = _clean_text(new_change_request)

    if not correction:
        return existing

    merged_parts = []
    if existing:
        merged_parts.append(existing)
    merged_parts.append(f"Final correction: {correction}")
    return "\n".join(merged_parts)


def review_followup_summary(state: dict) -> dict:
    """Pause for a final Streamlit confirmation before research handoff."""
    response = interrupt(_build_followup_confirmation_payload(state))

    if isinstance(response, dict):
        action = _clean_text(response.get("action"))
        change_request = _clean_text(response.get("followup_change_request"))
    else:
        action = _clean_text(response)
        change_request = ""

    if action not in {"continue", "start_over"}:
        raise ValueError("Final action must be 'continue' or 'start_over'.")

    updated_state = dict(state)
    updated_state["followup_change_request"] = _merge_final_correction(
        str(state.get("followup_change_request") or ""),
        change_request,
    )
    updated_state["final_action"] = action
    return updated_state
