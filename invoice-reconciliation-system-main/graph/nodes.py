"""
Graph Nodes for Invoice Reconciliation System

Each node represents a step in the reconciliation process.
Nodes are kept simple and delegate business logic to agent classes.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from decimal import Decimal

from graph.state import GraphState

from agents.document_agent import (
    DocumentIntelligenceAgent,
)

from agents.matching_agent import (
    MatchingAgent,
)

from agents.discrepancy_detection_agent import (
    DiscrepancyDetectionAgent,
    LineItem as DiscLineItem,
)

from agents.resolution_agent import (
    ResolutionAgent,
    ResolutionAction,
    DiscrepancyResult,
)

from models import (
    InvoiceData,
    PurchaseOrder,
)


logger = logging.getLogger(__name__)


# ============================================================
# EXECUTION TRACE
# ============================================================

def _ensure_execution_trace(
    state: GraphState,
) -> None:
    """
    Ensure execution_trace and errors exist.
    """

    if (
        "execution_trace" not in state
        or state.get("execution_trace") is None
    ):
        state["execution_trace"] = []

    if "errors" not in state:
        state["errors"] = []


# ============================================================
# DOCUMENT EXTRACTION
# ============================================================

def extract_document_node(
    state: GraphState,
) -> GraphState:
    """
    Extract structured invoice information from PDF.
    """

    _ensure_execution_trace(state)

    state["current_step"] = "extract_document"

    state["execution_trace"].append(
        "extract_document"
    )

    try:

        document_path = state.get(
            "document_path"
        )

        if not document_path:

            error_msg = (
                "document_path is required "
                "but not provided"
            )

            state["errors"].append(
                error_msg
            )

            logger.error(error_msg)

            return state

        # ----------------------------------------------------
        # DOCUMENT AGENT
        # ----------------------------------------------------

        doc_agent = (
            DocumentIntelligenceAgent()
        )

        document_result = (
            doc_agent.process(
                document_path
            )
        )

        state["document_result"] = (
            document_result
        )

        # ----------------------------------------------------
        # CONFIDENCE CHECK
        # ----------------------------------------------------

        if document_result.confidence < 0.3:

            error_msg = (
                "Document extraction failed "
                f"with low confidence: "
                f"{document_result.confidence}"
            )

            state["errors"].append(
                error_msg
            )

            logger.warning(
                error_msg
            )

            return state

        # ----------------------------------------------------
        # CONVERT TO SYSTEM MODEL
        # ----------------------------------------------------

        doc_data = document_result.data

        extracted_invoice = (
            _convert_to_invoice_data(
                doc_data,
                document_result,
            )
        )

        state["extracted_invoice"] = (
            extracted_invoice
        )

        logger.info(
            "Document extraction completed "
            "with confidence: %.2f",
            document_result.confidence,
        )

    except Exception as e:

        error_msg = (
            f"Error in document extraction: {e}"
        )

        state["errors"].append(
            error_msg
        )

        logger.error(
            error_msg,
            exc_info=True,
        )

    return state


# ============================================================
# PURCHASE ORDER MATCHING
# ============================================================

def match_invoice_node(
    state: GraphState,
) -> GraphState:
    """
    Match extracted invoice against purchase orders.
    """

    _ensure_execution_trace(state)

    state["current_step"] = (
        "match_invoice"
    )

    state["execution_trace"].append(
        "match_invoice"
    )

    try:

        invoice = state.get(
            "extracted_invoice"
        )

        purchase_orders = state.get(
            "purchase_orders",
            [],
        )

        if not invoice:

            error_msg = (
                "extracted_invoice is required "
                "but not provided"
            )

            state["errors"].append(
                error_msg
            )

            logger.error(error_msg)

            return state

        if not purchase_orders:

            error_msg = (
                "purchase_orders list is empty"
            )

            state["errors"].append(
                error_msg
            )

            logger.warning(error_msg)

            return state

        # ----------------------------------------------------
        # MATCHING AGENT
        # ----------------------------------------------------

        matching_agent = (
            MatchingAgent()
        )

        matching_result = (
            matching_agent.match(
                invoice,
                purchase_orders,
            )
        )

        state["matching_result"] = (
            matching_result
        )

        logger.info(
            "Matching completed: "
            "method=%s, confidence=%.2f",
            matching_result.matching_method,
            matching_result.confidence_score,
        )

    except Exception as e:

        error_msg = (
            f"Error in invoice matching: {e}"
        )

        state["errors"].append(
            error_msg
        )

        logger.error(
            error_msg,
            exc_info=True,
        )

    return state


# ============================================================
# DISCREPANCY DETECTION
# ============================================================

def detect_discrepancies_node(
    state: GraphState,
) -> GraphState:
    """
    Detect invoice-vs-PO discrepancies.

    IMPORTANT:
    A missing PO reference is a first-class discrepancy.

    If the invoice does not contain a reliable PO reference,
    this node creates ``missing_po_reference`` BEFORE considering
    any inferred PO match from the Matching Agent.

    This prevents vendor/amount/date-based matching from hiding
    the fact that the invoice itself has no PO reference.
    """

    _ensure_execution_trace(state)

    state["current_step"] = "detect_discrepancies"

    state["execution_trace"].append(
        "detect_discrepancies"
    )

    try:

        invoice = state.get(
            "extracted_invoice"
        )

        matching_result = state.get(
            "matching_result"
        )

        if not invoice:

            error_msg = (
                "extracted_invoice is required "
                "but not provided"
            )

            state["errors"].append(
                error_msg
            )

            logger.error(error_msg)

            return state

        # ========================================================
        # PO REFERENCE CHECK
        # ========================================================
        #
        # Check the invoice's actual PO reference BEFORE using
        # the Matching Agent's matched_po.
        #
        # This distinction is important:
        #
        #   po_reference -> explicitly present on invoice
        #   matched_po    -> PO inferred/found by Matching Agent
        #
        # An inferred PO must never erase a missing PO reference.
        #

        po_reference = getattr(
            invoice,
            "po_reference",
            None,
        )

        normalized_po_reference = (
            str(po_reference).strip()
            if po_reference is not None
            else ""
        )

        # Treat common empty/OCR placeholder values as missing.
        missing_po_reference = (
            not normalized_po_reference
            or normalized_po_reference.lower()
            in {
                "none",
                "null",
                "n/a",
                "na",
                "unknown",
                "not available",
                "not_available",
                "not applicable",
                "not_applicable",
                "-",
            }
        )

        # ========================================================
        # MISSING PO REFERENCE
        # ========================================================
        #
        # This branch intentionally executes even when the
        # Matching Agent has inferred a PO.
        #

        if missing_po_reference:

            logger.warning(
                "Invoice has no reliable PO reference. "
                "Creating missing PO discrepancy. "
                "Ignoring inferred PO match for discrepancy flow."
            )

            missing_po_discrepancy = (
                DiscrepancyResult(
                    field_name="po_reference",

                    expected_value=(
                        "Valid PO reference"
                    ),

                    actual_value=(
                        po_reference
                    ),

                    discrepancy_type=(
                        "missing_po_reference"
                    ),

                    confidence_score=0.98,

                    severity="medium",

                    description=(
                        "Invoice does not contain "
                        "a reliable purchase-order "
                        "reference. Any inferred PO "
                        "match is not treated as a valid "
                        "PO reference."
                    ),
                )
            )

            state["discrepancy_result"] = (
                _build_manual_discrepancy_result(
                    [
                        missing_po_discrepancy
                    ]
                )
            )

            logger.info(
                "Missing PO discrepancy created "
                "because invoice PO reference is absent."
            )

            return state

        # ========================================================
        # PO REFERENCE EXISTS BUT NO MATCH
        # ========================================================

        if (
            not matching_result
            or not matching_result.matched_po
        ):

            logger.warning(
                "Invoice contains a PO reference, "
                "but no matching PO was found. "
                "Creating missing PO discrepancy."
            )

            missing_po_discrepancy = (
                DiscrepancyResult(
                    field_name="po_reference",

                    expected_value=(
                        "Valid PO reference"
                    ),

                    actual_value=(
                        po_reference
                    ),

                    discrepancy_type=(
                        "missing_po_reference"
                    ),

                    confidence_score=0.98,

                    severity="medium",

                    description=(
                        "Invoice contains a PO reference, "
                        "but no corresponding purchase "
                        "order could be reliably matched."
                    ),
                )
            )

            state["discrepancy_result"] = (
                _build_manual_discrepancy_result(
                    [
                        missing_po_discrepancy
                    ]
                )
            )

            logger.info(
                "Missing PO discrepancy created "
                "because no matching PO was found."
            )

            return state

        # ========================================================
        # MATCHED PO
        # ========================================================

        matched_po = (
            matching_result.matched_po
        )

        invoice_items = (
            _convert_to_discrepancy_line_items(
                invoice.line_items or []
            )
        )

        po_items = (
            _convert_to_discrepancy_line_items(
                matched_po.line_items or []
            )
        )

        # ========================================================
        # DISCREPANCY AGENT
        # ========================================================

        discrepancy_agent = (
            DiscrepancyDetectionAgent()
        )

        discrepancy_result = (
            discrepancy_agent.detect_discrepancies(
                invoice_items=invoice_items,
                po_items=po_items,
            )
        )

        state["discrepancy_result"] = (
            discrepancy_result
        )

        logger.info(
            "Discrepancy detection completed: "
            "%d discrepancies found, "
            "confidence=%.2f",
            discrepancy_result.total_discrepancies,
            discrepancy_result.overall_confidence,
        )

    except Exception as e:

        error_msg = (
            f"Error in discrepancy detection: {e}"
        )

        state["errors"].append(
            error_msg
        )

        logger.error(
            error_msg,
            exc_info=True,
        )

    return state


# ============================================================
# RESOLUTION
# ============================================================

def resolve_node(
    state: GraphState,
) -> GraphState:
    """
    Generate final resolution recommendation.

    Passes all important matching context to the
    Resolution Agent:
        - PO reference
        - matching method
        - matching confidence
        - matched PO
    """

    _ensure_execution_trace(state)

    state["current_step"] = "resolve"

    state["execution_trace"].append(
        "resolve"
    )

    try:

        discrepancy_result = state.get(
            "discrepancy_result"
        )

        invoice = state.get(
            "extracted_invoice"
        )

        matching_result = state.get(
            "matching_result"
        )

        if not discrepancy_result:

            error_msg = (
                "discrepancy_result is required "
                "but not provided"
            )

            state["errors"].append(
                error_msg
            )

            logger.error(error_msg)

            return state

        # ----------------------------------------------------
        # CONVERT DISCREPANCIES
        # ----------------------------------------------------

        discrepancy_results = (
            _convert_to_resolution_discrepancies(
                discrepancy_result.discrepancies
            )
        )

        # ----------------------------------------------------
        # CONTEXT
        # ----------------------------------------------------

        context: Dict[str, Any] = {}

        # Invoice amount
        if invoice:

            if getattr(
                invoice,
                "total_amount",
                None,
            ) is not None:

                context["invoice_amount"] = (
                    invoice.total_amount
                )

        # ----------------------------------------------------
        # PO REFERENCE
        # ----------------------------------------------------

        po_reference = None

        if invoice:

            po_reference = getattr(
                invoice,
                "po_reference",
                None,
            )

        context["po_reference"] = (
            po_reference
        )

        context["missing_po"] = (
            not bool(
                str(
                    po_reference or ""
                ).strip()
            )
        )

        # ----------------------------------------------------
        # MATCHING INFORMATION
        # ----------------------------------------------------

        if matching_result:

            context["match_method"] = (
                getattr(
                    matching_result,
                    "matching_method",
                    "",
                )
            )

            context["matching_method"] = (
                getattr(
                    matching_result,
                    "matching_method",
                    "",
                )
            )

            context["matching_confidence"] = (
                getattr(
                    matching_result,
                    "confidence_score",
                    None,
                )
            )

            context["matched_po"] = (
                getattr(
                    matching_result,
                    "matched_po",
                    None,
                )
            )

        # ----------------------------------------------------
        # DISCREPANCY TYPES
        # ----------------------------------------------------

        context["discrepancy_types"] = [
            getattr(
                discrepancy,
                "discrepancy_type",
                "",
            ).value
            if hasattr(
                getattr(
                    discrepancy,
                    "discrepancy_type",
                    None,
                ),
                "value",
            )
            else str(
                getattr(
                    discrepancy,
                    "discrepancy_type",
                    "",
                )
            )
            for discrepancy in discrepancy_results
        ]

        # ----------------------------------------------------
        # MISSING PO FROM DISCREPANCIES
        # ----------------------------------------------------

        if any(
            "missing_po"
            in str(dtype).lower()
            for dtype in context[
                "discrepancy_types"
            ]
        ):

            context["missing_po"] = True

        # ----------------------------------------------------
        # RESOLUTION AGENT
        # ----------------------------------------------------

        invoice_id = (
            invoice.invoice_number
            if invoice
            else None
        )

        resolution_agent = (
            ResolutionAgent()
        )

        resolution_recommendation = (
            resolution_agent.resolve(
                discrepancies=
                    discrepancy_results,
                invoice_id=invoice_id,
                context=context,
            )
        )

        state[
            "resolution_recommendation"
        ] = resolution_recommendation

        logger.info(
            "Resolution completed: "
            "action=%s, confidence=%.2f",
            resolution_recommendation.action.value,
            resolution_recommendation.confidence_score,
        )

    except Exception as e:

        error_msg = (
            f"Error in resolution: {e}"
        )

        state["errors"].append(
            error_msg
        )

        logger.error(
            error_msg,
            exc_info=True,
        )

    return state


# ============================================================
# APPROVE
# ============================================================

def approve_node(
    state: GraphState,
) -> GraphState:

    _ensure_execution_trace(state)

    state["current_step"] = "approve"

    state["execution_trace"].append(
        "approve"
    )

    logger.info(
        "Invoice approved - "
        "reconciliation complete"
    )

    return state


# ============================================================
# REVIEW
# ============================================================

def review_node(
    state: GraphState,
) -> GraphState:

    _ensure_execution_trace(state)

    state["current_step"] = "review"

    state["execution_trace"].append(
        "review"
    )

    logger.info(
        "Invoice flagged for human review"
    )

    return state


# ============================================================
# ESCALATE
# ============================================================

def escalate_node(
    state: GraphState,
) -> GraphState:

    _ensure_execution_trace(state)

    state["current_step"] = "escalate"

    state["execution_trace"].append(
        "escalate"
    )

    logger.warning(
        "Invoice escalated - "
        "requires urgent manual review"
    )

    return state


# ============================================================
# ERROR HANDLER
# ============================================================

def error_handler_node(
    state: GraphState,
) -> GraphState:

    _ensure_execution_trace(state)

    state["current_step"] = (
        "error_handler"
    )

    state["execution_trace"].append(
        "error_handler"
    )

    errors = state.get(
        "errors",
        [],
    )

    logger.error(
        "Error handler invoked with "
        "%d error(s): %s",
        len(errors),
        errors,
    )

    return state


# ============================================================
# NO MATCH HANDLER
# ============================================================

def no_match_handler_node(
    state: GraphState,
) -> GraphState:
    """
    Handle invoices for which no PO can be matched.

    Missing/uncertain PO should normally be REVIEW,
    not automatic ESCALATE.
    """

    _ensure_execution_trace(state)

    state["current_step"] = (
        "no_match_handler"
    )

    state["execution_trace"].append(
        "no_match_handler"
    )

    invoice = state.get(
        "extracted_invoice"
    )

    invoice_id = (
        invoice.invoice_number
        if invoice
        else None
    )

    logger.warning(
        "No deterministic PO match found."
    )

    # --------------------------------------------------------
    # Create missing-PO discrepancy
    # --------------------------------------------------------

    discrepancy = (
        DiscrepancyResult(
            field_name="po_reference",
            expected_value="Valid PO reference",
            actual_value=(
                getattr(
                    invoice,
                    "po_reference",
                    None,
                )
                if invoice
                else None
            ),
            discrepancy_type=(
                "missing_po_reference"
            ),
            confidence_score=0.98,
            severity="medium",
            description=(
                "No reliable purchase-order "
                "reference or deterministic "
                "purchase-order match was found."
            ),
        )
    )

    # IMPORTANT:
    # Persist the manually-created discrepancy into GraphState.
    #
    # The no-match handler is a terminal fallback path and does not
    # pass through detect_discrepancies_node(). Without this assignment,
    # the discrepancy exists only as a local variable and is lost from
    # the final graph state. The evaluator therefore sees no
    # "missing_po_reference" discrepancy.
    state["discrepancy_result"] = (
        _build_manual_discrepancy_result(
            [discrepancy]
        )
    )

    logger.info(
        "Missing PO discrepancy persisted in GraphState."
    )

    resolution_agent = (
        ResolutionAgent()
    )

    recommendation = (
        resolution_agent.resolve(
            discrepancies=[
                discrepancy
            ],
            invoice_id=invoice_id,
            context={
                "missing_po": True,
                "po_reference": (
                    getattr(
                        invoice,
                        "po_reference",
                        None,
                    )
                    if invoice
                    else None
                ),
            },
        )
    )

    state[
        "resolution_recommendation"
    ] = recommendation

    return state


# ============================================================
# HELPER:
# DOCUMENT -> InvoiceData
# ============================================================

def _convert_to_invoice_data(
    doc_data: Dict[str, Any],
    agent_output,
) -> InvoiceData:
    """
    Convert Document Agent output to models.InvoiceData.
    """

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    invoice_date = None

    if doc_data.get("invoice_date"):

        try:

            date_value = (
                doc_data["invoice_date"]
            )

            if isinstance(
                date_value,
                datetime,
            ):

                invoice_date = (
                    date_value
                )

            else:

                date_str = str(
                    date_value
                ).strip()

                date_formats = [

                    "%Y-%m-%d",

                    "%m/%d/%Y",

                    "%d/%m/%Y",

                    "%Y/%m/%d",

                    "%d-%m-%Y",

                    "%Y-%m-%d %H:%M:%S",

                    "%m/%d/%Y %H:%M:%S",

                ]

                for fmt in date_formats:

                    try:

                        invoice_date = (
                            datetime.strptime(
                                date_str,
                                fmt,
                            )
                        )

                        break

                    except ValueError:
                        continue

                if invoice_date is None:

                    logger.warning(
                        "Could not parse "
                        "invoice_date: %s",
                        date_str,
                    )

        except Exception as e:

            logger.warning(
                "Error parsing invoice_date: %s",
                e,
            )

    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

    total_amount = None

    amounts = doc_data.get(
        "amounts",
        {},
    )

    if isinstance(
        amounts,
        dict,
    ):

        total_amount = amounts.get(
            "total"
        )

    # --------------------------------------------------------
    # PO REFERENCE
    # --------------------------------------------------------

    po_reference = (
        doc_data.get(
            "po_reference"
        )
    )

    # --------------------------------------------------------
    # VENDOR
    # --------------------------------------------------------

    vendor = doc_data.get(
        "vendor",
        {},
    )

    vendor_name = None
    vendor_address = None

    if isinstance(
        vendor,
        dict,
    ):

        vendor_name = vendor.get(
            "name"
        )

        vendor_address = vendor.get(
            "address"
        )

    # --------------------------------------------------------
    # CUSTOMER
    # --------------------------------------------------------

    customer = doc_data.get(
        "customer",
        {},
    )

    customer_name = None
    customer_address = None

    if isinstance(
        customer,
        dict,
    ):

        customer_name = customer.get(
            "name"
        )

        customer_address = customer.get(
            "address"
        )

    # --------------------------------------------------------
    # AMOUNTS
    # --------------------------------------------------------

    subtotal = None
    tax = None
    currency = None

    if isinstance(
        amounts,
        dict,
    ):

        subtotal = amounts.get(
            "subtotal"
        )

        tax = amounts.get(
            "tax"
        )

        currency = amounts.get(
            "currency"
        )

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

    return InvoiceData(

        invoice_number=
            doc_data.get(
                "invoice_number"
            ),

        invoice_date=
            invoice_date,

        due_date=
            doc_data.get(
                "due_date"
            ),

        vendor_name=
            vendor_name,

        vendor_address=
            vendor_address,

        customer_name=
            customer_name,

        customer_address=
            customer_address,

        subtotal=
            subtotal,

        tax=
            tax,

        total=
            total_amount,

        total_amount=
            total_amount,

        currency=
            currency,

        line_items=
            doc_data.get(
                "line_items",
                [],
            ),

        payment_terms=
            doc_data.get(
                "payment_terms"
            ),

        raw_text=
            doc_data.get(
                "raw_text_preview"
            ),

        po_reference=
            po_reference,
    )


# ============================================================
# HELPER:
# LINE ITEM CONVERSION
# ============================================================

def _convert_to_discrepancy_line_items(
    line_items: List[Dict[str, Any]],
) -> List[DiscLineItem]:
    """
    Convert invoice/PO line items into the
    Discrepancy Agent LineItem format.
    """

    converted_items = []

    for idx, item in enumerate(
        line_items
    ):

        if not isinstance(
            item,
            dict,
        ):

            continue

        # ----------------------------------------------------
        # ITEM ID
        # ----------------------------------------------------

        item_id = (
            item.get("item_id")
            or item.get("description")
            or f"ITEM-{idx + 1}"
        )

        # ----------------------------------------------------
        # NUMBERS
        # ----------------------------------------------------

        try:

            quantity = Decimal(
                str(
                    item.get(
                        "quantity",
                        0,
                    )
                )
            )

        except Exception:

            quantity = Decimal("0")

        try:

            unit_price = Decimal(
                str(
                    item.get(
                        "unit_price",
                        0,
                    )
                )
            )

        except Exception:

            unit_price = Decimal("0")

        # ----------------------------------------------------
        # UNIT
        # ----------------------------------------------------

        unit = item.get(
            "unit",
            "unit",
        )

        # ----------------------------------------------------
        # CREATE
        # ----------------------------------------------------

        converted_items.append(
            DiscLineItem(

                item_id=str(
                    item_id
                ),

                description=str(
                    item.get(
                        "description",
                        "",
                    )
                    or ""
                ),

                quantity=quantity,

                unit_price=unit_price,

                unit=str(
                    unit or "unit"
                ),

            )
        )

    return converted_items


# ============================================================
# HELPER:
# DISCREPANCY -> RESOLUTION
# ============================================================

def _convert_to_resolution_discrepancies(
    discrepancies,
) -> List[DiscrepancyResult]:
    """
    Convert DiscrepancyDetectionAgent results
    into ResolutionAgent format.
    """

    resolution_discrepancies = []

    for disc in (
        discrepancies or []
    ):

        discrepancy_type = getattr(
            disc,
            "discrepancy_type",
            "",
        )

        if hasattr(
            discrepancy_type,
            "value",
        ):

            discrepancy_type = (
                discrepancy_type.value
            )

        severity = getattr(
            disc,
            "severity",
            None,
        )

        if hasattr(
            severity,
            "value",
        ):

            severity = (
                severity.value
            )

        confidence = getattr(
            disc,
            "confidence",
            getattr(
                disc,
                "confidence_score",
                0.0,
            ),
        )

        resolution_discrepancies.append(

            DiscrepancyResult(

                field_name=str(
                    getattr(
                        disc,
                        "item_id",
                        "",
                    )
                ),

                expected_value=
                    getattr(
                        disc,
                        "po_value",
                        None,
                    ),

                actual_value=
                    getattr(
                        disc,
                        "invoice_value",
                        None,
                    ),

                discrepancy_type=
                    str(
                        discrepancy_type
                    ),

                confidence_score=
                    float(
                        confidence
                    ),

                severity=
                    str(
                        severity
                        or ""
                    ),

                description=
                    getattr(
                        disc,
                        "explanation",
                        None,
                    ),
            )
        )

    return resolution_discrepancies


# ============================================================
# HELPER:
# BUILD MANUAL DISCREPANCY RESULT
# ============================================================

def _build_manual_discrepancy_result(
    discrepancies: List[
        DiscrepancyResult
    ],
):
    """
    Lightweight compatible object for the
    no-match / missing-PO path.

    Uses the same fields consumed by resolve_node.
    """

    class ManualDiscrepancyResult:

        def __init__(
            self,
            items,
        ):

            self.discrepancies = items

            self.total_discrepancies = (
                len(items)
            )

            self.overall_confidence = (
                0.98
                if items
                else 0.95
            )

            self.summary = (
                "Missing PO reference detected."
                if items
                else "No discrepancies found."
            )

    return ManualDiscrepancyResult(
        discrepancies
    )