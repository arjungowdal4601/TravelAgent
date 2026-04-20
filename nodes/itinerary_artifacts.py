from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(".travel_itinerary_artifacts")


def write_itinerary_artifact(run_id: str, name: str, payload: Any) -> dict[str, str]:
    """Write a JSON or text itinerary artifact and return a compact reference."""
    artifact_dir = (ARTIFACT_ROOT / run_id).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = (artifact_dir / name).resolve()

    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
        artifact_format = "markdown" if path.suffix.lower() == ".md" else "text"
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        artifact_format = "json"

    return {
        "run_id": run_id,
        "path": str(path),
        "format": artifact_format,
    }


def read_itinerary_artifact(ref: dict[str, Any] | str | None) -> Any:
    """Read an itinerary artifact reference."""
    if isinstance(ref, dict):
        path_value = ref.get("path")
        artifact_format = ref.get("format")
    else:
        path_value = ref
        artifact_format = None

    if not path_value:
        return None

    path = Path(str(path_value))
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    if artifact_format == "json" or path.suffix.lower() == ".json":
        return json.loads(text)
    return text
