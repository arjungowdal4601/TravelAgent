import streamlit as st


def render_chat() -> None:
    for message in st.session_state.messages:
        chat_role = "assistant" if message["role"] == "ai" else "user"
        with st.chat_message(chat_role):
            st.markdown(message["content"])


def render_selected_destination(card: dict) -> None:
    """Show the user's selected destination after clicking Select."""
    st.success("Destination selected.")
    with st.container(border=True):
        st.subheader(card.get("state_or_region", "Selected Destination"))
        st.write("**Places Covered**")
        st.write(", ".join(card.get("places_covered", [])))
        st.write("**Estimated Price Range**")
        st.write(card.get("estimated_price_range", ""))
        st.write("**Highlights**")
        for point in card.get("highlights", []):
            st.write(f"- {point}")
        st.write("**Best For**")
        st.write(card.get("best_for", ""))
        st.write("**Duration Fit**")
        st.write(card.get("duration_fit", ""))
        st.write("**Why It Fits**")
        st.write(card.get("why_it_fits", ""))


def render_destination_shortlist_cards(shortlist_cards: list[dict]) -> dict | None:
    """Render destination cards and return the selected card, if any."""
    if not shortlist_cards:
        return None

    st.subheader("Choose Your Destination")
    st.write("Select one destination card to continue.")

    for index, card in enumerate(shortlist_cards):
        if _render_destination_card(card, index):
            return card

    return None


def render_shortlist_decision(shortlist_cards: list[dict]) -> dict | None:
    """Render shortlist decision UI for the graph interrupt."""
    if not shortlist_cards:
        st.warning("No shortlist cards are available yet.")
        return None

    st.subheader("Choose Your Destination")
    st.write("Select one destination, or ask for different suggestions.")

    for index, card in enumerate(shortlist_cards):
        if _render_destination_card(card, index):
            return {"action": "select", "selected_index": index}

    st.divider()
    if st.button("Show different destinations", key="reject_shortlist", use_container_width=True):
        return {"action": "reject"}

    return None


def render_half_baked_plan_input(interrupt_payload: dict) -> dict | None:
    """Render the rough-plan prompt and return the user's hint."""
    st.subheader(interrupt_payload.get("question", "Do you have any half-baked plan or trip feel in mind?"))

    examples = interrupt_payload.get("examples", [])
    if examples:
        st.caption("Examples: " + ", ".join(examples))

    user_hint = st.text_input(
        "Your rough idea",
        key="half_baked_plan_input",
        placeholder="cool weather and peaceful nature",
    )

    if st.button("Generate new shortlist", key="submit_half_baked_plan", use_container_width=True):
        return {"user_hint": user_hint}

    return None


def render_followup_question(interrupt_payload: dict) -> dict | None:
    """Render one MCQ follow-up question and return the selected option."""
    current_index = int(interrupt_payload.get("current_index", 0))
    total_questions = int(interrupt_payload.get("total_questions", 1))
    question = interrupt_payload.get("question", "Tell me your preference.")
    options = interrupt_payload.get("options", [])

    st.subheader(f"Follow-up question {current_index + 1} of {total_questions}")
    st.write(question)

    if not options:
        st.error("No answer options are available for this question.")
        return None

    answer = st.radio(
        "Choose one option",
        options,
        key=f"followup_answer_input_{current_index}",
    )

    if st.button("Submit answer", key=f"submit_followup_answer_{current_index}", use_container_width=True):
        return {"answer": answer}

    return None


def render_custom_followup_input(interrupt_payload: dict) -> dict | None:
    """Render the free-text extra notes box after MCQs."""
    st.subheader(interrupt_payload.get("question", "Anything else you want us to know?"))

    help_text = interrupt_payload.get("help_text")
    if help_text:
        st.caption(help_text)

    custom_note = st.text_area(
        "Extra notes",
        key="followup_custom_note_input",
        placeholder="Add preferences, concerns, must-visit places, or anything else.",
    )

    if st.button("Continue", key="submit_custom_followup_note", use_container_width=True):
        return {"followup_custom_note": custom_note}

    return None


def render_followup_summary_review(interrupt_payload: dict) -> dict | None:
    """Render the read-only follow-up summary and final comments box."""
    st.markdown(interrupt_payload.get("summary", ""))

    change_request = st.text_area(
        interrupt_payload.get("question", "Any changes or comments before we build the final brief?"),
        key="followup_change_request_input",
        placeholder="Add changes, corrections, or extra comments.",
    )

    if st.button("Build final brief", key="submit_followup_summary_review", use_container_width=True):
        return {"followup_change_request": change_request}

    return None


def render_final_brief_actions(interrupt_payload: dict) -> dict | None:
    """Render the final brief and return the chosen final action."""
    st.subheader("Final Trip Brief")
    st.markdown(interrupt_payload.get("final_brief", ""))

    left, right = st.columns(2)
    if left.button("Continue to research and itinerary", key="continue_final_brief", use_container_width=True):
        return {"action": "continue"}
    if right.button("Start over", key="start_over_final_brief", use_container_width=True):
        return {"action": "start_over"}

    return None


def _truncate_text(text: str, limit: int = 80) -> str:
    """Keep card text compact and easy to scan."""
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _render_bullets(values: list[str], limit: int = 4) -> None:
    """Render small bullet lists for compact cards."""
    for value in values[:limit]:
        st.caption(f"- {_truncate_text(value, 36)}")


def _render_destination_card(card: dict, index: int) -> bool:
    """Render one destination card and return True when selected."""
    with st.container(border=True):
        st.markdown(f"### {_truncate_text(card.get('state_or_region', f'Destination {index + 1}'), 28)}")
        st.caption(f"Places: {_truncate_text(', '.join(card.get('places_covered', [])), 58)}")
        st.caption(f"Best For: {_truncate_text(card.get('best_for', ''), 42)}")
        st.caption(f"Duration: {_truncate_text(card.get('duration_fit', ''), 42)}")
        st.caption(f"Price: {_truncate_text(card.get('estimated_price_range', ''), 42)}")
        st.caption(f"Fit: {_truncate_text(card.get('why_it_fits', ''), 52)}")
        st.caption("Highlights:")
        _render_bullets(card.get("highlights", []), limit=4)

        return st.button("Select", key=f"select_destination_{index}", use_container_width=True)
