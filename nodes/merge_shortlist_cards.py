def merge_shortlist_cards(state: dict) -> dict:
    """Merge the explained shortlist items into 4 clean comparison card objects."""
    explained_destinations = state.get("explained_shortlisted_destinations", [])

    def clean_list(values: list, limit: int) -> list[str]:
        cleaned = []
        for value in values or []:
            if not isinstance(value, str):
                continue
            item = value.strip()
            if item:
                cleaned.append(item)
        return cleaned[:limit]

    def clean_text(value: str, fallback: str = "") -> str:
        if not isinstance(value, str):
            return fallback
        return value.strip() or fallback

    shortlist_cards = []
    for item in explained_destinations:
        shortlist_cards.append(
            {
                "state_or_region": clean_text(item.get("state_or_region", "")),
                "places_covered": clean_list(item.get("places_covered", []), 4),
                "highlights": clean_list(item.get("highlights", []), 5),
                "best_for": clean_text(item.get("best_for", "")),
                "duration_fit": clean_text(item.get("duration_fit", "")),
                "why_it_fits": clean_text(item.get("why_it_fits", "")),
                "estimated_price_range": clean_text(item.get("estimated_price_range", "Not specified")),
            }
        )

    updated_state = dict(state)
    updated_state["shortlist_cards"] = shortlist_cards[:4]
    return updated_state
