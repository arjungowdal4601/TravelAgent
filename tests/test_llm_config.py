from llm import get_itinerary_llm, get_llm, get_research_llm, resolve_model_name
from nodes.call_destination_research import CURATOR_REASONING
from nodes.itinerary_agent import PLANNER_REASONING, PLANNER_TOOLS
from services.research_agent_helpers import RESEARCH_REASONING, RESEARCH_TOOLS


def test_single_model_defaults_to_gpt54_mini(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_RESEARCH_MODEL", "gpt-5")
    monkeypatch.setenv("OPENAI_ITINERARY_MODEL", "gpt-5")

    assert resolve_model_name() == "gpt-5.4-mini"
    assert get_llm().model_name == "gpt-5.4-mini"
    assert get_research_llm().model_name == "gpt-5.4-mini"
    assert get_itinerary_llm().model_name == "gpt-5.4-mini"


def test_single_global_model_override_applies_to_all_phases(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4-mini-custom")

    assert resolve_model_name() == "gpt-5.4-mini-custom"
    assert get_llm().model_name == "gpt-5.4-mini-custom"
    assert get_research_llm().model_name == "gpt-5.4-mini-custom"
    assert get_itinerary_llm().model_name == "gpt-5.4-mini-custom"


def test_model_constructors_do_not_set_token_caps(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MAX_COMPLETION_TOKENS", "100")
    monkeypatch.setenv("OPENAI_ITINERARY_MAX_COMPLETION_TOKENS", "100")

    assert get_llm().max_tokens is None
    assert get_research_llm().max_tokens is None
    assert get_itinerary_llm().max_tokens is None


def test_phase_reasoning_and_web_search_policy() -> None:
    assert CURATOR_REASONING == {"effort": "medium"}
    assert RESEARCH_REASONING == {"effort": "medium"}
    assert PLANNER_REASONING == {"effort": "high"}
    assert RESEARCH_TOOLS == [{"type": "web_search"}]
    assert PLANNER_TOOLS == [{"type": "web_search"}]
