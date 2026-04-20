import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


DEFAULT_MODEL = "gpt-5.4-mini"


def resolve_model_name() -> str:
    """Return the single model used across the travel agent."""
    load_dotenv()
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_llm() -> ChatOpenAI:
    """Create the chat model for the information-curator phase."""
    load_dotenv()
    return ChatOpenAI(model=resolve_model_name())


def get_research_llm() -> ChatOpenAI:
    """Create the Responses API model for citation-backed research nodes."""
    load_dotenv()
    return ChatOpenAI(
        model=resolve_model_name(),
        use_responses_api=True,
        output_version="responses/v1",
    )


def get_itinerary_llm() -> ChatOpenAI:
    """Create the Responses API model for itinerary planning and synthesis."""
    load_dotenv()
    return ChatOpenAI(
        model=resolve_model_name(),
        use_responses_api=True,
        output_version="responses/v1",
    )
