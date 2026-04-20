from typing import Any, TypedDict


class CitationRef(TypedDict, total=False):
    title: str
    url: str
    ref_type: str
    note: str


class ShortlistCard(TypedDict, total=False):
    card_title: str
    state_or_region: str
    trip_feel: str
    places_covered: list[str]
    highlights: list[str]
    best_for: str
    pace: str
    duration_fit: str
    why_it_fits: str
    estimated_price_range: str
    intent_match_reason: str
    difference_from_rejected: str


class DestinationKnowledgeCluster(TypedDict, total=False):
    name: str
    why_it_matters: str
    typical_time_need: str


class DestinationKnowledge(TypedDict, total=False):
    destination_overview: str
    key_place_clusters: list[DestinationKnowledgeCluster]
    how_to_reach: list[str]
    movement_within_destination: list[str]
    signature_experiences: list[str]
    local_food_highlights: list[str]
    planning_cautions: list[str]
    pace_signal: str
    citations: list[CitationRef]


class TravelEssentials(TypedDict, total=False):
    documents_and_permissions: list[str]
    packing_and_carry: list[str]
    local_dos: list[str]
    local_donts: list[str]
    safety_and_health: list[str]
    money_and_payments: list[str]
    connectivity_and_access: list[str]
    special_trip_notes: list[str]
    citations: list[CitationRef]


class ResearchPacket(TypedDict, total=False):
    destination_knowledge: DestinationKnowledge
    travel_essentials: TravelEssentials
    warnings: list[str]
    citations: list[CitationRef]


class ItineraryInput(TypedDict, total=False):
    research_input: dict[str, Any]
    planner_context: dict[str, Any]
    research_packet: ResearchPacket
    trip_summary: dict[str, Any]
    traveler_group: dict[str, Any]
    preferences: dict[str, Any]
    destination: dict[str, Any]
    warnings: list[str]
    source_refs: list[CitationRef]


class ItineraryValidation(TypedDict, total=False):
    valid: bool
    issues: list[str]
    repair_targets: list[str]
    repair_attempts: dict[str, int]


class FinalItinerary(TypedDict, total=False):
    trip_summary: dict[str, Any]
    how_to_reach: dict[str, Any]
    return_plan: dict[str, Any]
    stay_plan: dict[str, Any]
    local_transport: dict[str, Any]
    days: list[dict[str, Any]]
    cost_summary: dict[str, Any]
    carry_list: list[str]
    important_notes: list[str]
    documents: list[str]
    do_and_dont: list[str]
    source_notes: list[CitationRef]


# Legacy names kept as aliases so older imports fail gracefully during migration.
DestinationResearch = DestinationKnowledge
PracticalTravelInfo = TravelEssentials
DayItineraryPacket = dict[str, Any]
TripLiveContext = dict[str, Any]
TripSkeleton = dict[str, Any]
StayBasePlan = dict[str, Any]
BookingCostNotes = dict[str, Any]
TransportPlan = dict[str, Any]
DayPlanningTask = dict[str, Any]


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
    explained_shortlisted_destinations: list[ShortlistCard]
    shortlist_cards: list[ShortlistCard]
    rejected_shortlists: list[list[ShortlistCard]]
    shortlist_attempt_count: int
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
    destination_knowledge: DestinationKnowledge
    travel_essentials: TravelEssentials
    destination_research: DestinationResearch
    practical_travel_info: PracticalTravelInfo
    research_packet: ResearchPacket
    research_validation: dict[str, Any]
    research_agent_output: dict[str, Any]
    citations: list[dict[str, Any]]
    research_warnings: list[str]
    compact_research: dict[str, Any]
    itinerary_input: ItineraryInput
    itinerary_artifact_dir: str
    final_itinerary: FinalItinerary
    final_itinerary_markdown: str
    itinerary_validation: ItineraryValidation
    itinerary_view_ready: bool

    # Deprecated staged-itinerary fields retained for saved state compatibility.
    trip_live_context: TripLiveContext
    trip_skeleton: TripSkeleton
    stay_base_plan: StayBasePlan
    transport_plan: TransportPlan
    day_planning_tasks: list[DayPlanningTask]
    day_planning_task: DayPlanningTask
    day_itinerary_packets: list[DayItineraryPacket]
    day_detail_refs: dict[str, dict[str, str]]
    day_markdown_refs: dict[str, dict[str, str]]
    booking_cost_notes: BookingCostNotes
    itinerary_section_tasks: list[dict[str, Any]]
    itinerary_section_task: dict[str, Any]
    itinerary_sections: list[dict[str, Any]]
    itinerary_section_refs: dict[str, dict[str, Any]]
    itinerary_brief_summary: dict[str, Any]
    itinerary_general_instructions: dict[str, Any]
    source_registry: dict[str, dict[str, Any]]
    itinerary_repair_plan: dict[str, Any]
