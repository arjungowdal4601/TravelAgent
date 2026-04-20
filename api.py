from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from langgraph.types import Command
from pydantic import BaseModel, Field, model_validator

from main import travel_graph
from services import plan_artifacts


app = FastAPI(title="Travel Planner API", version="1.0.0")

PlanStatus = Literal["created", "waiting_for_review", "running", "completed", "failed"]
ReviewAction = Literal["approve", "reject", "modify"]
TripType = Literal["solo", "couple", "family", "group"]
BudgetMode = Literal["standard", "premium", "luxury", "custom"]

PLANS: dict[str, dict[str, Any]] = {}


class PlanCreateRequest(BaseModel):
    origin: str = Field(min_length=2)
    start_date: date
    end_date: date
    trip_type: TripType
    member_count: int = Field(ge=1)
    has_kids: bool = False
    has_seniors: bool = False
    budget_mode: BudgetMode = "standard"
    budget_value: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_dates(self) -> "PlanCreateRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self

    def to_graph_input(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "trip_days": (self.end_date - self.start_date).days + 1,
            "trip_type": self.trip_type,
            "member_count": self.member_count,
            "has_kids": self.has_kids,
            "has_seniors": self.has_seniors,
            "budget_mode": self.budget_mode,
            "budget_value": self.budget_value,
        }


class ReviewRequest(BaseModel):
    action: ReviewAction
    selected_index: int | None = Field(default=None, ge=0)
    answer: Any = None
    feedback: str | None = None


class PlanResponse(BaseModel):
    id: str
    status: PlanStatus
    stage: str
    draft: dict[str, Any]
    required_action: dict[str, Any] | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class FinalPlanResponse(BaseModel):
    id: str
    markdown: str
    structured_itinerary: dict[str, Any]
    artifact_paths: dict[str, str]


@app.post("/plan", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(request: PlanCreateRequest) -> PlanResponse:
    plan_id = str(uuid4())
    plan = {
        "id": plan_id,
        "thread_id": str(uuid4()),
        "status": "created",
        "stage": "created",
        "graph_state": {},
        "interrupt": None,
        "artifact_paths": {},
        "error": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    PLANS[plan_id] = plan
    _initialize_artifacts(plan)
    _run_graph(plan, request.to_graph_input())
    return _to_response(plan)


@app.get("/plan/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: str) -> PlanResponse:
    return _to_response(_get_plan_or_404(plan_id))


@app.post("/plan/{plan_id}/review", response_model=PlanResponse)
def review_plan(plan_id: str, request: ReviewRequest) -> PlanResponse:
    plan = _get_plan_or_404(plan_id)
    if plan["status"] != "waiting_for_review" or not isinstance(plan.get("interrupt"), dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This plan is not waiting for HITL feedback.",
        )

    resume_payloads = _review_to_resume_payloads(plan["interrupt"], request)
    for resume_payload in resume_payloads:
        _run_graph(plan, Command(resume=resume_payload))
        if plan["status"] != "waiting_for_review":
            break

    return _to_response(plan)


@app.get("/plan/{plan_id}/final", response_model=FinalPlanResponse)
def get_final_plan(plan_id: str) -> FinalPlanResponse:
    plan = _get_plan_or_404(plan_id)
    graph_state = plan.get("graph_state") or {}
    if not graph_state.get("itinerary_view_ready") or not graph_state.get("final_itinerary_markdown"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Final plan is only available after approval and itinerary completion.",
        )

    if not _final_artifacts_exist(plan):
        _write_artifacts(plan)
        _write_snapshot(plan)

    return FinalPlanResponse(
        id=plan_id,
        markdown=graph_state.get("final_itinerary_markdown") or "",
        structured_itinerary=graph_state.get("final_itinerary") or {},
        artifact_paths=plan.get("artifact_paths") or {},
    )


def _run_graph(plan: dict[str, Any], graph_input: Any) -> None:
    plan["status"] = "running"
    plan["updated_at"] = _now_iso()
    try:
        result = travel_graph.invoke(graph_input, config=_graph_config(plan))
        _sync_graph_state(plan, result)
    except HTTPException:
        raise
    except Exception as exc:
        plan["status"] = "failed"
        plan["stage"] = "failed"
        plan["error"] = f"{type(exc).__name__}: {exc}"
        plan["updated_at"] = _now_iso()
        _write_snapshot(plan)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=plan["error"]) from exc


def _sync_graph_state(plan: dict[str, Any], result: Any) -> None:
    graph_state = travel_graph.get_state(_graph_config(plan))
    plan["graph_state"] = dict(getattr(graph_state, "values", {}) or {})

    interrupts = _extract_interrupts(result)
    if interrupts:
        plan["interrupt"] = _interrupt_value(interrupts[0])
        plan["status"] = "waiting_for_review"
        plan["stage"] = _stage_from_interrupt(plan["interrupt"])
    else:
        plan["interrupt"] = None
        if plan["graph_state"].get("itinerary_view_ready") and plan["graph_state"].get("final_itinerary_markdown"):
            plan["status"] = "completed"
            plan["stage"] = "final_itinerary"
            plan["updated_at"] = _now_iso()
            _write_artifacts(plan)
        elif plan["graph_state"].get("final_action") == "start_over":
            plan["status"] = "completed"
            plan["stage"] = "start_over"
        else:
            plan["status"] = "completed"
            plan["stage"] = "completed"

    plan["updated_at"] = _now_iso()
    _write_snapshot(plan)


def _review_to_resume_payloads(interrupt_payload: dict[str, Any], request: ReviewRequest) -> list[dict[str, Any]]:
    interrupt_type = interrupt_payload.get("type")

    if interrupt_type == "shortlist_decision":
        if request.action == "approve":
            if request.selected_index is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="selected_index is required.")
            return [{"action": "select", "selected_index": request.selected_index}]

        if request.action in {"reject", "modify"}:
            payloads = [{"action": "reject"}]
            if _text(request.feedback):
                payloads.append({"user_hint": _text(request.feedback)})
            return payloads

    if interrupt_type == "half_baked_plan":
        hint = _text(request.feedback) or _text(request.answer)
        return [{"user_hint": hint}]

    if interrupt_type == "followup_question":
        answer = request.answer if request.answer is not None else _text(request.feedback)
        if answer in (None, ""):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="answer is required.")
        return [{"answer": answer}]

    if interrupt_type == "custom_followup_input":
        return [{"followup_custom_note": _text(request.feedback) or _text(request.answer)}]

    if interrupt_type in {"followup_summary", "followup_confirmation"}:
        correction = _text(request.feedback) or _text(request.answer)
        if request.action == "reject":
            return [{"action": "start_over", "followup_change_request": correction}]
        return [{"action": "continue", "followup_change_request": correction}]

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Unsupported review stage: {interrupt_type}",
    )


