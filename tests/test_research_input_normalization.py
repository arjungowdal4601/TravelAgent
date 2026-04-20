from nodes.research_agent import normalize_research_input


def test_normalize_research_input_works_without_generated_final_brief() -> None:
    state = {
        "selected_destination": {
            "state_or_region": "Uttarakhand",
            "places_covered": ["Rishikesh", "Mussoorie"],
            "highlights": ["Nature", "River views"],
            "best_for": "Family trips",
            "duration_fit": "4-5 days",
            "why_it_fits": "Short travel windows work well",
        },
        "origin": "Bengaluru, Karnataka",
        "start_date": "2026-05-10",
        "end_date": "2026-05-15",
        "trip_days": 6,
        "trip_type": "family",
        "budget_mode": "standard",
        "budget_value": None,
        "member_count": 4,
        "has_kids": True,
        "has_seniors": False,
        "followup_answers": [
            {
                "question": "Preferred pace?",
                "input_type": "single_select",
                "answer": "Relaxed",
            },
            {
                "question": "Which experiences?",
                "input_type": "multi_select",
                "answer": ["Nature", "Food"],
            },
        ],
        "followup_custom_note": "Need easy walking options.",
        "followup_change_request": "Final correction: Avoid late nights.",
    }

    output = normalize_research_input(state)
    research_input = output["research_input"]

    assert research_input["destination"].startswith("Uttarakhand")
    assert research_input["curator_summary"]
    assert research_input["final_brief"] == research_input["curator_summary"]
    assert research_input["preferences"]["change_request"] == "Final correction: Avoid late nights."

    followup_answers = research_input["preferences"]["followup_answers"]
    assert isinstance(followup_answers[1]["answer"], list)
    assert followup_answers[1]["answer"] == ["Nature", "Food"]
