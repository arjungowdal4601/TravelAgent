from datetime import date
from pathlib import Path

import streamlit as st
from langgraph.types import Command

from main import travel_graph
from UI.components import (
    render_chat,
    render_custom_followup_input,
    render_final_brief_actions,
    render_followup_question,
    render_followup_summary_review,
    render_half_baked_plan_input,
    render_shortlist_decision,
)
from UI.itinerary_view import render_itinerary_view
from UI.location_data import load_location_map
from UI.session_state import (
    add_message,
    build_graph_input,
    ensure_ai_prompt,
    finish_flow,
    init_state,
    reset_app_state,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_app() -> None:
    st.set_page_config(page_title="Travel Planner Chat", page_icon="T")

    location_map = load_location_map(PROJECT_ROOT)
    init_state(location_map)
    ensure_ai_prompt(st.session_state.step)

    graph_state = st.session_state.graph_state or {}
    has_itinerary = bool(graph_state.get("itinerary_view_ready") and graph_state.get("final_itinerary_markdown"))
    if has_itinerary:
        _render_view_switcher()
        if st.session_state.view == "itinerary":
            render_itinerary_view()
            return
    elif st.session_state.view == "itinerary":
        st.session_state.view = "chat"

    st.title("Travel Planner Chat")
    st.caption("A simple Streamlit chat UI for collecting the basic inputs for a trip.")

    render_chat()

    step = st.session_state.step
    trip_data = st.session_state.trip_data

    if step == "ask_origin":
        _render_origin_step(location_map, trip_data)
    elif step == "ask_dates":
        _render_dates_step(trip_data)
    elif step == "ask_trip_type":
        _render_trip_type_step(trip_data)
    elif step == "ask_member_count":
        _render_member_count_step(trip_data)
    elif step == "ask_special_members":
        _render_special_members_step(trip_data)
    elif step == "ask_budget_mode":
        _render_budget_mode_step(trip_data)
    elif step == "ask_budget_value":
        _render_budget_value_step(trip_data)
    elif step == "done":
        _render_done_step(location_map)


def _render_origin_step(location_map: dict[str, list[str]], trip_data: dict) -> None:
    states = list(location_map.keys())
    selected_state = st.selectbox("Select your state", states, key="origin_state_input")
    cities = location_map[selected_state]

    if st.session_state.get("origin_city_input") not in cities:
        st.session_state.origin_city_input = cities[0]

    selected_city = st.selectbox("Select your city or district", cities, key="origin_city_input")

    if st.button("Confirm origin", use_container_width=True):
        trip_data["origin_state"] = selected_state
        trip_data["origin_city"] = selected_city
        trip_data["origin"] = f"{selected_city}, {selected_state}"
        add_message("user", trip_data["origin"])
        st.session_state.step = "ask_dates"
        ensure_ai_prompt("ask_dates")
        st.rerun()


def _render_dates_step(trip_data: dict) -> None:
    date_range = st.date_input(
        "Select your trip date range",
        key="date_range_input",
        min_value=date.today(),
    )

    if st.button("Submit dates", use_container_width=True):
        if not isinstance(date_range, (list, tuple)) or len(date_range) != 2:
            st.error("Please select both a start date and an end date in the same date picker.")
        else:
            start_date, end_date = date_range
            trip_data["start_date"] = start_date.isoformat()
            trip_data["end_date"] = end_date.isoformat()
            add_message("user", f"{trip_data['start_date']} to {trip_data['end_date']}")
            st.session_state.step = "ask_trip_type"
            ensure_ai_prompt("ask_trip_type")
            st.rerun()


def _render_trip_type_step(trip_data: dict) -> None:
    st.write("Choose one option:")
    trip_options = ["solo", "couple", "family", "group"]
    option_columns = st.columns(len(trip_options))

    for index, option in enumerate(trip_options):
        if option_columns[index].button(option.title(), key=f"trip_type_{option}", use_container_width=True):
            trip_data["trip_type"] = option
            add_message("user", option.title())

            if option == "solo":
                trip_data["member_count"] = 1
                trip_data["has_seniors"] = False
                trip_data["has_kids"] = False
                next_step = "ask_budget_mode"
            elif option == "couple":
                trip_data["member_count"] = 2
                trip_data["has_seniors"] = False
                trip_data["has_kids"] = False
                next_step = "ask_budget_mode"
            else:
                trip_data["member_count"] = None
                trip_data["has_seniors"] = None
                trip_data["has_kids"] = None
                next_step = "ask_member_count"

            st.session_state.step = next_step
            ensure_ai_prompt(next_step)
            st.rerun()


def _render_member_count_step(trip_data: dict) -> None:
    member_count = st.chat_input("Enter the number of members")
    if member_count:
        value = member_count.strip()
        if not value.isdigit() or int(value) < 2:
            st.error("Please enter a whole number greater than or equal to 2.")
        else:
            trip_data["member_count"] = int(value)
            add_message("user", value)
            next_step = "ask_special_members" if trip_data["trip_type"] in {"family", "group"} else "ask_budget_mode"
            st.session_state.step = next_step
            ensure_ai_prompt(next_step)
            st.rerun()


def _render_special_members_step(trip_data: dict) -> None:
    st.write("Choose one option:")
    presence_options = [
        ("none", "No seniors or kids"),
        ("seniors", "Seniors only"),
        ("kids", "Kids only"),
        ("both", "Both"),
    ]
    presence_columns = st.columns(len(presence_options))

    for index, (value, label) in enumerate(presence_options):
        if presence_columns[index].button(label, key=f"special_members_{value}", use_container_width=True):
            trip_data["has_seniors"] = value in {"seniors", "both"}
            trip_data["has_kids"] = value in {"kids", "both"}
            add_message("user", label)
            st.session_state.step = "ask_budget_mode"
            ensure_ai_prompt("ask_budget_mode")
            st.rerun()


def _render_budget_mode_step(trip_data: dict) -> None:
    st.write("Choose one option:")
    budget_options = ["standard", "premium", "luxury", "custom"]
    budget_columns = st.columns(len(budget_options))

    for index, option in enumerate(budget_options):
        if budget_columns[index].button(option.title(), key=f"budget_mode_{option}", use_container_width=True):
            trip_data["budget_mode"] = option
            add_message("user", option.title())

            if option == "custom":
                st.session_state.step = "ask_budget_value"
                ensure_ai_prompt("ask_budget_value")
            else:
                trip_data["budget_value"] = None
                finish_flow()

            st.rerun()


def _render_budget_value_step(trip_data: dict) -> None:
    budget_value = st.slider(
        "Select a custom budget amount",
        min_value=5000,
        max_value=300000,
        step=1000,
        key="budget_slider_value",
    )

    if st.button("Confirm budget", use_container_width=True):
        trip_data["budget_value"] = budget_value
        add_message("user", str(budget_value))
        finish_flow()
        st.rerun()


def _render_done_step(location_map: dict[str, list[str]]) -> None:
    st.info("Input collection is complete.")

    if st.session_state.graph_error:
        st.error(st.session_state.graph_error)

    try:
        if st.session_state.graph_state is None and st.session_state.graph_interrupt is None:
            result = travel_graph.invoke(build_graph_input(), config=_graph_config())
            _sync_graph_result(result)
        st.session_state.graph_error = None
    except Exception as exc:
        st.session_state.graph_error = f"Could not run travel graph: {exc}"
        st.error(st.session_state.graph_error)
        return

    if st.session_state.graph_interrupt:
        _render_graph_interrupt(st.session_state.graph_interrupt, location_map)
        return

    _render_graph_completion(location_map)


def _graph_config() -> dict:
    return {"configurable": {"thread_id": st.session_state.graph_thread_id}}


def _render_view_switcher() -> None:
    left, right = st.columns(2)
    if left.button("Chat Flow", key="view_chat", use_container_width=True):
        st.session_state.view = "chat"
        st.rerun()
    if right.button("Itinerary View", key="view_itinerary", use_container_width=True):
        st.session_state.view = "itinerary"
        st.rerun()


def _sync_graph_result(result: dict | None) -> None:
    graph_state = travel_graph.get_state(_graph_config())
    st.session_state.graph_state = dict(graph_state.values or {})

    interrupts = []
    if isinstance(result, dict):
        interrupts = result.get("__interrupt__", [])

    if interrupts:
        st.session_state.graph_interrupt = interrupts[0].value
    else:
        st.session_state.graph_interrupt = None


def _resume_graph(payload: dict, location_map: dict[str, list[str]]) -> None:
    try:
        result = travel_graph.invoke(Command(resume=payload), config=_graph_config())
        _sync_graph_result(result)
        st.session_state.graph_error = None
    except Exception as exc:
        st.session_state.graph_error = f"Could not resume travel graph: {exc}"
        st.error(st.session_state.graph_error)
        return

    if (st.session_state.graph_state or {}).get("final_action") == "start_over":
        reset_app_state(location_map)

    st.rerun()


def _render_graph_interrupt(interrupt_payload: dict, location_map: dict[str, list[str]]) -> None:
    interrupt_type = interrupt_payload.get("type")
    resume_payload = None

    if interrupt_type == "shortlist_decision":
        resume_payload = render_shortlist_decision(interrupt_payload.get("shortlist_cards", []))
    elif interrupt_type == "half_baked_plan":
        resume_payload = render_half_baked_plan_input(interrupt_payload)
    elif interrupt_type == "followup_question":
        resume_payload = render_followup_question(interrupt_payload)
    elif interrupt_type == "custom_followup_input":
        resume_payload = render_custom_followup_input(interrupt_payload)
    elif interrupt_type == "followup_summary":
        resume_payload = render_followup_summary_review(interrupt_payload)
    elif interrupt_type == "final_brief":
        resume_payload = render_final_brief_actions(interrupt_payload)
    else:
        st.error(f"Unknown graph interrupt type: {interrupt_type}")

    if resume_payload is not None:
        _resume_graph(resume_payload, location_map)


def _render_graph_completion(location_map: dict[str, list[str]]) -> None:
    graph_state = st.session_state.graph_state or {}

    if graph_state.get("final_action") == "start_over":
        reset_app_state(location_map)
        st.rerun()

    if graph_state.get("itinerary_view_ready") and graph_state.get("final_itinerary_markdown"):
        st.success("Final itinerary is ready.")
        if st.button("Open itinerary view", key="open_itinerary_view", use_container_width=True):
            st.session_state.view = "itinerary"
            st.rerun()
        with st.expander("View itinerary validation"):
            st.json(graph_state.get("itinerary_validation", {}))
        return

    if graph_state.get("research_packet"):
        research_validation = graph_state.get("research_validation") or {}
        itinerary_validation = graph_state.get("itinerary_validation") or {}

        if research_validation.get("valid") is False:
            st.warning("Research finished, but itinerary planning did not start because research validation failed.")
            issues = research_validation.get("issues") or []
            if issues:
                st.write("Research validation issues:")
                for issue in issues:
                    st.write(f"- {issue}")
        elif itinerary_validation.get("valid") is False:
            st.warning("Itinerary planning ran, but markdown was not rendered because itinerary validation failed.")
            issues = itinerary_validation.get("issues") or []
            if issues:
                st.write("Itinerary validation issues:")
                for issue in issues:
                    st.write(f"- {issue}")
        elif research_validation.get("valid") is True:
            st.warning("Research is valid, but no final itinerary was produced. Restart this Streamlit run to rebuild the graph from the latest code.")
        else:
            st.success("Destination research packet is ready.")

        with st.expander("View research validation"):
            st.json(research_validation)
        if itinerary_validation:
            with st.expander("View itinerary validation"):
                st.json(itinerary_validation)
        with st.expander("View research packet"):
            st.json(graph_state["research_packet"])
        return

    if graph_state.get("information_curator_complete"):
        st.success("Information curator flow is complete. Research packet is being prepared.")
        return

    if graph_state.get("final_brief"):
        st.subheader("Final Trip Brief")
        st.markdown(graph_state["final_brief"])
        return

    st.write("Travel graph is complete.")
