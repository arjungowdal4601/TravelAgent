from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "output"


def initialize_plan_artifacts(plan_id: str, plan_metadata: dict[str, Any], graph: Any) -> dict[str, str]:
    """Create the session output folder and workflow graph files immediately."""
    output_dir = _session_dir(plan_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    graph_png_error = _write_workflow_graph_files(output_dir, graph)
    artifact_paths = _artifact_paths(output_dir)

    metadata = {
        "plan_id": plan_id,
        "status": plan_metadata.get("status", "created"),
        "stage": plan_metadata.get("stage", "created"),
        "created_at": plan_metadata.get("created_at") or _now_iso(),
        "updated_at": plan_metadata.get("updated_at") or _now_iso(),
        "artifacts": artifact_paths,
    }
    if graph_png_error:
        metadata["workflow_graph_png_error"] = graph_png_error

    _write_json(output_dir / "metadata.json", metadata)
    _write_json(output_dir / "status.json", _status_payload(plan_metadata, artifact_paths))
    _write_json(output_dir / "draft.json", {})
    _write_json(output_dir / "graph_state.json", {})
    metadata["artifacts"] = _artifact_paths(output_dir)
    _write_json(output_dir / "metadata.json", metadata)
    return _artifact_paths(output_dir)


def write_plan_snapshot(plan_id: str, plan: dict[str, Any], draft: dict[str, Any] | None = None) -> dict[str, str]:
    """Persist current API session state while the workflow is still active."""
    output_dir = _session_dir(plan_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths = _artifact_paths(output_dir)
    _write_json(output_dir / "status.json", _status_payload(plan, artifact_paths))
    _write_json(output_dir / "draft.json", draft or {})
    _write_json(output_dir / "graph_state.json", plan.get("graph_state") or {})

    interrupt_path = output_dir / "interrupt.json"
    if plan.get("interrupt") is not None:
        _write_json(interrupt_path, plan.get("interrupt"))
    elif interrupt_path.exists():
        interrupt_path.unlink()

    metadata = _read_json(output_dir / "metadata.json") or {}
    metadata.update(
        {
            "plan_id": plan_id,
            "status": plan.get("status", metadata.get("status", "created")),
            "stage": plan.get("stage", metadata.get("stage", "created")),
            "created_at": plan.get("created_at") or metadata.get("created_at") or _now_iso(),
            "updated_at": plan.get("updated_at") or _now_iso(),
            "artifacts": _artifact_paths(output_dir),
        }
    )
    _write_json(output_dir / "metadata.json", metadata)
    return _artifact_paths(output_dir)


def write_plan_artifacts(plan_id: str, graph_state: dict[str, Any], graph: Any) -> dict[str, str]:
    """Persist final plan markdown, structured JSON, and workflow graph files."""
    output_dir = _session_dir(plan_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown = str(graph_state.get("final_itinerary_markdown") or "").strip()
    if not markdown:
        raise ValueError("final_itinerary_markdown is required before writing artifacts.")

    (output_dir / "final.md").write_text(markdown, encoding="utf-8")
    _write_json(output_dir / "final_itinerary.json", graph_state.get("final_itinerary") or {})

    graph_png_error = _write_workflow_graph_files(output_dir, graph)
    artifact_paths = _artifact_paths(output_dir)

    metadata = _read_json(output_dir / "metadata.json") or {}
    metadata.update(
        {
            "plan_id": plan_id,
            "status": "completed",
            "stage": "final_itinerary",
            "created_at": metadata.get("created_at") or _now_iso(),
            "updated_at": _now_iso(),
            "artifacts": artifact_paths,
        }
    )
    if graph_png_error:
        metadata["workflow_graph_png_error"] = graph_png_error

    _write_json(output_dir / "metadata.json", metadata)
    return artifact_paths


def _write_workflow_graph_files(output_dir: Path, graph: Any) -> str:
    graph_png_error = ""
    graph_obj = graph.get_graph(xray=True)
    (output_dir / "workflow_graph.mmd").write_text(graph_obj.draw_mermaid(), encoding="utf-8")
    try:
        (output_dir / "workflow_graph.png").write_bytes(graph_obj.draw_mermaid_png())
    except Exception as exc:  # pragma: no cover - depends on external Mermaid renderer availability.
        graph_png_error = f"{type(exc).__name__}: {exc}"
    return graph_png_error


def _artifact_paths(output_dir: Path) -> dict[str, str]:
    candidates = {
        "output_dir": output_dir,
        "metadata": output_dir / "metadata.json",
        "status": output_dir / "status.json",
        "draft": output_dir / "draft.json",
        "graph_state": output_dir / "graph_state.json",
        "interrupt": output_dir / "interrupt.json",
        "final_markdown": output_dir / "final.md",
        "structured_itinerary": output_dir / "final_itinerary.json",
        "workflow_graph_mermaid": output_dir / "workflow_graph.mmd",
        "workflow_graph_png": output_dir / "workflow_graph.png",
    }
    return {
        key: str(path.resolve())
        for key, path in candidates.items()
        if key == "output_dir" or path.exists()
    }


def _status_payload(plan: dict[str, Any], artifact_paths: dict[str, str]) -> dict[str, Any]:
    return {
        "plan_id": plan.get("id"),
        "status": plan.get("status"),
        "stage": plan.get("stage"),
        "error": plan.get("error"),
        "created_at": plan.get("created_at"),
        "updated_at": plan.get("updated_at"),
        "artifact_paths": artifact_paths,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _session_dir(plan_id: str) -> Path:
    safe_plan_id = "".join(ch for ch in plan_id if ch.isalnum() or ch in {"-", "_"})
    if not safe_plan_id:
        raise ValueError("plan_id must contain at least one safe filename character.")
    return OUTPUT_ROOT / safe_plan_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
