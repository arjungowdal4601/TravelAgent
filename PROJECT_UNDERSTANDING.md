# Travel Agent: Understanding and Full Code Flow

## What This Project Is

This project is a **Streamlit + LangGraph travel planning system** focused on India trips.
It is built as a staged pipeline:

1. Collect user trip inputs in chat-style UI.
2. Curate and confirm destination intent with user interaction loops.
3. Run factual destination research with citations.
4. Build a practical day-by-day itinerary with cost ranges.
5. Render final Markdown itinerary plus structured JSON data.

The system is intentionally split into clear stages so each stage has one responsibility and can be validated.

## Main Intention

The main intention is to produce a **practical, explainable, and user-aligned itinerary** instead of a generic travel essay.

Core goals:

- Keep the user in control with decision checkpoints (select/reject shortlist, review summary, continue/start over).
- Use live web-backed research where needed for practical context.
- Keep outputs structured and compact (JSON contracts, validation, fallback behavior).
- Deliver a clean final itinerary in Markdown for easy reading in UI.

## High-Level Architecture

- `app.py` starts Streamlit UI.
- `UI/app.py` runs step-based input collection and handles graph interrupts/resume.
- `main.py` defines and compiles a LangGraph `StateGraph(TravelState)`.
- `schemas/travel_state.py` defines shared state contract and merge strategies.
- `nodes/` contains all execution logic, split into:
  - Information curator flow
  - Research flow
  - Itinerary flow

## End-to-End Flow

### Stage 1: Basic Input Collection (UI)

The UI collects:

- origin
- date range
- trip type
- members / kids / seniors
- budget mode and optional custom budget

Then it converts this to graph input and invokes the graph.

### Stage 2: Information Curator Flow (Interactive)

1. `call_destination_research`
   - LLM returns exactly 4 destination groups.
2. `build_shortlist_cards`
   - Deterministically cleans and normalizes card data for UI.
   - Preserves existing card fields and adds `card_title`, `trip_feel`, `pace`.
   - Mirrors normalized cards into `explained_shortlisted_destinations` for compatibility.
4. `await_shortlist_decision` (interrupt)
   - User selects one destination or rejects all.
5. If rejected:
   - `ask_half_baked_plan` (interrupt)
   - `call_destination_research_with_user_hint`
   - back to card normalization + shortlist selection
6. If selected:
   - `call_generate_contextual_destination_questions`
   - `collect_followup_answers` loop
   - `collect_custom_followup_input` (interrupt)
   - `review_followup_summary` (interrupt)
   - same confirmation interrupt renders Streamlit summary + optional correction + action
   - `continue` starts research pipeline, `start_over` resets app flow

### Stage 3: Research Agent Flow

Runs only when user chooses `continue`.

1. `normalize_research_input`
   - Compacts selected destination + user preferences into research-ready payload.
2. `build_destination_research`
   - Web-backed structured destination intelligence.
3. `enrich_with_practical_travel_info`
   - Adds weather, local movement, docs, safety, etc.
4. `aggregate_research_packet`
   - Merges and compacts packet with citations.
5. `validate_research_packet`
   - Checks completeness and size budget.
6. Conditional repair path:
   - Can re-run destination or practical enrichment once.
7. `research_agent_output`
   - Emits compact debug-friendly summary.

### Stage 4: Itinerary Agent Flow

1. `prepare_itinerary_input`
   - Transforms validated research into planner input.
2. `fetch_live_trip_context`
   - Pulls practical live context for transport/stay/fares/timings.
3. `build_trip_skeleton`
   - Creates ordered day slots from trip dates.
4. `plan_days_sequentially`
   - Plans each day with constraints and fallback handling.
5. `aggregate_final_itinerary`
   - Produces final structured itinerary object.
6. `render_clean_itinerary_markdown`
   - Builds user-facing Markdown output.
7. `show_separate_itinerary_view`
   - Marks itinerary view as ready in UI.

## Routing and Control Decisions

Routing functions in `nodes/routing.py` drive key branch behavior:

- shortlist decision route: selected vs rejected
- follow-up loop route: continue questions vs move to custom notes
- final action route: continue research/planning vs start over
- research validation route: repair target or continue

This keeps business logic explicit and easy to inspect.

## State and Data Contract

`TravelState` is the central memory object across all nodes.
It stores:

- user inputs and selected destination
- follow-up Q&A, final correction, and confirmation action
- normalized research input/output
- live context and itinerary planning packets
- final itinerary JSON + final Markdown
- validation results and readiness flags

It also uses merge helpers for fan-out/fan-in style data (`day_itinerary_packets`, `itinerary_sections`, `source_registry`).

## Quality and Safety Patterns

The system includes several reliability patterns:

- strict output shape checks (for example, exactly 4 shortlist items)
- compactness budgets to prevent oversized state payloads
- citation merging and deduplication for factual context
- fallback generation when LLM calls fail or data is incomplete
- validation before downstream stages continue
- interrupt/resume checkpoints for user control

## How UI and Graph Work Together

- Graph nodes trigger pauses using `interrupt(...)`.
- Streamlit detects interrupt payload type and renders matching component.
- User action returns a payload and resumes graph with `Command(resume=...)`.
- This design creates a guided conversation while keeping orchestration in LangGraph.

## Final Understanding in One Line

This project is a **multi-stage travel planning orchestrator** that moves from user intent -> destination curation -> cited research -> practical itinerary markdown, with validation and user checkpoints at every important decision point.
