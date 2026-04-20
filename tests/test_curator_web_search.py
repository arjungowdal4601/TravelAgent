import json

from langchain_core.runnables import RunnableLambda

from nodes.call_destination_research import call_destination_research
from nodes.call_destination_research_with_user_hint import call_destination_research_with_user_hint


class _Response:
    def __init__(self, content: str):
        self.content = content


class _FallbackLLM:
    def __init__(self, content: str, calls: list[str]):
        self.content = content
        self.calls = calls

    def bind(self, **kwargs):
        self.calls.append("fallback_bind")
        return RunnableLambda(lambda _: _Response(self.content))


def _base_state() -> dict:
    return {
        "origin": "Origin City, Origin State",
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "trip_days": 5,
        "trip_type": "family",
        "member_count": 4,
        "has_kids": False,
        "has_seniors": True,
        "budget_mode": "premium",
        "budget_value": None,
    }


def _cards(prefix: str = "Search") -> list[dict]:
    return [
        {
            "card_title": f"{prefix} Trip {index} https://example.com/{index}",
            "state_or_region": f"{prefix} Region {index}",
            "trip_feel": "Grounded by search [1]",
            "places_covered": [f"{prefix} Place {index}"],
            "highlights": ["Practical access", "Season fit", "Local character"],
            "best_for": "Families",
            "pace": "balanced",
            "duration_fit": "Fits the available days",
            "why_it_fits": "Matches the route and comfort needs 【citation】",
            "estimated_price_range": "INR 40k-70k",
            "intent_match_reason": "Matches the hint",
            "difference_from_rejected": "Different region",
        }
        for index in range(4)
    ]


def test_initial_shortlist_uses_web_search_helper(monkeypatch) -> None:
    calls = []

    def fake_search_llm():
        calls.append("search")
        return RunnableLambda(lambda _: _Response(json.dumps(_cards())))

    monkeypatch.setattr("nodes.call_destination_research.get_curator_search_llm", fake_search_llm)

    output = call_destination_research(_base_state())

    assert calls == ["search"]
    assert len(output["shortlisted_destinations"]) == 4
    first_card = output["shortlisted_destinations"][0]
    assert "http" not in first_card["card_title"]
    assert "[1]" not in first_card["trip_feel"]
    assert "【" not in first_card["why_it_fits"]


def test_custom_hint_shortlist_uses_web_search_helper(monkeypatch) -> None:
    calls = []

    def fake_search_llm():
        calls.append("search")
        return RunnableLambda(lambda _: _Response(json.dumps(_cards("Hint"))))

    monkeypatch.setattr("nodes.call_destination_research.get_curator_search_llm", fake_search_llm)
    state = {
        **_base_state(),
        "user_hint": "quiet forest stay",
        "rejected_shortlists": [[{"card_title": "Rejected Trip", "state_or_region": "Rejected Region"}]],
        "shortlist_attempt_count": 2,
    }

    output = call_destination_research_with_user_hint(state)

    assert calls == ["search"]
    assert len(output["shortlisted_destinations"]) == 4
    assert output["shortlisted_destinations"][0]["intent_match_reason"] == "Matches the hint"


def test_curator_falls_back_when_web_search_errors(monkeypatch) -> None:
    calls = []

    def failing_search_llm():
        calls.append("search")
        raise RuntimeError("search unavailable")

    monkeypatch.setattr("nodes.call_destination_research.get_curator_search_llm", failing_search_llm)
    monkeypatch.setattr(
        "nodes.call_destination_research.get_llm",
        lambda: _FallbackLLM(json.dumps(_cards("Fallback")), calls),
    )

    output = call_destination_research(_base_state())

    assert calls == ["search", "fallback_bind"]
    assert output["shortlisted_destinations"][0]["state_or_region"] == "Fallback Region 0"
