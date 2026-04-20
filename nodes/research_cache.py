import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


CACHE_TTLS_SECONDS = {
    "coverage": 30 * 24 * 60 * 60,
    "weather": 6 * 60 * 60,
    "documents": 60 * 60,
    "packing": 7 * 24 * 60 * 60,
    "money": 7 * 24 * 60 * 60,
    "local_practicals": 7 * 24 * 60 * 60,
    "safety": 7 * 24 * 60 * 60,
    "connectivity": 7 * 24 * 60 * 60,
    "local_transport": 7 * 24 * 60 * 60,
    "medical": 7 * 24 * 60 * 60,
    "cultural": 7 * 24 * 60 * 60,
    "adventure": 7 * 24 * 60 * 60,
}


def make_cache_key(node_type: str, payload: dict[str, Any]) -> str:
    """Build a stable cache key for a research node and its compact inputs."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{node_type}_{digest}"


def _cache_dir() -> Path:
    return Path(os.getenv("TRAVEL_RESEARCH_CACHE_DIR", ".travel_research_cache"))


def _cache_path(cache_key: str) -> Path:
    safe_name = "".join(char for char in cache_key if char.isalnum() or char in {"_", "-"})
    return _cache_dir() / f"{safe_name}.json"


def get_cached_payload(node_type: str, cache_key: str) -> dict[str, Any] | None:
    ttl = CACHE_TTLS_SECONDS.get(node_type)
    if ttl is None:
        return None

    path = _cache_path(cache_key)
    if not path.exists():
        return None

    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    created_at = cached.get("created_at")
    if not isinstance(created_at, (int, float)):
        return None

    if time.time() - created_at > ttl:
        return None

    payload = cached.get("payload")
    return payload if isinstance(payload, dict) else None


def set_cached_payload(node_type: str, cache_key: str, payload: dict[str, Any]) -> None:
    if node_type not in CACHE_TTLS_SECONDS:
        return

    path = _cache_path(cache_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "node_type": node_type,
                    "created_at": time.time(),
                    "payload": payload,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        return
