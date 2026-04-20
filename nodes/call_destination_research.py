import ast
import json

from langchain_core.prompts import ChatPromptTemplate

from constants.prompts.information_curator_prompts import (
    DESTINATION_RESEARCH_HUMAN_PROMPT,
    DESTINATION_RESEARCH_SYSTEM_PROMPT,
)
from llm import get_llm


def _clean_json_text(text: str) -> str:
    """Remove common markdown wrappers so the response can be parsed as JSON."""
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return cleaned.strip()


def _extract_text_content(content) -> str:
    """Extract plain text from string or content-block style model responses."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "text" and isinstance(item.get("value"), str):
                    parts.append(item["value"])
        return "\n".join(parts)

    return str(content)


def _load_json_payload(text: str):
    """Load model output as JSON, with a simple fallback for Python-style dict strings."""
    cleaned_text = _clean_json_text(text)

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        return ast.literal_eval(cleaned_text)


def call_destination_research(state: dict) -> dict:
    """Shortlist exactly 4 India destination groups from the current graph state."""
    travel_input = {
        "origin": state.get("origin"),
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
        "trip_days": state.get("trip_days"),
        "trip_type": state.get("trip_type"),
        "member_count": state.get("member_count"),
        "has_kids": state.get("has_kids"),
        "has_seniors": state.get("has_seniors"),
        "budget_mode": state.get("budget_mode"),
        "budget_value": state.get("budget_value"),
    }

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", DESTINATION_RESEARCH_SYSTEM_PROMPT),
            ("human", DESTINATION_RESEARCH_HUMAN_PROMPT),
        ]
    )

    llm = get_llm().bind(reasoning={"effort": "medium"})
    response = (prompt | llm).invoke(
        {"travel_input": json.dumps(travel_input, indent=2)}
    )
    content = _extract_text_content(response.content)
    shortlisted_destinations = _load_json_payload(content)

    if not isinstance(shortlisted_destinations, list) or len(shortlisted_destinations) != 4:
        raise ValueError("The model must return exactly 4 destination groups.")

    updated_state = dict(state)
    updated_state["shortlisted_destinations"] = shortlisted_destinations
    return updated_state
