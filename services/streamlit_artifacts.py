from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services import plan_artifacts


def streamlit_plan_id(thread_id: str) -> str:
    return f"streamlit-{thread_id}"


def initialize_streamlit_artifacts(thread_id: str, graph: Any, created_at: str | None = None) -> dict[str, str]:
    plan = build_streamlit_plan(
        thread_id=thread_id,
        step="ask_origin",
        graph_state={},
        interrupt=None,
        error=None,
        created_at=created_at,
    )
    return plan_artifacts.initialize_plan_artifacts(plan["id"], plan, graph)


def write_streamlit_snapshot(
    thread_id: str,
    step: str,
    graph_state: dict[str, Any] | None,
    interrupt: dict[str, Any] | None,
    error: str | None,
    trip_data: dict[str, Any] | None,
    created_at: str | None,
) -> dict[str, str]:
    plan = build_streamlit_plan(
        thread_id=thread_id,
        step=step,
        graph_state=graph_state or {},
        interrupt=interrupt,
        error=error,
        created_at=created_at,
    )
    return plan_artifacts.write_plan_snapshot(
        plan["id"],
        plan,
        build_streamlit_draft(plan, trip_data or {}, step),
    )


def write_streamlit_final_artifacts(thread_id: str, graph_state: dict[str, Any], graph: Any) -> dict[str, str]:
    return plan_artifacts.write_plan_artifacts(streamlit_plan_id(thread_id), graph_state, graph)


def build_streamlit_plan(
    thread_id: str,
    step: str,
    graph_state: dict[str, Any],
    interrupt: dict[str, Any] | None,
    error: str | None,
    created_at: str | None,
) -> dict[str, Any]:
    status, stage = streamlit_status_stage(step, graph_state, interrupt, error)
    now = _now_iso()
    return {
        "id": streamlit_plan_id(thread_id),
        "thread_id": thread_id,
        "status": status,
        "stage": stage,
        "graph_state": graph_state,
        "interrupt": interrupt,
        "error": error,
        "created_at": created_at or now,
        "updated_at": now,
    }


def build_streamlit_draft(plan: dict[str, Any], trip_data: dict[str, Any], step: str) -> dict[str, Any]:
    interrupt = plan.get("interrupt")
    if isinstance(interrupt, dict):
        return {"stage": plan["stage"], "interrupt": interrupt}

    graph_state = plan.get("graph_state") or {}
    if graph_state.get("final_itinerary_markdown"):
        return {
            "stage": "final_itinerary",
            "final_itinerary_markdown": graph_state.get("final_itinerary_markdown"),
            "itinerary_validation": graph_state.get("itinerary_validation") or {},
        }

    return {
        "stage": plan.get("stage", "input_collection"),
        "current_step": step,
        "trip_data": trip_data,
        "research_validation": graph_state.get("research_validation") or {},
        "itinerary_validation": graph_state.get("itinerary_validation") or {},
    }


def streamlit_status_stage(
    step: str,
    graph_state: dict[str, Any],
    interrupt: dict[str, Any] | None,
    error: str | None,
) -> tuple[str, str]:
    if error:
        return "failed", "failed"
    if isinstance(interrupt, dict):
        return "waiting_for_review", str(interrupt.get("type") or "waiting_for_review")
    if graph_state.get("itinerary_view_ready") and graph_state.get("final_itinerary_markdown"):
        return "completed", "final_itinerary"
    if graph_state.get("final_action") == "start_over":
        return "completed", "start_over"
    if graph_state.get("research_packet"):
        return "running", "research_packet"
    if graph_state.get("information_curator_complete"):
        return "running", "information_curator_complete"
    if graph_state:
        return "running", "graph_running"
    if step == "done":
        return "running", "starting_graph"
    return "created", "input_collection"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
