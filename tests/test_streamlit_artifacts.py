import json
from pathlib import Path

from services import plan_artifacts, streamlit_artifacts


class _FakeDrawableGraph:
    def draw_mermaid(self) -> str:
        return "graph TD\n  start --> end\n"

    def draw_mermaid_png(self) -> bytes:
        return b"fake-png-bytes"


class _FakeGraph:
    def get_graph(self, xray=False):
        return _FakeDrawableGraph()


def test_output_root_defaults_to_repo_output_folder() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert plan_artifacts.OUTPUT_ROOT == repo_root / "output"


def test_streamlit_artifact_initialization_creates_session_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(plan_artifacts, "OUTPUT_ROOT", tmp_path / "output")

    artifact_paths = streamlit_artifacts.initialize_streamlit_artifacts(
        "thread-123",
        _FakeGraph(),
        "2026-04-20T00:00:00+00:00",
    )

    plan_dir = tmp_path / "output" / "streamlit-thread-123"
    assert Path(artifact_paths["output_dir"]) == plan_dir.resolve()
    for filename in [
        "metadata.json",
        "status.json",
        "draft.json",
        "graph_state.json",
        "workflow_graph.png",
        "workflow_graph.mmd",
    ]:
        assert (plan_dir / filename).exists()


def test_streamlit_snapshot_writes_interrupt_and_graph_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(plan_artifacts, "OUTPUT_ROOT", tmp_path / "output")
    streamlit_artifacts.initialize_streamlit_artifacts("thread-123", _FakeGraph())

    streamlit_artifacts.write_streamlit_snapshot(
        thread_id="thread-123",
        step="done",
        graph_state={"shortlist_cards": [{"card_title": "Card A"}]},
        interrupt={"type": "shortlist_decision"},
        error=None,
        trip_data={"origin": "Origin City, Origin State"},
        created_at="2026-04-20T00:00:00+00:00",
    )

    plan_dir = tmp_path / "output" / "streamlit-thread-123"
    status_payload = json.loads((plan_dir / "status.json").read_text(encoding="utf-8"))
    draft_payload = json.loads((plan_dir / "draft.json").read_text(encoding="utf-8"))
    graph_state = json.loads((plan_dir / "graph_state.json").read_text(encoding="utf-8"))
    interrupt = json.loads((plan_dir / "interrupt.json").read_text(encoding="utf-8"))

    assert status_payload["status"] == "waiting_for_review"
    assert status_payload["stage"] == "shortlist_decision"
    assert draft_payload["interrupt"]["type"] == "shortlist_decision"
    assert graph_state["shortlist_cards"][0]["card_title"] == "Card A"
    assert interrupt["type"] == "shortlist_decision"


def test_streamlit_final_artifacts_write_markdown_and_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(plan_artifacts, "OUTPUT_ROOT", tmp_path / "output")
    graph_state = {
        "itinerary_view_ready": True,
        "final_itinerary_markdown": "# Final Plan\n\nReady.",
        "final_itinerary": {"trip_summary": {"destination": "Destination A"}},
    }

    streamlit_artifacts.initialize_streamlit_artifacts("thread-123", _FakeGraph())
    artifact_paths = streamlit_artifacts.write_streamlit_final_artifacts(
        "thread-123",
        graph_state,
        _FakeGraph(),
    )

    assert Path(artifact_paths["final_markdown"]).read_text(encoding="utf-8").startswith("# Final Plan")
    structured = json.loads(Path(artifact_paths["structured_itinerary"]).read_text(encoding="utf-8"))
    assert structured["trip_summary"]["destination"] == "Destination A"
