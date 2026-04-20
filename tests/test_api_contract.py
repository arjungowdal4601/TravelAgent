from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api
from services import plan_artifacts


class _FakeState:
    def __init__(self, values: dict):
        self.values = values


class _FakeDrawableGraph:
    def draw_mermaid(self) -> str:
        return "graph TD\n  start --> end\n"

    def draw_mermaid_png(self) -> bytes:
        return b"fake-png-bytes"


class _FakeGraph:
    def __init__(self):
        self.values: dict = {}
        self.invocations = []

    def invoke(self, graph_input, config=None):
        self.invocations.append(graph_input)
        resume = getattr(graph_input, "resume", None)
        if resume is None:
            self.values = {
                "shortlist_cards": [
                    {"card_title": "Card A", "state_or_region": "Region A"},
                    {"card_title": "Card B", "state_or_region": "Region B"},
                ]
            }
            return {
                "__interrupt__": [
                    {
                        "value": {
                            "type": "shortlist_decision",
                            "shortlist_cards": self.values["shortlist_cards"],
                        }
                    }
                ]
            }

        if resume.get("action") == "reject":
            self.values = {"shortlist_decision": "rejected"}
            return {"__interrupt__": [{"value": {"type": "half_baked_plan"}}]}

        if resume.get("user_hint"):
            self.values = {"user_hint": resume["user_hint"], "shortlist_cards": [{"card_title": "New Card"}]}
            return {"__interrupt__": [{"value": {"type": "shortlist_decision", "shortlist_cards": self.values["shortlist_cards"]}}]}

        self.values = {
            "itinerary_view_ready": True,
            "final_itinerary_markdown": "# Final Plan\n\nReady.",
            "final_itinerary": {"trip_summary": {"destination": "Region A"}},
        }
        return {}

    def get_state(self, config=None):
        return _FakeState(self.values)

    def get_graph(self, xray=False):
        return _FakeDrawableGraph()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    fake_graph = _FakeGraph()
    api.PLANS.clear()
    monkeypatch.setattr(api, "travel_graph", fake_graph)
    monkeypatch.setattr(plan_artifacts, "OUTPUT_ROOT", tmp_path / "output")
    return TestClient(api.app), fake_graph, tmp_path / "output"


def _valid_plan_payload() -> dict:
    return {
        "origin": "Origin City, Origin State",
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "trip_type": "family",
        "member_count": 4,
        "has_kids": False,
        "has_seniors": True,
        "budget_mode": "premium",
        "budget_value": None,
    }


def test_create_plan_returns_id_and_current_stage(client) -> None:
    test_client, _fake_graph, output_root = client

    response = test_client.post("/plan", json=_valid_plan_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["status"] == "waiting_for_review"
    assert body["stage"] == "shortlist_decision"
    assert body["required_action"]["type"] == "shortlist_decision"
    plan_dir = output_root / body["id"]
    assert plan_dir.exists()
    for filename in [
        "metadata.json",
        "status.json",
        "draft.json",
        "graph_state.json",
        "interrupt.json",
        "workflow_graph.png",
        "workflow_graph.mmd",
    ]:
        assert (plan_dir / filename).exists()

    status_payload = json.loads((plan_dir / "status.json").read_text(encoding="utf-8"))
    assert status_payload["status"] == "waiting_for_review"
    assert status_payload["stage"] == "shortlist_decision"


def test_get_plan_unknown_id_returns_404(client) -> None:
    test_client, _fake_graph, _output_root = client

    response = test_client.get("/plan/missing")

    assert response.status_code == 404


def test_final_before_completion_returns_409(client) -> None:
    test_client, _fake_graph, _output_root = client
    plan_id = test_client.post("/plan", json=_valid_plan_payload()).json()["id"]

    response = test_client.get(f"/plan/{plan_id}/final")

    assert response.status_code == 409


def test_review_approve_completes_and_writes_artifacts(client) -> None:
    test_client, _fake_graph, output_root = client
    plan_id = test_client.post("/plan", json=_valid_plan_payload()).json()["id"]

    review_response = test_client.post(
        f"/plan/{plan_id}/review",
        json={"action": "approve", "selected_index": 0},
    )
    assert review_response.status_code == 200
    review_artifacts = review_response.json()["artifact_paths"]

    assert Path(review_artifacts["final_markdown"]).exists()
    assert Path(review_artifacts["structured_itinerary"]).exists()

    final_response = test_client.get(f"/plan/{plan_id}/final")

    assert review_response.json()["status"] == "completed"
    assert final_response.status_code == 200
    artifacts = final_response.json()["artifact_paths"]
    assert Path(artifacts["final_markdown"]).exists()
    assert Path(artifacts["workflow_graph_png"]).exists()
    assert Path(artifacts["workflow_graph_mermaid"]).exists()
    assert Path(artifacts["metadata"]).exists()
    assert (output_root / plan_id / "final.md").read_text(encoding="utf-8").startswith("# Final Plan")


def test_reject_with_feedback_submits_custom_hint_in_same_review_call(client) -> None:
    test_client, fake_graph, output_root = client
    plan_id = test_client.post("/plan", json=_valid_plan_payload()).json()["id"]

    response = test_client.post(
        f"/plan/{plan_id}/review",
        json={"action": "reject", "feedback": "quiet highland trip"},
    )

    assert response.status_code == 200
    assert response.json()["stage"] == "shortlist_decision"
    assert getattr(fake_graph.invocations[-1], "resume") == {"user_hint": "quiet highland trip"}
    draft_payload = json.loads((output_root / plan_id / "draft.json").read_text(encoding="utf-8"))
    assert draft_payload["stage"] == "shortlist_decision"


def test_invalid_plan_payload_returns_422(client) -> None:
    test_client, _fake_graph, _output_root = client
    payload = _valid_plan_payload()
    payload["end_date"] = "2026-05-30"

    response = test_client.post("/plan", json=payload)

    assert response.status_code == 422
