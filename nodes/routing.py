from langgraph.graph import END


def route_shortlist_decision(state: dict) -> str:
    """Route after the user accepts or rejects the shortlist."""
    if state.get("shortlist_decision") == "selected":
        return "call_generate_contextual_destination_questions"
    if state.get("shortlist_decision") == "rejected":
        return "ask_half_baked_plan"
    raise ValueError("shortlist_decision must be 'selected' or 'rejected'.")


def route_followup_progress(state: dict) -> str:
    """Loop until every follow-up question has an answer."""
    questions = state.get("followup_questions", [])
    current_index = int(state.get("current_followup_index") or 0)

    if current_index < len(questions):
        return "collect_followup_answers"
    return "collect_custom_followup_input"


def route_final_action(state: dict) -> str:
    """Route after the final confirmation action."""
    if state.get("final_action") == "continue":
        return "handoff_to_parent_graph"
    if state.get("final_action") == "start_over":
        return END
    raise ValueError("final_action must be 'continue' or 'start_over'.")


def route_research_validation(state: dict) -> str:
    """Route one compact research repair pass or continue to itinerary planning."""
    validation = state.get("research_validation") or {}
    if validation.get("valid"):
        return "prepare_itinerary_input"

    repair_target = validation.get("repair_target")
    if repair_target == "destination_knowledge":
        return "destination_knowledge_agent"
    if repair_target == "travel_essentials":
        return "travel_essentials_agent"
    if repair_target == "aggregate":
        return "research_aggregator"
    return END


# Backward-compatible itinerary routing alias for older tests/imports.
def route_itinerary_validation(state: dict) -> str:
    validation = state.get("itinerary_validation") or {}
    if validation.get("valid"):
        return "render_clean_itinerary_markdown"
    return END
