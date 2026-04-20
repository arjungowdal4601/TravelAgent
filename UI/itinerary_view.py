import streamlit as st

from nodes.itinerary_artifacts import read_itinerary_artifact


def render_itinerary_view() -> None:
    """Render the final itinerary from graph state without mutating graph output."""
    graph_state = st.session_state.graph_state or {}
    final_itinerary = graph_state.get("final_itinerary")
    markdown = graph_state.get("final_itinerary_markdown")
    full_markdown = read_itinerary_artifact(graph_state.get("final_itinerary_markdown_ref"))
    if isinstance(full_markdown, str) and full_markdown.strip():
        markdown = full_markdown
    validation = graph_state.get("itinerary_validation")

    st.title("Final Itinerary")

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
