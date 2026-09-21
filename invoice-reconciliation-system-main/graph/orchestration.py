"""
LangGraph Orchestration for Invoice Reconciliation System

This module defines the complete graph workflow with:
- State management
- Node execution
- Conditional routing based on confidence scores and results
- Error handling
- Human review/escalation paths
"""

import hashlib
import logging
import uuid
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import GraphState
from graph.nodes import (
    extract_document_node,
    match_invoice_node,
    detect_discrepancies_node,
    resolve_node,
    approve_node,
    review_node,
    escalate_node,
    error_handler_node,
    no_match_handler_node,
)

logger = logging.getLogger(__name__)


def should_continue_after_extraction(
    state: GraphState,
) -> Literal["match_invoice", "human_review"]:
    """
    Conditional routing after document extraction.

    Routes to matching if confidence is sufficient,
    otherwise to human review.
    """

    document_result = state.get(
        "document_result"
    )

    errors = state.get(
        "errors",
        [],
    )

    # If there are errors, send to human review.
    if errors:
        return "human_review"

    # Check extraction confidence.
    if (
        document_result
        and document_result.confidence >= 0.3
    ):
        return "match_invoice"

    return "human_review"


def should_continue_after_matching(
    state: GraphState,
) -> Literal["detect_discrepancies", "no_match_handler"]:
    """
    Conditional routing after invoice matching.

    A successfully matched invoice proceeds to discrepancy
    detection.

    An invoice with no PO match goes to the dedicated
    no-match handler.

    Matching execution errors also go to the no-match
    fallback path.
    """

    matching_result = state.get(
        "matching_result"
    )

    errors = state.get(
        "errors",
        [],
    )

    # If there are errors, handle them.
    if errors:
        return "no_match_handler"

    # If a match was found, run discrepancy detection.
    if (
        matching_result
        and matching_result.matched_po
    ):
        return "detect_discrepancies"

    # No match found.
    return "no_match_handler"


def route_after_resolution(
    state: GraphState,
) -> Literal["approve", "review", "escalate"]:
    """
    Conditional routing after resolution recommendation.

    Routes based on the recommended action from the
    Resolution Agent.
    """

    resolution = state.get(
        "resolution_recommendation"
    )

    errors = state.get(
        "errors",
        [],
    )

    # If there are errors, always escalate.
    if errors:
        return "escalate"

    if not resolution:
        return "escalate"

    action = resolution.action.value

    if action == "approve":
        return "approve"

    if action == "review":
        return "review"

    # Default / escalate.
    return "escalate"


