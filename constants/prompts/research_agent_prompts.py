DESTINATION_RESEARCH_SYSTEM_PROMPT = """
You are a compact destination research agent.

Use web search for live destination and travel-practical information. Return only valid JSON.
Focus on coherent destination intelligence, not a long guidebook essay.
Keep every field concise and structured.
""".strip()


DESTINATION_RESEARCH_HUMAN_PROMPT = """
Research input:
{research_input}

Return one compact JSON object:
{{
  "destination_summary": "2-3 concise sentences",
  "duration_fit": "what can realistically be covered in the trip length",
  "area_clusters": [
    {{"name": "area/cluster", "places": ["place"], "notes": "short planning note"}}
  ],
  "must_do_places": [
    {{"name": "place", "area": "area", "why": "short reason", "time_need": "rough time"}}
  ],
  "optional_places": [
    {{"name": "place", "area": "area", "include_if": "condition", "time_need": "rough time"}}
  ],
  "niche_or_extra_places": [
    {{"name": "place", "area": "area", "include_if": "condition"}}
  ],
  "best_experiences": ["short idea"],
  "best_food": ["short food idea"],
  "best_activities": ["short activity/adventure idea"],
  "constraints": ["key planning constraint"],
  "warnings": ["important warning only"],
  "assumptions": ["explicit assumption"],
  "citations": [
    {{"title": "source title", "url": "https://..."}}
  ]
}}
""".strip()


PRACTICAL_TRAVEL_INFO_SYSTEM_PROMPT = """
You are a practical travel enrichment node.

Use web search where needed for current or destination-specific travel facts.
Return only valid JSON. Keep output compact and avoid repeated generic advice.
Include practical sections only when they are relevant to the destination, season, group, or activities.
""".strip()


PRACTICAL_TRAVEL_INFO_HUMAN_PROMPT = """
Research input:
{research_input}

Destination research:
{destination_research}

Return one compact JSON object:
{{
  "weather_temperature": {{
    "summary": "short weather/temperature context for the dates or season",
    "facts": ["specific relevant fact"],
    "warnings": ["weather warning only if relevant"]
  }},
  "carry": ["what to carry, compact"],
  "practical_facts": ["on-ground travel fact"],
  "local_transport": ["local transfer / movement note"],
  "money": ["cash/payment note if relevant"],
  "documents": ["document/permit/ID note if relevant"],
  "safety": ["safety/health/access note if relevant"],
  "connectivity": ["network/internet note if relevant"],
  "culture": ["etiquette/dress note if relevant"],
  "warnings": ["important practical warning"],
  "citations": [
    {{"title": "source title", "url": "https://..."}}
  ]
}}
""".strip()

