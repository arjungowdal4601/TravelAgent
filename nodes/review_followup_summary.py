from langgraph.types import interrupt


def _format_selected_destination(selected_destination: dict) -> str:
    title = selected_destination.get("state_or_region", "Selected destination")
    places = ", ".join(selected_destination.get("places_covered", []))
    if places:
        return f"{title} ({places})"
    return str(title)


def _build_followup_summary(state: dict) -> str:
    selected_destination = state.get("selected_destination") or {}
    answers = state.get("followup_answers") or []
    custom_note = state.get("followup_custom_note") or "No extra notes added."

    lines = [
        "### This is what we understood",
        f"**Destination:** {_format_selected_destination(selected_destination)}",
        "",
        "**Your follow-up choices:**",
    ]

    for index, answer in enumerate(answers, start=1):
        question = answer.get("question", f"Question {index}")
        selected_option = answer.get("answer", "No preference selected")
        lines.append(f"{index}. **{question}**  ")
        lines.append(f"   Answer: {selected_option}")

    lines.extend(
        [
            "",
            "**Extra notes:**",
            str(custom_note),
        ]
    )

    return "\n".join(lines)


def review_followup_summary(state: dict) -> dict:
    """Pause for a final comments box before building the final brief."""
    summary = _build_followup_summary(state)
    response = interrupt(
        {
            "type": "followup_summary",
            "summary": summary,
            "question": "Any changes or comments before we build the final brief?",
        }
    )

    if isinstance(response, dict):
        change_request = str(response.get("followup_change_request") or "").strip()
    else:
        change_request = str(response or "").strip()

    updated_state = dict(state)
    updated_state["followup_change_request"] = change_request
    return updated_state
