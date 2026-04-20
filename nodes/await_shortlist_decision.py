from langgraph.types import interrupt


def await_shortlist_decision(state: dict) -> dict:
    """Pause until the user selects or rejects the shortlist."""
    shortlist_cards = state.get("shortlist_cards", [])
    if not shortlist_cards:
        raise ValueError("No shortlist cards available for selection.")

    decision = interrupt(
        {
            "type": "shortlist_decision",
            "question": "Choose one destination or ask for different suggestions.",
            "shortlist_cards": shortlist_cards,
        }
    )

    if not isinstance(decision, dict):
        raise ValueError("Shortlist decision must be a dictionary.")

    action = decision.get("action")
    updated_state = dict(state)

    if action == "reject":
        rejected_shortlists = list(state.get("rejected_shortlists") or [])
        rejected_shortlists.append([dict(card) for card in shortlist_cards])
        updated_state["shortlist_decision"] = "rejected"
        updated_state["rejected_shortlists"] = rejected_shortlists
        updated_state["shortlist_attempt_count"] = int(state.get("shortlist_attempt_count") or 1) + 1
        updated_state["selected_destination"] = None
        return updated_state

    if action != "select":
        raise ValueError("Shortlist decision action must be 'select' or 'reject'.")

    selected_index = decision.get("selected_index")
    if not isinstance(selected_index, int):
        raise ValueError("Selected destination index must be an integer.")
    if selected_index < 0 or selected_index >= len(shortlist_cards):
        raise ValueError("Selected destination index is out of range.")

    updated_state["shortlist_decision"] = "selected"
    updated_state["selected_destination"] = shortlist_cards[selected_index]
    updated_state["followup_questions"] = []
    updated_state["current_followup_index"] = 0
    updated_state["followup_answers"] = []
    updated_state["followup_custom_note"] = ""
    updated_state["followup_change_request"] = ""
    updated_state["final_brief"] = None
    updated_state["final_action"] = None
    return updated_state
