import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from llm import get_research_llm
from nodes.research_cache import get_cached_payload, make_cache_key, set_cached_payload
from services.llm_response_parsing import extract_text_content, load_json_payload


RESEARCH_REASONING = {"effort": "medium"}
RESEARCH_TOOLS = [{"type": "web_search"}]

DESTINATION_KNOWLEDGE_FIELDS = {
    "destination_overview",
    "key_place_clusters",
    "how_to_reach",
    "movement_within_destination",
    "signature_experiences",
    "local_food_highlights",
    "planning_cautions",
    "pace_signal",
    "citations",
}

TRAVEL_ESSENTIALS_LIST_FIELDS = [
    "documents_and_permissions",
    "packing_and_carry",
    "local_dos",
    "local_donts",
    "safety_and_health",
    "money_and_payments",
    "connectivity_and_access",
    "special_trip_notes",
]


def run_research_json(
    *,
    node_type: str,
    system_prompt: str,
    human_prompt: str,
    variables: dict[str, Any],
    cache_payload: dict[str, Any],
) -> dict[str, Any]:
    cache_key = make_cache_key(node_type, cache_payload)
    cached = get_cached_payload(node_type, cache_key)
    if cached is not None:
        return cached

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", human_prompt),
        ]
    )
    model = get_research_llm().bind_tools(
        RESEARCH_TOOLS,
        tool_choice="web_search",
        reasoning=RESEARCH_REASONING,
    )
    response = (prompt | model).invoke(variables)
    text = extract_text_content(response.content)
    payload = load_json_payload(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{node_type} must return one JSON object.")

    payload["citations"] = merge_citations(
        extract_response_citations(response.content),
        payload.get("citations") or [],
        payload.get("source_refs") or [],
    )
    set_cached_payload(node_type, cache_key, payload)
    return payload


def normalize_destination_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    clusters = []
    for item in clean_dict_list(payload.get("key_place_clusters") or []):
        cluster = {
            "name": trim_text(item.get("name"), 90),
            "why_it_matters": trim_text(item.get("why_it_matters"), 180),
            "typical_time_need": trim_text(item.get("typical_time_need"), 80),
        }
        cluster = strip_empty(cluster)
        if cluster:
            clusters.append(cluster)

    normalized = {
        "destination_overview": trim_text(payload.get("destination_overview"), 700),
        "key_place_clusters": clusters[:8],
        "how_to_reach": trim_str_list(payload.get("how_to_reach") or [], limit=6, text_limit=180),
        "movement_within_destination": trim_str_list(payload.get("movement_within_destination") or [], limit=6, text_limit=180),
        "signature_experiences": trim_str_list(payload.get("signature_experiences") or [], limit=8, text_limit=150),
        "local_food_highlights": trim_str_list(payload.get("local_food_highlights") or [], limit=8, text_limit=130),
        "planning_cautions": trim_str_list(payload.get("planning_cautions") or [], limit=8, text_limit=160),
        "pace_signal": trim_text(payload.get("pace_signal"), 180),
        "citations": clean_citations(payload.get("citations") or [])[:10],
    }
    return strip_empty(normalized)


def normalize_travel_essentials(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        field: trim_str_list(payload.get(field) or [], limit=6, text_limit=160)
        for field in TRAVEL_ESSENTIALS_LIST_FIELDS
    }
    normalized["citations"] = clean_citations(payload.get("citations") or [])[:10]
    return strip_empty(normalized)


def has_practical_coverage(essentials: dict[str, Any]) -> bool:
    return any(clean_str_list(essentials.get(field) or []) for field in TRAVEL_ESSENTIALS_LIST_FIELDS)


def essentials_input_projection(research_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "destination": research_input.get("destination"),
        "selected_destination": research_input.get("selected_destination"),
        "trip": research_input.get("trip"),
        "group_signals": research_input.get("group_signals"),
        "interests": research_input.get("interests"),
        "pace": research_input.get("pace"),
        "constraints": research_input.get("constraints"),
        "preferences": research_input.get("preferences"),
    }


def extract_response_citations(content: Any) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    blocks = content if isinstance(content, list) else []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        annotations = block.get("annotations") or []
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            title = clean_text(annotation.get("title") or annotation.get("text") or annotation.get("label"))
            url = clean_text(annotation.get("url") or annotation.get("uri"))
            if url:
                citations.append({"title": title or url, "url": url})
        if isinstance(block.get("text"), dict):
            for annotation in block["text"].get("annotations") or []:
                if not isinstance(annotation, dict):
                    continue
                title = clean_text(annotation.get("title") or annotation.get("text") or annotation.get("label"))
                url = clean_text(annotation.get("url") or annotation.get("uri"))
                if url:
                    citations.append({"title": title or url, "url": url})
    return compact_citations(citations)


def merge_citations(*citation_groups: Any) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for group in citation_groups:
        for citation in clean_citations(group):
            url_key = citation["url"].lower().strip()
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)
            merged.append(citation)
    return merged[:20]


