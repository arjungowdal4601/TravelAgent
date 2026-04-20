import pytest
from langgraph.graph import END

from nodes.review_followup_summary import review_followup_summary
from nodes.routing import route_final_action


def test_review_followup_summary_continue_with_correction(monkeypatch) -> None:
    captured_payload = {}

    def _fake_interrupt(payload):
        captured_payload.update(payload)
        return {
            "action": "continue",
            "followup_change_request": "Please avoid late-night activities.",
        }

    monkeypatch.setattr("nodes.review_followup_summary.interrupt", _fake_interrupt)

    state = {
        "selected_destination": {
            "card_title": "Calm Hills Escape",
            "state_or_region": "Himachal Pradesh",
            "places_covered": ["Manali", "Naggar"],
        },
        "followup_answers": [
            {
                "question": "Preferred pace?",
                "input_type": "single_select",
                "answer": "Relaxed",
            },
            {
                "question": "Pick experiences",
                "input_type": "multi_select",
                "answer": ["Nature", "Food"],
            },
        ],
        "followup_custom_note": "Need kid-friendly options.",
        "followup_change_request": "Existing note",
    }

    output = review_followup_summary(state)

    assert captured_payload["type"] == "followup_confirmation"
    assert captured_payload["selected_destination"]["state_or_region"] == "Himachal Pradesh"
    assert output["final_action"] == "continue"
    assert "Existing note" in output["followup_change_request"]
    assert "Final correction: Please avoid late-night activities." in output["followup_change_request"]


def test_review_followup_summary_start_over_without_correction(monkeypatch) -> None:
    monkeypatch.setattr(
        "nodes.review_followup_summary.interrupt",
        lambda _: {"action": "start_over"},
    )

    state = {
        "selected_destination": {"state_or_region": "Goa"},
        "followup_answers": [],
        "followup_custom_note": "",
    }
    output = review_followup_summary(state)
    assert output["final_action"] == "start_over"
    assert output["followup_change_request"] == ""


def test_review_followup_summary_rejects_invalid_action(monkeypatch) -> None:
    monkeypatch.setattr(
        "nodes.review_followup_summary.interrupt",
        lambda _: {"action": "invalid"},
    )
    with pytest.raises(ValueError):
        review_followup_summary({"selected_destination": {"state_or_region": "Kerala"}})


def test_route_final_action_still_routes_continue_and_start_over() -> None:
    assert route_final_action({"final_action": "continue"}) == "handoff_to_parent_graph"
    assert route_final_action({"final_action": "start_over"}) == END
