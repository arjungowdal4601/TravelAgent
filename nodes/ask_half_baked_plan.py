from langgraph.types import interrupt


def ask_half_baked_plan(state: dict) -> dict:
    """Pause and ask for the user's rough destination preference."""
    answer = interrupt(
        {
            "type": "half_baked_plan",
            "question": "Do you have any half-baked plan or trip feel in mind?",
            "examples": [
                "Uttarakhand",
                "Uttarakhand trekking",
                "beach with adventure sports",
                "cool weather and peaceful nature",
            ],
        }
    )

    if isinstance(answer, dict):
        user_hint = str(answer.get("user_hint") or answer.get("answer") or "").strip()
    else:
        user_hint = str(answer or "").strip()

    if not user_hint:
        user_hint = "No specific preference. Suggest better options."

    updated_state = dict(state)
    updated_state["user_hint"] = user_hint
    return updated_state
