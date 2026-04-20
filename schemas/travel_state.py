from typing import Annotated, Any, TypedDict


def merge_day_itinerary_packets(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Merge fan-out day packets by stable day_id and sort by day_index."""
    merged: dict[str, dict[str, Any]] = {}
    for packet in left or []:
        if isinstance(packet, dict) and packet.get("day_id"):
            merged[str(packet["day_id"])] = packet
    for packet in right or []:
        if isinstance(packet, dict) and packet.get("day_id"):
            merged[str(packet["day_id"])] = packet
    return sorted(
        merged.values(),
        key=lambda item: (
            int(item.get("day_index") or 0),
            str(item.get("day_id") or ""),
        ),
    )


def merge_itinerary_sections(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Merge parallel final itinerary sections by section_id."""
    merged: dict[str, dict[str, Any]] = {}
    for section in left or []:
        if isinstance(section, dict) and section.get("section_id"):
            merged[str(section["section_id"])] = section
    for section in right or []:
        if isinstance(section, dict) and section.get("section_id"):
            merged[str(section["section_id"])] = section
    return sorted(merged.values(), key=lambda item: str(item.get("section_id") or ""))


def merge_source_registry(
    left: dict[str, dict[str, Any]] | None,
    right: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Merge source refs by id, keeping updates deterministic."""
    merged: dict[str, dict[str, Any]] = {}
    for registry in [left or {}, right or {}]:
        for key, value in registry.items():
            if isinstance(value, dict):
                merged[str(key)] = value
    return merged


class CitationRef(TypedDict, total=False):
    title: str
    url: str
    ref_type: str
    note: str


class ItineraryInput(TypedDict, total=False):
    trip_summary: dict[str, Any]
    destination_summary: dict[str, Any]
    traveler_group: dict[str, Any]
    preferences: dict[str, Any]
    must_do_places: list[dict[str, Any]]
    optional_places: list[dict[str, Any]]
    area_clusters: list[dict[str, Any]]
    practical_notes: dict[str, Any]
    constraints: list[str]
    assumptions: list[str]
    warnings: list[str]
    citations: list[CitationRef]


class DaySlot(TypedDict, total=False):
    day_id: str
    day_index: int
    date: str
    title_placeholder: str
    day_type: str
    base_area: str
    day_intensity: str
    arrival_logistics_needed: bool
    return_logistics_needed: bool
    base_area_placeholder: str
    start_time_policy: str
    end_time_policy: str
    planning_intensity: str
    carryover_constraints: list[str]
    notes: list[str]


class NightSlot(TypedDict, total=False):
    night_id: str
    after_day_id: str
    date: str
    block_type: str
    base_area_placeholder: str
    notes: list[str]


class TripSkeleton(TypedDict, total=False):
    trip_days: int
    start_date: str
    end_date: str
    day_slots: list[DaySlot]
    night_slots: list[NightSlot]
    base_area: str
    assumptions: list[str]


class TripLiveContext(TypedDict, total=False):
    origin_destination_transport_context: dict[str, Any]
    return_transport_context: dict[str, Any]
    stay_cost_context: dict[str, Any]
    local_fare_context: list[dict[str, Any]]
    attraction_cost_context: list[dict[str, Any]]
    meal_cost_context: dict[str, Any]
    local_transfer_cost_context: list[dict[str, Any]]
    opening_time_context: list[dict[str, Any]]
    restaurant_context: list[dict[str, Any]]
    fallback_estimate_policy: str
    source_refs: list[CitationRef]


class DestinationResearch(TypedDict, total=False):
    destination_summary: str
    duration_fit: str
    area_clusters: list[dict[str, Any]]
    must_do_places: list[dict[str, Any]]
    optional_places: list[dict[str, Any]]
    niche_or_extra_places: list[dict[str, Any]]
    best_experiences: list[str]
    best_food: list[str]
    best_activities: list[str]
    constraints: list[str]
    warnings: list[str]
    assumptions: list[str]
    citations: list[CitationRef]


class PracticalTravelInfo(TypedDict, total=False):
    weather_temperature: dict[str, Any]
    carry: list[str]
    practical_facts: list[str]
    local_transport: list[str]
    money: list[str]
    documents: list[str]
    safety: list[str]
    connectivity: list[str]
    culture: list[str]
    warnings: list[str]
    citations: list[CitationRef]


class StayBasePlan(TypedDict, total=False):
    primary_base_area: str
    night_wise_base_allocation: list[dict[str, Any]]
    check_in_check_out_assumptions: list[str]
    stay_transitions: list[dict[str, Any]]
    reasoning: list[str]
    assumptions: list[str]
    source_refs: list[CitationRef]


class BookingCostNotes(TypedDict, total=False):
    exact_booking_costs_available: bool
    notes: list[str]
    transport_cost_assumptions: list[str]
    daily_cost_assumptions: list[str]
    booking_refs: list[CitationRef]
    cost_refs: list[CitationRef]


class TransportPlan(TypedDict, total=False):
    outbound_journey_summary: dict[str, Any]
    return_journey_summary: dict[str, Any]
    major_transfer_plan: list[dict[str, Any]]
    local_movement_strategy: dict[str, Any]
    first_mile_last_mile_assumptions: list[str]
    booking_cost_assumptions: list[str]
    source_refs: list[CitationRef]
    booking_cost_refs: list[CitationRef]


class DayPlanningTask(TypedDict, total=False):
    day_id: str
    day_index: int
    date: str
    day_type: str
    assigned_base_area: str
    must_do_candidates: list[dict[str, Any]]
    optional_candidates: list[dict[str, Any]]
    area_focus: list[str]
    food_ideas: list[str]
    constraints: list[str]
    timing_policy: dict[str, Any]
    pacing_target: str
    day_level_cost_assumptions: list[str]
    practical_notes: list[str]
    carry_suggestions: list[str]
    citations: list[CitationRef]
    source_ids: list[str]
    itinerary_run_id: str
    projection_char_count: int


class DayItineraryPacket(TypedDict, total=False):
    day_id: str
    day_index: int
    date: str
    title: str
    day_type: str
    base_area: str
    schedule: list[dict[str, Any]]
    meals: list[dict[str, Any]]
    estimated_spend: dict[str, Any]
    important_note: str
    source_refs: list[CitationRef]
    planned_places: list[str]
    start_of_day_time: str
    end_of_day_time: str
    ordered_activities: list[dict[str, Any]]
    meal_placement: list[dict[str, Any]]
    breaks: list[dict[str, Any]]
    local_transport_notes: list[str]
    expected_spend: dict[str, Any]
    carry_for_day: list[str]
    notes: list[str]
    warnings: list[str]
    citations: list[CitationRef]
    source_ids: list[str]
    artifact_ref: dict[str, str]
    markdown_ref: dict[str, str]
    activity_count: int
    major_activity_count: int
    warning_count: int
    planned_places: list[str]
    validation_flags: dict[str, Any]


class ItineraryValidation(TypedDict, total=False):
    valid: bool
    issues: list[str]
    repair_targets: list[str]
    repair_attempts: dict[str, int]


class FinalItinerary(TypedDict, total=False):
    trip_brief: dict[str, Any]
    travel_logistics: dict[str, Any]
    stay_plan: dict[str, Any]
    local_transport: dict[str, Any]
    days: list[DayItineraryPacket]
    trip_notes: list[str]
    do_and_dont: dict[str, list[str]]
    cost_summary: dict[str, Any]
    source_notes: list[CitationRef]
    trip_summary: dict[str, Any]
    stay_base_plan: StayBasePlan
    transport_plan: TransportPlan
    day_plans: list[DayItineraryPacket]
    night_plans: list[dict[str, Any]]
    cost_summary: dict[str, Any]
    carry_list: list[str]
    documents: list[str]
    warnings: list[str]
    do_and_dont: dict[str, list[str]]
    source_refs: dict[str, list[CitationRef]]
    assumptions: list[str]
    place_coverage: dict[str, Any]
    sections: list[dict[str, Any]]
    day_detail_refs: dict[str, dict[str, str]]
    day_markdown_refs: dict[str, dict[str, str]]
    final_markdown_ref: dict[str, str]


class TravelState(TypedDict, total=False):
    origin: str
    start_date: str
    end_date: str
    trip_days: int
    trip_type: str
    member_count: int
    has_kids: bool
    has_seniors: bool
    budget_mode: str
    budget_value: int
    shortlisted_destinations: list[dict[str, Any]]
    explained_shortlisted_destinations: list[dict[str, Any]]
    shortlist_cards: list[dict[str, Any]]
    selected_destination: dict[str, Any]
    shortlist_decision: str
    user_hint: str
    followup_questions: list[dict[str, Any]]
    current_followup_index: int
    followup_answers: list[dict[str, Any]]
    followup_custom_note: str
    followup_change_request: str
    final_brief: str
    final_action: str
    information_curator_complete: bool
    research_input: dict[str, Any]
    destination_research: DestinationResearch
    practical_travel_info: PracticalTravelInfo
    research_packet: dict[str, Any]
    research_validation: dict[str, Any]
    research_agent_output: dict[str, Any]
    citations: list[dict[str, Any]]
    research_warnings: list[str]
    compact_research: dict[str, Any]
    itinerary_input: ItineraryInput
    itinerary_run_id: str
    itinerary_artifact_dir: str
    trip_live_context: TripLiveContext
    trip_skeleton: TripSkeleton
    stay_base_plan: StayBasePlan
    transport_plan: TransportPlan
    day_planning_tasks: list[DayPlanningTask]
    day_planning_task: DayPlanningTask
    day_itinerary_packets: Annotated[list[DayItineraryPacket], merge_day_itinerary_packets]
    day_detail_refs: dict[str, dict[str, str]]
    day_markdown_refs: dict[str, dict[str, str]]
    booking_cost_notes: BookingCostNotes
    itinerary_section_tasks: list[dict[str, Any]]
    itinerary_section_task: dict[str, Any]
    itinerary_sections: Annotated[list[dict[str, Any]], merge_itinerary_sections]
    itinerary_section_refs: dict[str, dict[str, Any]]
    itinerary_brief_summary: dict[str, Any]
    itinerary_general_instructions: dict[str, Any]
    source_registry: Annotated[dict[str, dict[str, Any]], merge_source_registry]
    final_itinerary: FinalItinerary
    final_itinerary_markdown: str
    final_itinerary_markdown_ref: dict[str, str]
    final_markdown_ref: dict[str, str]
    itinerary_validation: ItineraryValidation
    itinerary_repair_plan: dict[str, Any]
    itinerary_view_ready: bool
