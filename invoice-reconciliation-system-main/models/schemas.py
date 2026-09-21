from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime


@dataclass
class AgentResult:
    data: Dict[str, Any]
    confidence: float
    explanation: str


class ResolutionAction(Enum):
    APPROVE = "approve"
    REVIEW = "review"
    ESCALATE = "escalate"


@dataclass
class InvoiceData:
    """Structured invoice data - shared model for matching agent"""
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    total_amount: Optional[float] = None  # Alias for total, used by matching agent
    currency: Optional[str] = None
    line_items: List[Dict[str, Any]] = None
    payment_terms: Optional[str] = None
    raw_text: Optional[str] = None
    po_reference: Optional[str] = None  # PO reference from invoice

    def __post_init__(self):
        if self.line_items is None:
            self.line_items = []
        # Ensure total_amount is set if total is set
        if self.total_amount is None and self.total is not None:
            self.total_amount = self.total
        if self.total is None and self.total_amount is not None:
            self.total = self.total_amount


@dataclass
class PurchaseOrder:
    """Purchase Order data model"""
    po_number: str
    vendor_name: str
    total_amount: float
    po_date: datetime
    line_items: Optional[List[Dict[str, Any]]] = None
    vendor_address: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self):
        if self.line_items is None:
            self.line_items = []


@dataclass
class MatchingResult:
    """Result from Matching Agent"""
    matched_po: Optional[PurchaseOrder]
    confidence_score: float
    explanation: str
    matching_method: str  # "exact", "fuzzy", "none"
    match_details: Dict[str, Any]
