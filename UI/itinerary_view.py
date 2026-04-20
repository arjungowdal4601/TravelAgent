import streamlit as st

def render_itinerary_view() -> None:
    """Render the final itinerary from graph state without mutating graph output."""
    graph_state = st.session_state.graph_state or {}
    final_itinerary = graph_state.get("final_itinerary")
    markdown = graph_state.get("final_itinerary_markdown")
    validation = graph_state.get("itinerary_validation")

    st.title("Final Itinerary")
    total_seconds = st.session_state.get("graph_total_seconds")
    if isinstance(total_seconds, (int, float)):
        st.caption(f"Generated in {total_seconds:.1f} seconds")

    if not markdown:
        st.info("The final itinerary is not available yet.")
        if validation:
            with st.expander("Itinerary validation"):
                st.json(validation)
        return

    st.markdown(markdown)

    with st.expander("Structured itinerary"):
        st.json(final_itinerary or {})

    if validation:
        with st.expander("Itinerary validation"):
            st.json(validation)
