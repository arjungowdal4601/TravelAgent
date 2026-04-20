def _clean_list(values, limit: int) -> list[str]:
    """Keep only non-empty strings, trimmed and size-limited."""
    cleaned: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if item:
            cleaned.append(item)
    return cleaned[:limit]


def _clean_text(value, fallback: str = "") -> str:
    """Normalize possibly-missing text values to compact strings."""
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip()
    return cleaned or fallback


def _derive_title(item: dict, state_or_region: str) -> str:
    """Build a deterministic card title when the model did not provide one."""
    explicit_title = _clean_text(item.get("card_title", ""))
    if explicit_title:
        return explicit_title

    best_for = _clean_text(item.get("best_for", ""))
    if best_for:
        return f"{state_or_region} - {best_for}"

    return state_or_region


def _derive_trip_feel(item: dict) -> str:
    """Create a short trip feel fallback without losing readability."""
    explicit_feel = _clean_text(item.get("trip_feel", ""))
    if explicit_feel:
        return explicit_feel

    why_it_fits = _clean_text(item.get("why_it_fits", ""))
    if why_it_fits:
        return why_it_fits

    return "Balanced travel experience"


def _derive_pace(item: dict) -> str:
    """Map model pace to supported values with a safe default."""
    pace = _clean_text(item.get("pace", "")).lower()
    if pace in {"relaxed", "balanced", "fast-paced"}:
        return pace
    return "balanced"


def build_shortlist_cards(state: dict) -> dict:
    """Normalize shortlist output into exactly 4 UI-safe comparison cards."""
    shortlisted_destinations = state.get("shortlisted_destinations", [])
    if len(shortlisted_destinations) != 4:
        raise ValueError("Expected exactly 4 shortlisted destinations before card build.")

    shortlist_cards = []
    for item in shortlisted_destinations:
        state_or_region = _clean_text(item.get("state_or_region", ""), "Destination")
        card = {
            "card_title": _derive_title(item, state_or_region),
            "state_or_region": state_or_region,
            "trip_feel": _derive_trip_feel(item),
            "places_covered": _clean_list(item.get("places_covered", []), 4),
            "highlights": _clean_list(item.get("highlights", []), 5),
            "best_for": _clean_text(item.get("best_for", "")),
            "pace": _derive_pace(item),
            "duration_fit": _clean_text(item.get("duration_fit", "")),
            "why_it_fits": _clean_text(item.get("why_it_fits", "")),
            "estimated_price_range": _clean_text(
                item.get("estimated_price_range", "Not specified"),
                "Not specified",
            ),
        }
        shortlist_cards.append(card)

    updated_state = dict(state)
    updated_state["shortlist_cards"] = shortlist_cards[:4]
    # Backward-compatible mirror for older consumers that still read this key.
    updated_state["explained_shortlisted_destinations"] = shortlist_cards[:4]
    return updated_state
