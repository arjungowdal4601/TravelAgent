from langgraph.types import interrupt


def show_read_only_final_brief(state: dict) -> dict:
    """Pause so the UI can show the final brief and final actions."""
    final_brief = state.get("final_brief")
    if not isinstance(final_brief, str) or not final_brief.strip():
        raise ValueError("Final brief is required before showing final actions.")

    response = interrupt(
        {
            "type": "final_brief",
            "final_brief": final_brief,
            "actions": ["continue", "start_over"],
        }
    )

    if isinstance(response, dict):
        action = str(response.get("action") or "").strip()
    else:
        action = str(response or "").strip()

    if action not in {"continue", "start_over"}:
        raise ValueError("Final action must be 'continue' or 'start_over'.")

    updated_state = dict(state)
    updated_state["final_action"] = action
    return updated_state