def compact_citations(values: Any, *, limit: int = 20, title_limit: int = 120, url_limit: int = 300) -> list[dict[str, str]]:
    compacted: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for citation in clean_dict_list(values or []):
        url = clean_text(citation.get("url"))[:url_limit]
        if not url:
            continue
        url_key = url.lower().strip()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        title = clean_text(citation.get("title"), url)[:title_limit]
        item = {"title": title, "url": url}
        if clean_text(citation.get("ref_type")):
            item["ref_type"] = clean_text(citation.get("ref_type"))[:50]
        compacted.append(item)
        if len(compacted) >= limit:
            break
    return compacted


def clean_citations(values: Any) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for item in clean_dict_list(values or []):
        url = clean_text(item.get("url"))
        if not url:
            continue
        citations.append({"title": clean_text(item.get("title"), url), "url": url})
    return citations


def infer_interests(
    selected_destination: dict[str, Any],
    followup_answers: list[dict[str, Any]],
    custom_note: str,
    change_request: str,
) -> list[str]:
    text_parts: list[str] = []
    text_parts.extend(clean_str_list(selected_destination.get("highlights") or []))
    text_parts.append(clean_text(selected_destination.get("best_for")))
    text_parts.append(custom_note)
    text_parts.append(change_request)
    for answer in followup_answers:
        raw = answer.get("answer")
        if isinstance(raw, list):
            text_parts.extend(clean_str_list(raw))
        else:
            text_parts.append(clean_text(raw))

    text = " ".join(text_parts).lower()
    interests = []
    keyword_map = {
        "nature": ["nature", "hill", "mountain", "river", "forest", "beach", "view"],
        "food": ["food", "cafe", "seafood", "local cuisine", "restaurant"],
        "culture": ["culture", "heritage", "temple", "palace", "fort", "monastery"],
        "adventure": ["adventure", "trek", "rafting", "water sport", "snow", "safari"],
        "relaxation": ["relax", "slow", "quiet", "resort", "wellness"],
        "family-friendly": ["family", "kids", "senior", "easy walking"],
    }
    for label, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            interests.append(label)
    return interests[:6] or ["balanced sightseeing"]


def infer_pace(followup_answers: list[dict[str, Any]], custom_note: str, change_request: str) -> str:
    text = " ".join(
        [clean_text(custom_note), clean_text(change_request)]
        + [clean_text(answer.get("answer")) if not isinstance(answer.get("answer"), list) else " ".join(clean_str_list(answer.get("answer"))) for answer in followup_answers]
    ).lower()
    if any(keyword in text for keyword in ["relaxed", "slow", "easy", "kid", "senior"]):
        return "relaxed"
    if any(keyword in text for keyword in ["fast", "packed", "active", "cover more"]):
        return "active"
    return "balanced"


