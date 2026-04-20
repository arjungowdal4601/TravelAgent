from langgraph.types import interrupt


def collect_custom_followup_input(state: dict) -> dict:
    """Pause for any extra notes after the MCQ answers."""
    response = interrupt(
        {
            "type": "custom_followup_input",
            "question": "Anything else you want us to know before we prepare the brief?",
            "help_text": "Add preferences, concerns, must-visit places, or anything the options did not cover.",
        }
    )

    if isinstance(response, dict):
        custom_note = str(response.get("followup_custom_note") or "").strip()
    else:
        custom_note = str(response or "").strip()

    updated_state = dict(state)
    updated_state["followup_custom_note"] = custom_note
    return updated_state
