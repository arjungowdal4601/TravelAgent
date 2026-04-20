import json
from pathlib import Path

import streamlit as st


def load_location_map(project_root: Path) -> dict[str, list[str]]:
    """Load and validate location data from the JSON source file."""
    json_path = project_root / "constants" / "india_locations.json"

    try:
        raw_data = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st.error("Location data file is missing. Please add `constants/india_locations.json`.")
        st.stop()
    except json.JSONDecodeError as exc:
        st.error(f"Location data is malformed JSON: {exc}")
        st.stop()

    if not isinstance(raw_data, list):
        st.error("Location data must be a JSON array of objects.")
        st.stop()

    location_map: dict[str, list[str]] = {}

    for entry in raw_data:
        if not isinstance(entry, dict):
            continue

        state = entry.get("state")
        locations = entry.get("locations")

        if not isinstance(state, str) or not state.strip():
            continue
        if not isinstance(locations, list):
            continue

        cleaned_locations = []
        seen = set()

        for location in locations:
            if not isinstance(location, str):
                continue
            normalized_location = location.strip()
            if not normalized_location or normalized_location in seen:
                continue
            cleaned_locations.append(normalized_location)
            seen.add(normalized_location)

        if cleaned_locations:
            location_map[state.strip()] = cleaned_locations

    if not location_map:
        st.error("Location data is empty or invalid after validation.")
        st.stop()

    return dict(sorted(location_map.items()))
