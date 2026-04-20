from nodes.call_generate_contextual_destination_questions import (
    _normalize_followup_questions,
)
from nodes.collect_followup_answers import collect_followup_answers


def test_normalize_followup_questions_supports_mixed_types() -> None:
    raw = [
        {
            "question": "What pace do you prefer?",
            "input_type": "single_select",
            "options": ["Relaxed", "Balanced", "Fast", "Balanced"],
            "why_this_matters": "Sets day density.",
        },
        {
            "question": "Which experiences matter most?",
            "input_type": "multi_select",
            "options": ["Nature", "Food", "Adventure", "Culture"],
        },
        {
            "question": "Any specific must-do request?",
            "input_type": "text",
            "placeholder": "e.g., sunrise trek",
        },
        # Backward-compatible old schema (no input_type).
        {
            "question": "Where do you prefer to stay?",
            "options": ["City center", "Quiet outskirts", "Resort zone"],
        },
    ]

    questions = _normalize_followup_questions(raw)
    assert len(questions) == 4
    assert questions[0]["input_type"] == "single_select"
    assert questions[0]["options"] == ["Relaxed", "Balanced", "Fast"]
    assert questions[1]["input_type"] == "multi_select"
    assert questions[2]["input_type"] == "text"
    assert questions[2]["placeholder"] == "e.g., sunrise trek"
    assert questions[3]["input_type"] == "single_select"
    assert "why_this_matters" in questions[1]


def test_collect_followup_answers_single_select(monkeypatch) -> None:
    state = {
        "followup_questions": [
            {
                "question": "Preferred pace?",
                "input_type": "single_select",
                "options": ["Relaxed", "Balanced", "Fast"],
            }
        ],
        "current_followup_index": 0,
        "followup_answers": [],
    }

    monkeypatch.setattr(
        "nodes.collect_followup_answers.interrupt",
        lambda _: {"answer": "Balanced"},
    )

    output = collect_followup_answers(state)
    assert output["current_followup_index"] == 1
    assert output["followup_answers"][0]["answer"] == "Balanced"
    assert output["followup_answers"][0]["input_type"] == "single_select"


def test_collect_followup_answers_multi_select(monkeypatch) -> None:
    state = {
        "followup_questions": [
            {
                "question": "Pick experiences",
                "input_type": "multi_select",
                "options": ["Nature", "Food", "Culture"],
            }
        ],
        "current_followup_index": 0,
        "followup_answers": [],
    }

    monkeypatch.setattr(
        "nodes.collect_followup_answers.interrupt",
        lambda _: {"answer": ["Nature", "Food"]},
    )

    output = collect_followup_answers(state)
    assert output["current_followup_index"] == 1
    assert output["followup_answers"][0]["answer"] == ["Nature", "Food"]
    assert output["followup_answers"][0]["input_type"] == "multi_select"


def test_collect_followup_answers_text(monkeypatch) -> None:
    state = {
        "followup_questions": [
            {
                "question": "Any custom must-do?",
                "input_type": "text",
                "placeholder": "Type here",
            }
        ],
        "current_followup_index": 0,
        "followup_answers": [],
    }

    monkeypatch.setattr(
        "nodes.collect_followup_answers.interrupt",
        lambda _: {"answer": "Sunrise viewpoint on day 2"},
    )

    output = collect_followup_answers(state)
    assert output["current_followup_index"] == 1
    assert output["followup_answers"][0]["answer"] == "Sunrise viewpoint on day 2"
    assert output["followup_answers"][0]["input_type"] == "text"
