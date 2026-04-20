LIVE_TRIP_CONTEXT_SYSTEM_PROMPT = """
You are the live-context node for a travel itinerary planner.

Return only valid JSON. Use web search surgically for current or practical facts that improve final itinerary quality:
- cost context
- opening or timing context
- restaurant or meal context
- origin-to-destination and return transport context
- stay area and hotel/stay budget context
- local transfer, auto, taxi, or day-cab context

Do not rebuild the full research packet. Do not produce a travel essay. Do not fabricate exact prices.
Use concise ranges when exact sourced prices are not available.
Do not claim live ticket availability or hotel availability.
""".strip()


LIVE_TRIP_CONTEXT_HUMAN_PROMPT = """
Planner input:
{itinerary_input}

Return one JSON object with this shape:
{{
  "origin_destination_transport_context": {{
    "recommended_mode": "flight|train|bus|self-drive|cab|mixed",
    "route": "short origin to destination route",
    "pickup_point": "origin airport/station/bus stand/city area if relevant",
    "dropoff_point": "destination airport/station/bus stand/base area if relevant",
    "time_label": "short duration/range",
    "cost_label": "short amount/range",
    "source_status": "exact|estimated|derived",
    "note": "one practical note",
    "source_ref": {{"title": "source title", "url": "https://..."}}
  }},
  "return_transport_context": {{
    "recommended_mode": "flight|train|bus|self-drive|cab|mixed",
    "route": "short destination to origin route",
    "pickup_point": "destination departure point",
    "dropoff_point": "origin arrival point",
    "time_label": "short duration/range",
    "cost_label": "short amount/range",
    "source_status": "exact|estimated|derived",
    "note": "one practical note",
    "source_ref": {{"title": "source title", "url": "https://..."}}
  }},
  "stay_cost_context": {{
    "base_area": "best stay area, not a specific hotel unless sourced",
    "stay_type": "hotel/homestay/resort type assumption",
    "room_basis": "room assumption, such as 1 room or 2 rooms",
    "nightly_cost_label": "short amount/range per night",
    "source_status": "estimated|derived|exact",
    "note": "one practical stay note",
    "source_ref": {{"title": "source title", "url": "https://..."}}
  }},
  "local_fare_context": [
    {{
      "scope": "short auto/cab/day-cab/inter-area transfer",
      "cost_label": "short amount/range",
      "when_to_use": "short usage guidance",
      "source_status": "exact|estimated|derived",
      "source_ref": {{"title": "source title", "url": "https://..."}}
    }}
  ],
  "attraction_cost_context": [
    {{
      "name": "place or activity",
      "cost_label": "short amount or range",
      "source_status": "exact|estimated|derived",
      "source_ref": {{"title": "source title", "url": "https://..."}}
    }}
  ],
  "meal_cost_context": {{
    "breakfast": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "lunch": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "dinner": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}}
  }},
  "local_transfer_cost_context": [
    {{
      "scope": "local taxi / cab / auto / transfer",
      "cost_label": "short amount or range",
      "source_status": "exact|estimated|derived",
      "source_ref": {{"title": "source title", "url": "https://..."}}
    }}
  ],
  "opening_time_context": [
    {{
      "name": "place",
      "timing": "short timing guidance",
      "source_ref": {{"title": "source title", "url": "https://..."}}
    }}
  ],
  "restaurant_context": [
    {{
      "name": "restaurant or food area",
      "area": "area",
      "meal": "breakfast|lunch|dinner|any",
      "why": "short reason",
      "source_ref": {{"title": "source title", "url": "https://..."}}
    }}
  ],
  "fallback_estimate_policy": "one short sentence",
  "source_refs": [
    {{"title": "source title", "url": "https://...", "ref_type": "cost|timing|restaurant|transfer|stay|transport"}}
  ]
}}
""".strip()


DAY_PLANNING_SYSTEM_PROMPT = """
You are the sequential day planner for a final travel itinerary.

Return only valid JSON for one day. Keep the day short, timed, practical, and cost-aware.
Use the validated research input and live context. Do not write long descriptions.
Do not repeat generic trip-level advice. Do not output "Not priced".
Use "hotel/base area" for stay references unless a sourced specific hotel exists.
Arrival days must include origin-to-destination travel and check-in.
Departure days must include checkout and return travel.
""".strip()


DAY_PLANNING_HUMAN_PROMPT = """
Day input:
{day_input}

Return one JSON object with this shape:
{{
  "day_id": "D0",
  "date": "YYYY-MM-DD",
  "title": "short day title",
  "day_type": "arrival_light|sightseeing|departure_light|arrival_departure_light",
  "base_area": "area",
  "schedule": [
    {{
      "time": "08:00",
      "type": "breakfast|visit|lunch|transfer|activity|dinner|buffer",
      "label": "short action",
      "area": "area",
      "cost": "short amount/range if relevant"
    }}
  ],
  "meals": [
    {{"meal": "breakfast", "time": "08:00", "label": "Breakfast near hotel/base area", "cost": "short amount/range"}}
  ],
  "estimated_spend": {{
    "breakfast": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "lunch": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "dinner": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "local_travel": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "entry_activity": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "misc_buffer": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}},
    "total": {{"label": "amount/range", "source_status": "estimated", "source_ref": null}}
  }},
  "important_note": "one short note only when truly useful",
  "source_refs": [
    {{"title": "source title", "url": "https://...", "ref_type": "cost|timing|restaurant|transfer|research"}}
  ]
}}
""".strip()
