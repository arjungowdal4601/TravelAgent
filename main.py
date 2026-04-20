from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from schemas.travel_state import TravelState
from nodes.ask_half_baked_plan import ask_half_baked_plan
from nodes.await_shortlist_decision import await_shortlist_decision
from nodes.call_destination_research import call_destination_research
from nodes.call_destination_research_with_user_hint import (
    call_destination_research_with_user_hint,
)
from nodes.call_generate_contextual_destination_questions import (
    call_generate_contextual_destination_questions,
)
from nodes.collect_custom_followup_input import collect_custom_followup_input
from nodes.collect_followup_answers import collect_followup_answers
from nodes.build_shortlist_cards import build_shortlist_cards
from nodes.handoff_to_parent_graph import handoff_to_parent_graph
from nodes.itinerary_agent import (
    itinerary_planner,
    prepare_itinerary_input,
    render_clean_itinerary_markdown,
    show_separate_itinerary_view,
)
from nodes.review_followup_summary import review_followup_summary
from nodes.research_agent import (
    destination_knowledge_agent,
    normalize_research_input,
    research_agent_output,
    research_aggregator,
    travel_essentials_agent,
    validate_research_packet,
)
from nodes.routing import (
    route_final_action,
    route_followup_progress,
    route_research_validation,
    route_shortlist_decision,
)


def build_graph():
    graph = StateGraph(TravelState)
    graph.add_node("call_destination_research", call_destination_research)
    graph.add_node("build_shortlist_cards", build_shortlist_cards)
    graph.add_node("await_shortlist_decision", await_shortlist_decision)
    graph.add_node("ask_half_baked_plan", ask_half_baked_plan)
    graph.add_node(
        "call_destination_research_with_user_hint",
        call_destination_research_with_user_hint,
    )
    graph.add_node(
        "call_generate_contextual_destination_questions",
        call_generate_contextual_destination_questions,
    )
    graph.add_node("collect_followup_answers", collect_followup_answers)
    graph.add_node("collect_custom_followup_input", collect_custom_followup_input)
    graph.add_node("review_followup_summary", review_followup_summary)

    graph.add_node("handoff_to_parent_graph", handoff_to_parent_graph)
    graph.add_node("normalize_research_input", normalize_research_input)
    graph.add_node("destination_knowledge_agent", destination_knowledge_agent)
    graph.add_node("travel_essentials_agent", travel_essentials_agent)
    graph.add_node("research_aggregator", research_aggregator)
    graph.add_node("validate_research_packet", validate_research_packet)
    graph.add_node("research_agent_output", research_agent_output)
    graph.add_node("prepare_itinerary_input", prepare_itinerary_input)
    graph.add_node("itinerary_planner", itinerary_planner)
    graph.add_node("render_clean_itinerary_markdown", render_clean_itinerary_markdown)
    graph.add_node("show_separate_itinerary_view", show_separate_itinerary_view)

    graph.add_edge(START, "call_destination_research")
    graph.add_edge("call_destination_research", "build_shortlist_cards")
    graph.add_edge("build_shortlist_cards", "await_shortlist_decision")
    graph.add_conditional_edges(
        "await_shortlist_decision",
        route_shortlist_decision,
        {
            "call_generate_contextual_destination_questions": "call_generate_contextual_destination_questions",
            "ask_half_baked_plan": "ask_half_baked_plan",
        },
    )

    graph.add_edge("ask_half_baked_plan", "call_destination_research_with_user_hint")
    graph.add_edge(
        "call_destination_research_with_user_hint",
        "build_shortlist_cards",
    )

    graph.add_edge(
        "call_generate_contextual_destination_questions",
        "collect_followup_answers",
    )
    graph.add_conditional_edges(
        "collect_followup_answers",
        route_followup_progress,
        {
            "collect_followup_answers": "collect_followup_answers",
            "collect_custom_followup_input": "collect_custom_followup_input",
        },
    )
    graph.add_edge("collect_custom_followup_input", "review_followup_summary")
    graph.add_conditional_edges(
        "review_followup_summary",
        route_final_action,
        {
            "handoff_to_parent_graph": "handoff_to_parent_graph",
            END: END,
        },
    )

    graph.add_edge("handoff_to_parent_graph", "normalize_research_input")
    graph.add_edge("normalize_research_input", "destination_knowledge_agent")
    graph.add_edge("destination_knowledge_agent", "travel_essentials_agent")
    graph.add_edge("travel_essentials_agent", "research_aggregator")
    graph.add_edge("research_aggregator", "validate_research_packet")
    graph.add_conditional_edges(
        "validate_research_packet",
        route_research_validation,
        {
            "destination_knowledge_agent": "destination_knowledge_agent",
            "travel_essentials_agent": "travel_essentials_agent",
            "research_aggregator": "research_aggregator",
            "prepare_itinerary_input": "prepare_itinerary_input",
            END: END,
        },
    )
    graph.add_edge("prepare_itinerary_input", "itinerary_planner")
    graph.add_edge("itinerary_planner", "render_clean_itinerary_markdown")
    graph.add_edge("render_clean_itinerary_markdown", "show_separate_itinerary_view")
    graph.add_edge("show_separate_itinerary_view", END)

    return graph.compile(checkpointer=InMemorySaver())


travel_graph = build_graph()
