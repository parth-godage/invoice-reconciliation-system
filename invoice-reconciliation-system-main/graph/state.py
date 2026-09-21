"""
LangGraph State Schema for Invoice Reconciliation System

Defines the state that flows through the graph, containing:
- Input data (document path, purchase orders)
- Intermediate results from each agent
- Final resolution recommendation
- Error tracking
"""

from typing import TypedDict, List, Optional, Any, Dict
from dataclasses import asdict


# Import agent output types
from agents.document_agent import AgentOutput, InvoiceData as DocInvoiceData
from agents.matching_agent import MatchingResult
from agents.discrepancy_detection_agent import DiscrepancyDetectionResult
from agents.resolution_agent import ResolutionRecommendation
from models import PurchaseOrder, InvoiceData


class GraphState(TypedDict):
    """
    State schema for the invoice reconciliation graph.
    
    All fields are optional to allow incremental updates as the graph progresses.
    """
    # Inputs
    document_path: str
    purchase_orders: List[PurchaseOrder]
    
    # Document Agent outputs
    document_result: Optional[AgentOutput]
    extracted_invoice: Optional[InvoiceData]
    
    # Matching Agent outputs
    matching_result: Optional[MatchingResult]
    
    # Discrepancy Detection outputs
    discrepancy_result: Optional[DiscrepancyDetectionResult]
    
    # Resolution Agent outputs
    resolution_recommendation: Optional[ResolutionRecommendation]
    
    # Metadata and error handling
    errors: List[str]
    current_step: str
    execution_trace: List[str]  # Track execution path for debugging
