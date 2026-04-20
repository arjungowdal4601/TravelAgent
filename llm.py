import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


def get_llm() -> ChatOpenAI:
    """Create a simple chat model for the travel prototype."""
    load_dotenv()

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
    )


def get_research_llm() -> ChatOpenAI:
    """Create a research model that can use OpenAI server-side web search."""
    load_dotenv()

    return ChatOpenAI(
        model=resolve_research_model_name(),
        use_responses_api=True,
        output_version="responses/v1",
    )


def resolve_research_model_name() -> str:
    """Return the GPT-5 model required for destination research."""
    load_dotenv()

    model = os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5")
    if "mini" in model.lower():
        return "gpt-5"
    return model


def resolve_itinerary_model_name() -> str:
    """Return a non-mini GPT-5 model for final itinerary planning."""
    load_dotenv()

    model = os.getenv("OPENAI_ITINERARY_MODEL", "gpt-5.4")
    if "mini" in model.lower():
        return "gpt-5.4"
    return model


def get_itinerary_llm() -> ChatOpenAI:
    """Create the GPT-5 itinerary model used for planning and synthesis."""
    load_dotenv()

    return ChatOpenAI(
        model=resolve_itinerary_model_name(),
        use_responses_api=True,
        output_version="responses/v1",
    )
