import ast
import json
from typing import Any


def clean_json_text(text: str) -> str:
    """Remove common markdown wrappers so the response can be parsed as JSON."""
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return cleaned.strip()


def extract_text_content(content: Any) -> str:
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


def load_json_payload(text: str) -> Any:
    """Load model output as JSON, with fallback for Python-style dict/list strings."""
    cleaned_text = clean_json_text(text)

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        return ast.literal_eval(cleaned_text)
