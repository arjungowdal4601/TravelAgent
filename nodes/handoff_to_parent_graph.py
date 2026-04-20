def handoff_to_parent_graph(state: dict) -> dict:
    """Mark the information curator flow as complete for future handoff."""
    updated_state = dict(state)
    updated_state["information_curator_complete"] = True
    return updated_state