def _to_response(plan: dict[str, Any]) -> PlanResponse:
    return PlanResponse(
        id=plan["id"],
        status=plan["status"],
        stage=plan["stage"],
        draft=_draft_for_plan(plan),
        required_action=plan.get("interrupt"),
        artifact_paths=plan.get("artifact_paths") or {},
        error=plan.get("error"),
    )


def _draft_for_plan(plan: dict[str, Any]) -> dict[str, Any]:
    graph_state = plan.get("graph_state") or {}
    interrupt_payload = plan.get("interrupt")
    if isinstance(interrupt_payload, dict):
        return {"stage": _stage_from_interrupt(interrupt_payload), "interrupt": interrupt_payload}

    if graph_state.get("final_itinerary_markdown"):
        return {
            "stage": "final_itinerary",
            "final_itinerary_markdown": graph_state.get("final_itinerary_markdown"),
            "itinerary_validation": graph_state.get("itinerary_validation") or {},
        }

    return {
        "stage": plan.get("stage", "unknown"),
        "research_validation": graph_state.get("research_validation") or {},
        "itinerary_validation": graph_state.get("itinerary_validation") or {},
    }


def _write_artifacts(plan: dict[str, Any]) -> None:
    plan["artifact_paths"] = plan_artifacts.write_plan_artifacts(
        plan["id"],
        plan.get("graph_state") or {},
        travel_graph,
    )


def _initialize_artifacts(plan: dict[str, Any]) -> None:
    plan["artifact_paths"] = plan_artifacts.initialize_plan_artifacts(
        plan["id"],
        plan,
        travel_graph,
    )


def _write_snapshot(plan: dict[str, Any]) -> None:
    plan["artifact_paths"] = plan_artifacts.write_plan_snapshot(
        plan["id"],
        plan,
        _draft_for_plan(plan),
    )


def _final_artifacts_exist(plan: dict[str, Any]) -> bool:
    artifact_paths = plan.get("artifact_paths") or {}
    final_markdown = artifact_paths.get("final_markdown")
    structured_itinerary = artifact_paths.get("structured_itinerary")
    return bool(
        final_markdown
        and structured_itinerary
        and Path(final_markdown).exists()
        and Path(structured_itinerary).exists()
    )


def _get_plan_or_404(plan_id: str) -> dict[str, Any]:
    plan = PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    return plan


def _graph_config(plan: dict[str, Any]) -> dict[str, Any]:
    return {"configurable": {"thread_id": plan["thread_id"]}}


def _extract_interrupts(result: Any) -> list[Any]:
    if isinstance(result, dict):
        return list(result.get("__interrupt__", []) or [])
    return []


def _interrupt_value(interrupt_item: Any) -> dict[str, Any]:
    if isinstance(interrupt_item, dict) and isinstance(interrupt_item.get("value"), dict):
        return interrupt_item["value"]
    value = getattr(interrupt_item, "value", interrupt_item)
    if isinstance(value, dict):
        return value
    return {"type": "unknown", "payload": value}


def _stage_from_interrupt(interrupt_payload: dict[str, Any] | None) -> str:
    if not isinstance(interrupt_payload, dict):
        return "completed"
    return str(interrupt_payload.get("type") or "waiting_for_review")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