def infer_known_constraints(
    state: dict[str, Any],
    selected_destination: dict[str, Any],
    custom_note: str,
    change_request: str,
) -> list[str]:
    constraints = []
    if state.get("has_kids"):
        constraints.append("Keep kid-friendly pacing and avoid late-night transfers.")
    if state.get("has_seniors"):
        constraints.append("Prefer lower physical strain and reliable local transfers.")
    if clean_text(custom_note):
        constraints.append(custom_note)
    if clean_text(change_request):
        constraints.append(change_request)
    duration_fit = clean_text(selected_destination.get("duration_fit"))
    if duration_fit:
        constraints.append(f"Shortlist duration signal: {duration_fit}")
    return dedupe(constraints)[:8]


def format_destination(selected_destination: dict[str, Any]) -> str:
    region = clean_text(selected_destination.get("state_or_region") or selected_destination.get("card_title"), "Selected destination")
    places = clean_str_list(selected_destination.get("places_covered") or [])
    return f"{region}: {', '.join(places)}" if places else region


def compact_destination(selected_destination: dict[str, Any]) -> dict[str, Any]:
    return strip_empty(
        {
            "state_or_region": clean_text(selected_destination.get("state_or_region")),
            "places_covered": clean_str_list(selected_destination.get("places_covered") or [])[:8],
            "highlights": clean_str_list(selected_destination.get("highlights") or [])[:8],
            "best_for": clean_text(selected_destination.get("best_for")),
            "duration_fit": clean_text(selected_destination.get("duration_fit")),
            "why_it_fits": clean_text(selected_destination.get("why_it_fits")),
        }
    )


def clean_followup_answers(values: list[Any]) -> list[dict[str, Any]]:
    answers = []
    for item in values:
        if not isinstance(item, dict):
            continue
        answer = item.get("answer")
        if isinstance(answer, list):
            cleaned_answer: str | list[str] = clean_str_list(answer)
        else:
            cleaned_answer = clean_text(answer)
        if cleaned_answer in ([], ""):
            continue
        answers.append(
            strip_empty(
                {
                    "question": clean_text(item.get("question")),
                    "input_type": clean_text(item.get("input_type")),
                    "answer": cleaned_answer,
                }
            )
        )
    return answers


def build_curator_summary(
    selected_destination: dict[str, Any],
    followup_answers: list[dict[str, Any]],
    custom_note: str,
    change_request: str,
) -> str:
    lines = [f"Selected destination: {format_destination(selected_destination)}."]
    why = clean_text(selected_destination.get("why_it_fits"))
    if why:
        lines.append(f"Why it fits: {why}")
    if followup_answers:
        answer_bits = []
        for item in followup_answers[:6]:
            answer = item.get("answer")
            answer_text = ", ".join(answer) if isinstance(answer, list) else clean_text(answer)
            question = clean_text(item.get("question"), "Follow-up")
            answer_bits.append(f"{question}: {answer_text}")
        lines.append("Traveler preferences: " + " | ".join(answer_bits))
    if custom_note:
        lines.append(f"Custom note: {custom_note}")
    if change_request:
        lines.append(f"Final correction: {change_request}")
    return "\n".join(lines)


def trim_str_list(values: Any, *, limit: int, text_limit: int) -> list[str]:
    return [trim_text(value, text_limit) for value in clean_str_list(values)[:limit] if trim_text(value, text_limit)]


def trim_text(value: Any, limit: int) -> str:
    text = clean_text(value)
    return text[:limit].rstrip()


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        cleaned = " ".join(value.strip().split())
    else:
        cleaned = " ".join(str(value).strip().split())
    return cleaned or fallback


def clean_str_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        text = clean_text(value)
        if text:
            cleaned.append(text)
    return dedupe(cleaned)


def clean_dict_list(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        if isinstance(value, dict):
            item = strip_empty(value)
            if isinstance(item, dict) and item:
                cleaned.append(item)
    return cleaned


def strip_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = strip_empty(item)
            if normalized not in ({}, [], None, ""):
                cleaned[key] = normalized
        return cleaned
    if isinstance(value, list):
        return [item for raw in value if (item := strip_empty(raw)) not in ({}, [], None, "")]
    return value


def dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = clean_text(value)
        key = text.lower()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def require_dict(state: dict, key: str) -> dict[str, Any]:
    value = state.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} is required before research can continue.")
    return value


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
