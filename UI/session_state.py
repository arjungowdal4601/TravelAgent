from datetime import date, timedelta
from uuid import uuid4

import streamlit as st


ORIGIN_STATE_PLACEHOLDER = "Select state"
ORIGIN_CITY_PLACEHOLDER = "Select city"


STEP_PROMPTS = {
    "ask_origin": "Hi! Let's start your trip. Which Indian state and city or district are you traveling from?",
    "ask_dates": "What is your travel date range? Please select the start and end date together.",
    "ask_trip_type": "What kind of trip is this?",
    "ask_member_count": "How many members are traveling?",
    "ask_special_members": "Are any seniors or kids part of this trip?",
    "ask_budget_mode": "What budget preference would you like to use?",
    "ask_budget_value": "What custom budget amount should I note down?",
}


def _default_trip_data() -> dict:
    return {
        "origin_state": None,
        "origin_city": None,
        "origin": None,
        "start_date": None,
        "end_date": None,
        "trip_type": None,
        "member_count": None,
        "has_seniors": None,
        "has_kids": None,
        "budget_mode": None,
        "budget_value": None,
    }


def init_state(location_map: dict[str, list[str]]) -> None:
    """Initialize session state for chat messages, flow step, and collected data."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "step" not in st.session_state:
        st.session_state.step = "ask_origin"

    if "prompted_steps" not in st.session_state:
        st.session_state.prompted_steps = set()

    if "trip_data" not in st.session_state:
        st.session_state.trip_data = _default_trip_data()

    if "origin_state_input" not in st.session_state:
        st.session_state.origin_state_input = ORIGIN_STATE_PLACEHOLDER

    if "origin_city_input" not in st.session_state:
        st.session_state.origin_city_input = ORIGIN_CITY_PLACEHOLDER

    if "date_range_input" not in st.session_state:
        st.session_state.date_range_input = (date.today(), date.today() + timedelta(days=1))

    if "budget_slider_value" not in st.session_state:
        st.session_state.budget_slider_value = 50000

    if "summary_added" not in st.session_state:
        st.session_state.summary_added = False

    if "graph_state" not in st.session_state:
        st.session_state.graph_state = None

    if "graph_interrupt" not in st.session_state:
        st.session_state.graph_interrupt = None

    if "graph_thread_id" not in st.session_state:
        st.session_state.graph_thread_id = str(uuid4())

    if "graph_error" not in st.session_state:
        st.session_state.graph_error = None

    if "graph_step_timings" not in st.session_state:
        st.session_state.graph_step_timings = []

    if "graph_total_seconds" not in st.session_state:
        st.session_state.graph_total_seconds = None

    if "graph_current_status" not in st.session_state:
        st.session_state.graph_current_status = ""

    if "graph_artifact_paths" not in st.session_state:
        st.session_state.graph_artifact_paths = {}

    if "graph_artifacts_initialized_for" not in st.session_state:
        st.session_state.graph_artifacts_initialized_for = None

    if "graph_artifact_created_at" not in st.session_state:
        st.session_state.graph_artifact_created_at = None

    if "graph_final_artifacts_written" not in st.session_state:
        st.session_state.graph_final_artifacts_written = False

    if "graph_artifact_error" not in st.session_state:
        st.session_state.graph_artifact_error = None

    if "selected_destination" not in st.session_state:
        st.session_state.selected_destination = None

    if "view" not in st.session_state:
        st.session_state.view = "chat"


def add_message(role: str, content: str) -> None:
    st.session_state.messages.append({"role": role, "content": content})


def ensure_ai_prompt(step: str) -> None:
    """Add each assistant prompt only once."""
    if step in STEP_PROMPTS and step not in st.session_state.prompted_steps:
        add_message("ai", STEP_PROMPTS[step])
        st.session_state.prompted_steps.add(step)


def build_summary() -> str:
    data = st.session_state.trip_data
    lines = [
        "Here is what I understood:",
        f"Origin: {data['origin']}",
        f"Dates: {data['start_date']} to {data['end_date']}",
        f"Trip Type: {data['trip_type'].title()}",
        f"Members: {1 if data['trip_type'] == 'solo' else data['member_count']}",
    ]

    if data["trip_type"] in {"family", "group"}:
        lines.append(f"Seniors Present: {'Yes' if data['has_seniors'] else 'No'}")
        lines.append(f"Kids Present: {'Yes' if data['has_kids'] else 'No'}")

    lines.append(f"Budget Preference: {data['budget_mode'].title()}")

    if data["budget_mode"] == "custom":
        lines.append(f"Custom Budget Amount: {data['budget_value']}")

    return "\n".join(lines)


def reset_graph_results() -> None:
    """Clear old graph output before a new shortlist run."""
    st.session_state.graph_state = None
    st.session_state.graph_interrupt = None
    st.session_state.graph_error = None
    st.session_state.selected_destination = None
    st.session_state.graph_thread_id = str(uuid4())
    st.session_state.view = "chat"
    st.session_state.graph_step_timings = []
    st.session_state.graph_total_seconds = None
    st.session_state.graph_current_status = ""
    st.session_state.graph_artifact_paths = {}
    st.session_state.graph_artifacts_initialized_for = None
    st.session_state.graph_artifact_created_at = None
    st.session_state.graph_final_artifacts_written = False
    st.session_state.graph_artifact_error = None


def reset_app_state(location_map: dict[str, list[str]]) -> None:
    """Reset the whole app back to the first basic input step."""
    st.session_state.messages = []
    st.session_state.step = "ask_origin"
    st.session_state.prompted_steps = set()
    st.session_state.trip_data = _default_trip_data()

    st.session_state.origin_state_input = ORIGIN_STATE_PLACEHOLDER
    st.session_state.origin_city_input = ORIGIN_CITY_PLACEHOLDER
    st.session_state.date_range_input = (date.today(), date.today() + timedelta(days=1))
    st.session_state.budget_slider_value = 50000
    st.session_state.summary_added = False
    st.session_state.view = "chat"

    reset_graph_results()

    for key in list(st.session_state.keys()):
        if key.startswith("followup_answer_input_"):
            del st.session_state[key]
        if key in {
            "half_baked_plan_input",
            "followup_custom_note_input",
            "followup_change_request_input",
        }:
            del st.session_state[key]


def build_graph_input() -> dict:
    """Convert collected app input into the graph state format."""
    data = st.session_state.trip_data
    start_date = date.fromisoformat(data["start_date"])
    end_date = date.fromisoformat(data["end_date"])
    trip_days = (end_date - start_date).days + 1

    return {
        "origin": data["origin"],
        "start_date": data["start_date"],
        "end_date": data["end_date"],
        "trip_days": trip_days,
        "trip_type": data["trip_type"],
        "member_count": data["member_count"],
        "has_kids": bool(data["has_kids"]),
        "has_seniors": bool(data["has_seniors"]),
        "budget_mode": data["budget_mode"],
        "budget_value": data["budget_value"],
    }


def is_complete_origin_selection(state: str | None, city: str | None) -> bool:
    return bool(
        state
        and city
        and state != ORIGIN_STATE_PLACEHOLDER
        and city != ORIGIN_CITY_PLACEHOLDER
    )


def finish_flow() -> None:
    st.session_state.step = "done"
    reset_graph_results()
    if not st.session_state.summary_added:
        add_message("ai", build_summary())
        st.session_state.summary_added = True