def create_reconciliation_graph() -> StateGraph:
    """
    Create and configure the invoice reconciliation graph.

    Graph structure:

        START
          |
          v
    extract_document
          |
          +---- low confidence/error ---> review
          |
          v
    match_invoice
          |
          +---- no match/error --------> no_match_handler
          |
          v
    detect_discrepancies
          |
          v
        resolve
          |
          +---- APPROVE ---> approve ---> END
          |
          +---- REVIEW ----> review ----> END
          |
          +---- ESCALATE --> escalate --> END

    The no-match handler is kept as a dedicated fallback
    for invoices where no PO can be matched.
    """

    # Create graph.
    workflow = StateGraph(
        GraphState
    )

    # --------------------------------------------------------
    # NODES
    # --------------------------------------------------------

    workflow.add_node(
        "extract_document",
        extract_document_node,
    )

    workflow.add_node(
        "match_invoice",
        match_invoice_node,
    )

    workflow.add_node(
        "detect_discrepancies",
        detect_discrepancies_node,
    )

    workflow.add_node(
        "resolve",
        resolve_node,
    )

    workflow.add_node(
        "approve",
        approve_node,
    )

    workflow.add_node(
        "review",
        review_node,
    )

    workflow.add_node(
        "escalate",
        escalate_node,
    )

    workflow.add_node(
        "error_handler",
        error_handler_node,
    )

    workflow.add_node(
        "no_match_handler",
        no_match_handler_node,
    )

    # --------------------------------------------------------
    # ENTRY POINT
    # --------------------------------------------------------

    workflow.set_entry_point(
        "extract_document"
    )

    # --------------------------------------------------------
    # AFTER EXTRACTION
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "extract_document",
        should_continue_after_extraction,
        {
            "match_invoice": "match_invoice",
            "human_review": "review",
        },
    )

    # --------------------------------------------------------
    # AFTER MATCHING
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "match_invoice",
        should_continue_after_matching,
        {
            "detect_discrepancies": (
                "detect_discrepancies"
            ),
            "no_match_handler": (
                "no_match_handler"
            ),
        },
    )

    # --------------------------------------------------------
    # DISCREPANCY DETECTION -> RESOLUTION
    # --------------------------------------------------------

    workflow.add_edge(
        "detect_discrepancies",
        "resolve",
    )

    # --------------------------------------------------------
    # RESOLUTION -> FINAL ACTION
    # --------------------------------------------------------

    workflow.add_conditional_edges(
        "resolve",
        route_after_resolution,
        {
            "approve": "approve",
            "review": "review",
            "escalate": "escalate",
        },
    )

    # --------------------------------------------------------
    # NO MATCH FALLBACK
    # --------------------------------------------------------
    #
    # Keep the existing behavior:
    # no_match_handler -> escalate.
    #
    # The no_match_handler itself creates the missing PO
    # discrepancy and resolution recommendation where needed.
    #

    workflow.add_edge(
        "no_match_handler",
        "escalate",
    )

    # --------------------------------------------------------
    # TERMINAL NODES
    # --------------------------------------------------------

    workflow.add_edge(
        "approve",
        END,
    )

    workflow.add_edge(
        "review",
        END,
    )

    workflow.add_edge(
        "escalate",
        END,
    )

    # Error handler fallback.
    workflow.add_edge(
        "error_handler",
        "escalate",
    )

    return workflow


def compile_graph(
    checkpoint_memory: bool = True,
):
    """
    Compile the graph with optional checkpointing.

    Args:
        checkpoint_memory:
            If True, enable in-memory checkpointing.

    Returns:
        Compiled graph ready for execution.
    """

    graph = create_reconciliation_graph()

    if checkpoint_memory:

        # Enable checkpointing for state persistence.
        memory = MemorySaver()

        compiled = graph.compile(
            checkpointer=memory
        )

    else:

        compiled = graph.compile()

    return compiled


def run_reconciliation(
    document_path: str,
    purchase_orders: list,
    checkpoint_memory: bool = True,
) -> dict:
    """
    Execute the complete invoice reconciliation workflow.

    Args:
        document_path:
            Path to invoice document (PDF/image).

        purchase_orders:
            List of PurchaseOrder objects.

        checkpoint_memory:
            Enable in-memory checkpointing.

    Returns:
        Final state dictionary with all results.
    """

    # --------------------------------------------------------
    # COMPILE GRAPH
    # --------------------------------------------------------

    graph = compile_graph(
        checkpoint_memory=checkpoint_memory
    )

    # --------------------------------------------------------
    # INITIAL STATE
    # --------------------------------------------------------

    initial_state: GraphState = {
        "document_path": document_path,
        "purchase_orders": purchase_orders,
        "document_result": None,
        "extracted_invoice": None,
        "matching_result": None,
        "discrepancy_result": None,
        "resolution_recommendation": None,
        "errors": [],
        "current_step": "start",
        "execution_trace": [],
    }

    # --------------------------------------------------------
    # EXECUTE GRAPH
    # --------------------------------------------------------

    try:

        if checkpoint_memory:

            # Generate a unique thread ID for this run.
            thread_id = hashlib.md5(
                f"{document_path}_{uuid.uuid4()}".encode()
            ).hexdigest()

            # LangGraph requires thread_id when checkpointing
            # is enabled.
            config = {
                "configurable": {
                    "thread_id": thread_id
                }
            }

            final_state = graph.invoke(
                initial_state,
                config=config,
            )

        else:

            # No checkpointing.
            final_state = graph.invoke(
                initial_state
            )

        return final_state

    except Exception as e:

        logger.error(
            f"Graph execution failed: {str(e)}",
            exc_info=True,
        )

        # Return an error state.
        error_state = initial_state.copy()

        error_state["errors"].append(
            f"Graph execution failed: {str(e)}"
        )

        error_state["current_step"] = (
            "error"
        )

        return error_state
