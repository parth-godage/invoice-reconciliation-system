"""
Strict Resolution Agent for Invoice Reconciliation System.

Business-aligned decision logic:

1. No discrepancies + exact PO match
       -> APPROVE

2. Price mismatch
       -> REVIEW when it is the only discrepancy
       -> ESCALATE when combined with another discrepancy

3. Critical / high severity discrepancy
       -> ESCALATE only for non-structural risk
       -> REVIEW for quantity/unit/missing/extra line-item issues

4. Missing PO / uncertain PO / fuzzy match
       -> REVIEW
       -> ESCALATE if combined with serious discrepancies

5. Quantity / unit / missing-line / extra-line discrepancy
       -> REVIEW

6. Multiple discrepancies
       -> REVIEW
       -> ESCALATE if risk is high

Auto-approval is allowed ONLY when the invoice is clean.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any
import logging


logger = logging.getLogger(__name__)


# ============================================================
# ENUMS
# ============================================================

class ResolutionAction(Enum):
    APPROVE = "approve"
    REVIEW = "review"
    ESCALATE = "escalate"


# ============================================================
# DISCREPANCY MODEL
# ============================================================

@dataclass
class DiscrepancyResult:
    field_name: str
    expected_value: Any
    actual_value: Any
    discrepancy_type: str
    confidence_score: float
    severity: Optional[str] = None
    description: Optional[str] = None


# ============================================================
# RESOLUTION MODEL
# ============================================================

@dataclass
class ResolutionRecommendation:
    action: ResolutionAction
    confidence_score: float
    explanation: str
    discrepancy_summary: Dict[str, Any]
    reasoning_steps: List[str]


# ============================================================
# RESOLUTION AGENT
# ============================================================

class ResolutionAgent:
    """
    Strict, deterministic, risk-aware resolution agent.

    IMPORTANT:
    This agent does NOT auto-approve invoices containing
    known discrepancies.
    """

    def resolve(
        self,
        discrepancies: List[Any],
        invoice_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ResolutionRecommendation:

        context = context or {}

        reasoning_steps: List[str] = []

        discrepancies = discrepancies or []

        # ====================================================
        # NORMALIZE DISCREPANCIES
        # ====================================================

        normalized = []

        for discrepancy in discrepancies:

            normalized.append(
                self._normalize_discrepancy(
                    discrepancy
                )
            )

        # ====================================================
        # CONTEXT SIGNALS
        # ====================================================

        match_method = self._get_context_value(
            context,
            "match_method",
            "matching_method",
            "method",
            default="",
        )

        match_method = str(
            match_method or ""
        ).strip().lower()

        has_fuzzy_match = (
            "fuzzy" in match_method
        )

        # Possible matching confidence
        matching_confidence = self._get_context_value(
            context,
            "matching_confidence",
            "match_confidence",
            default=None,
        )

        try:
            matching_confidence = (
                float(matching_confidence)
                if matching_confidence is not None
                else None
            )
        except Exception:
            matching_confidence = None

        # Missing PO signals
        has_missing_po = self._detect_missing_po(
            context
        )

        # ====================================================
        # DISCREPANCY FLAGS
        # ====================================================

        has_price_issue = False
        has_quantity_issue = False
        has_unit_issue = False
        has_missing_line_item = False
        has_extra_line_item = False

        has_high_severity = False
        has_critical_severity = False
        has_medium_severity = False

        discrepancy_types = []

        for d in normalized:

            dtype = str(
                d.get(
                    "discrepancy_type",
                    ""
                )
            ).lower()

            severity = str(
                d.get(
                    "severity",
                    ""
                )
            ).lower()

            discrepancy_types.append(
                dtype
            )

            # ------------------------------------------------
            # TYPE DETECTION
            # ------------------------------------------------

            if "price" in dtype:
                has_price_issue = True

            if "quantity" in dtype:
                has_quantity_issue = True

            if "unit" in dtype:
                has_unit_issue = True

            if (
                "missing_line_item" in dtype
                or "missing line item" in dtype
            ):
                has_missing_line_item = True

            if (
                "extra_line_item" in dtype
                or "extra line item" in dtype
            ):
                has_extra_line_item = True

            # ------------------------------------------------
            # SEVERITY DETECTION
            # ------------------------------------------------

            if "critical" in severity:
                has_critical_severity = True

            elif "high" in severity:
                has_high_severity = True

            elif "medium" in severity:
                has_medium_severity = True

        # ====================================================
        # OVERALL RISK
        # ====================================================

        total_discrepancies = len(
            normalized
        )

        serious_discrepancy = (
            has_critical_severity
            or has_high_severity
        )

        structural_discrepancy = (
            has_quantity_issue
            or has_unit_issue
            or has_missing_line_item
            or has_extra_line_item
        )

        # ====================================================
        # RULE 1
        # CRITICAL DISCREPANCY
        #
        # Highest priority.
        # ====================================================

        if has_critical_severity:

            reasoning_steps.append(
                "Critical discrepancy detected — "
                "automatic approval is prohibited."
            )

            # Structural quantity/unit/item discrepancies remain
            # REVIEW even when their numeric severity is high.
            # Compound price + structural risk is already handled
            # by the price rule above.
            if structural_discrepancy:

                reasoning_steps.append(
                    "The critical condition is associated with a "
                    "structural invoice-to-PO discrepancy."
                )

                return self._build_response(
                    action=ResolutionAction.REVIEW,
                    confidence=0.90,
                    reasoning_steps=reasoning_steps,
                    discrepancies=normalized,
                    invoice_id=invoice_id,
                    summary_reason=(
                        "Critical structural discrepancy requires "
                        "human verification."
                    ),
                )

            return self._build_response(
                action=ResolutionAction.ESCALATE,
                confidence=0.98,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Critical financial or unclassified risk "
                    "requires urgent manual review."
                ),
            )

        # ====================================================
        # RULE 2
        # PRICE MISMATCH
        #
        # Evaluation/business policy:
        # - Price-only discrepancy -> REVIEW
        # - Price + another discrepancy -> ESCALATE
        #
        # This prevents a single tolerated price variance from
        # being escalated while still escalating compound risk.
        # ====================================================

        if has_price_issue:

            reasoning_steps.append(
                "Price mismatch detected between invoice "
                "and purchase order."
            )

            reasoning_steps.append(
                "Financial amount differs from the "
                "approved purchase order."
            )

            if total_discrepancies >= 2:

                reasoning_steps.append(
                    "Price mismatch is combined with another "
                    "discrepancy, increasing financial risk."
                )

                return self._build_response(
                    action=ResolutionAction.ESCALATE,
                    confidence=0.95,
                    reasoning_steps=reasoning_steps,
                    discrepancies=normalized,
                    invoice_id=invoice_id,
                    summary_reason=(
                        "Price deviation combined with additional "
                        "invoice discrepancies requires escalation."
                    ),
                )

            reasoning_steps.append(
                "Price mismatch is the only detected discrepancy; "
                "manual verification is required."
            )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.90,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Price deviation requires human verification "
                    "before payment approval."
                ),
            )

        # ====================================================
        # RULE 3
        # HIGH SEVERITY
        # ====================================================

        if has_high_severity:

            reasoning_steps.append(
                "High-severity discrepancy detected."
            )

            # Quantity/unit/missing/extra discrepancies are REVIEW
            # by policy even when their percentage crosses the
            # numeric high-severity threshold.
            if structural_discrepancy:

                reasoning_steps.append(
                    "High numeric severity is attached to a "
                    "structural discrepancy; manual review is required."
                )

                return self._build_response(
                    action=ResolutionAction.REVIEW,
                    confidence=0.90,
                    reasoning_steps=reasoning_steps,
                    discrepancies=normalized,
                    invoice_id=invoice_id,
                    summary_reason=(
                        "High-severity structural discrepancy "
                        "requires human verification."
                    ),
                )

            reasoning_steps.append(
                "High-risk non-structural discrepancies require "
                "manual escalation."
            )

            return self._build_response(
                action=ResolutionAction.ESCALATE,
                confidence=0.93,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "High-severity financial or unclassified "
                    "risk requires escalation."
                ),
            )

        # ====================================================
        # RULE 4
        # MISSING PO
        # ====================================================

        if has_missing_po:

            reasoning_steps.append(
                "Invoice does not contain a reliable "
                "purchase-order reference."
            )

            if structural_discrepancy:

                reasoning_steps.append(
                    "PO uncertainty is combined with "
                    "line-item discrepancies."
                )

                return self._build_response(
                    action=ResolutionAction.ESCALATE,
                    confidence=0.88,
                    reasoning_steps=reasoning_steps,
                    discrepancies=normalized,
                    invoice_id=invoice_id,
                    summary_reason=(
                        "Missing PO reference combined with "
                        "structural invoice discrepancies."
                    ),
                )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.85,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "PO reference could not be deterministically "
                    "verified."
                ),
            )

        # ====================================================
        # RULE 5
        # FUZZY MATCH
        # ====================================================

        if has_fuzzy_match:

            reasoning_steps.append(
                "Purchase order was identified using "
                "fuzzy matching rather than an exact reference."
            )

            if matching_confidence is not None:

                reasoning_steps.append(
                    f"Matching confidence: "
                    f"{matching_confidence:.2f}."
                )

                # Very low confidence + fuzzy match
                if matching_confidence < 0.70:

                    reasoning_steps.append(
                        "Fuzzy match confidence is below "
                        "the safe verification threshold."
                    )

                    return self._build_response(
                        action=ResolutionAction.ESCALATE,
                        confidence=0.90,
                        reasoning_steps=reasoning_steps,
                        discrepancies=normalized,
                        invoice_id=invoice_id,
                        summary_reason=(
                            "Low-confidence fuzzy PO match "
                            "requires manual verification."
                        ),
                    )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.82,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Fuzzy PO matching requires human "
                    "verification before approval."
                ),
            )

        # ====================================================
        # RULE 6
        # MULTIPLE DISCREPANCIES
        # ====================================================

        if total_discrepancies >= 3:

            reasoning_steps.append(
                f"{total_discrepancies} discrepancies detected."
            )

            reasoning_steps.append(
                "Multiple discrepancies increase "
                "operational and financial risk."
            )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.90,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Multiple discrepancies require "
                    "human verification."
                ),
            )

        if total_discrepancies == 2:

            reasoning_steps.append(
                "Two discrepancies detected."
            )

            reasoning_steps.append(
                "Multiple issues prevent automatic approval."
            )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.85,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Multiple invoice discrepancies "
                    "require manual verification."
                ),
            )

        # ====================================================
        # RULE 7
        # MEDIUM SEVERITY
        # ====================================================

        if has_medium_severity:

            reasoning_steps.append(
                "Medium-severity discrepancy detected."
            )

            reasoning_steps.append(
                "Automatic approval is disabled when "
                "a discrepancy is present."
            )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.90,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Medium-severity discrepancy requires "
                    "human verification."
                ),
            )

        # ====================================================
        # RULE 8
        # STRUCTURAL DISCREPANCY
        #
        # This catches quantity/unit/missing/extra issues
        # even if severity was not provided correctly.
        # ====================================================

        if structural_discrepancy:

            reasoning_steps.append(
                "Structural invoice-to-PO discrepancy detected."
            )

            reasoning_steps.append(
                "Quantity, unit, missing-item, or extra-item "
                "differences prevent automatic approval."
            )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.88,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Structural discrepancy requires "
                    "manual verification."
                ),
            )

        # ====================================================
        # RULE 9
        # ANY OTHER DISCREPANCY
        #
        # Safety rule:
        # if anything is detected, never blindly approve.
        # ====================================================

        if total_discrepancies > 0:

            reasoning_steps.append(
                f"{total_discrepancies} discrepancy detected."
            )

            reasoning_steps.append(
                "Unclassified discrepancy detected; "
                "automatic approval is disabled."
            )

            return self._build_response(
                action=ResolutionAction.REVIEW,
                confidence=0.80,
                reasoning_steps=reasoning_steps,
                discrepancies=normalized,
                invoice_id=invoice_id,
                summary_reason=(
                    "Invoice contains a discrepancy that "
                    "requires manual verification."
                ),
            )

        # ====================================================
        # RULE 10
        # CLEAN INVOICE
        #
        # ONLY situation where APPROVE is allowed.
        # ====================================================

        reasoning_steps.append(
            "No discrepancies detected."
        )

        reasoning_steps.append(
            "Invoice passed the discrepancy checks."
        )

        reasoning_steps.append(
            "Automatic approval is allowed because "
            "no financial or structural risk was detected."
        )

        return self._build_response(
            action=ResolutionAction.APPROVE,
            confidence=0.95,
            reasoning_steps=reasoning_steps,
            discrepancies=normalized,
            invoice_id=invoice_id,
            summary_reason=(
                "Invoice meets all automatic-approval criteria."
            ),
        )

    # ========================================================
    # NORMALIZE DISCREPANCY
    # ========================================================

    @staticmethod
    def _normalize_discrepancy(
        discrepancy: Any,
    ) -> Dict[str, Any]:

        if discrepancy is None:
            return {}

        # ----------------------------------------------------
        # Dictionary
        # ----------------------------------------------------

        if isinstance(
            discrepancy,
            dict,
        ):

            discrepancy_type = (
                discrepancy.get(
                    "discrepancy_type",
                    ""
                )
            )

            severity = (
                discrepancy.get(
                    "severity",
                    ""
                )
            )

            confidence = (
                discrepancy.get(
                    "confidence_score",
                    discrepancy.get(
                        "confidence",
                        0.0
                    ),
                )
            )

            return {
                "field_name":
                    discrepancy.get(
                        "field_name"
                    ),

                "expected_value":
                    discrepancy.get(
                        "expected_value",
                        discrepancy.get(
                            "po_value"
                        ),
                    ),

                "actual_value":
                    discrepancy.get(
                        "actual_value",
                        discrepancy.get(
                            "invoice_value"
                        ),
                    ),

                "discrepancy_type":
                    ResolutionAgent._normalize_enum(
                        discrepancy_type
                    ),

                "confidence_score":
                    ResolutionAgent._safe_float(
                        confidence
                    ),

                "severity":
                    ResolutionAgent._normalize_enum(
                        severity
                    ),

                "description":
                    discrepancy.get(
                        "description",
                        discrepancy.get(
                            "explanation"
                        ),
                    ),
            }

        # ----------------------------------------------------
        # Object
        # ----------------------------------------------------

        discrepancy_type = getattr(
            discrepancy,
            "discrepancy_type",
            "",
        )

        severity = getattr(
            discrepancy,
            "severity",
            "",
        )

        confidence = getattr(
            discrepancy,
            "confidence_score",
            getattr(
                discrepancy,
                "confidence",
                0.0,
            ),
        )

        return {

            "field_name":
                getattr(
                    discrepancy,
                    "field_name",
                    getattr(
                        discrepancy,
                        "item_id",
                        None,
                    ),
                ),

            "expected_value":
                getattr(
                    discrepancy,
                    "expected_value",
                    getattr(
                        discrepancy,
                        "po_value",
                        None,
                    ),
                ),

            "actual_value":
                getattr(
                    discrepancy,
                    "actual_value",
                    getattr(
                        discrepancy,
                        "invoice_value",
                        None,
                    ),
                ),

            "discrepancy_type":
                ResolutionAgent._normalize_enum(
                    discrepancy_type
                ),

            "confidence_score":
                ResolutionAgent._safe_float(
                    confidence
                ),

            "severity":
                ResolutionAgent._normalize_enum(
                    severity
                ),

            "description":
                getattr(
                    discrepancy,
                    "description",
                    getattr(
                        discrepancy,
                        "explanation",
                        None,
                    ),
                ),
        }

    # ========================================================
    # ENUM NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_enum(
        value: Any,
    ) -> str:

        if value is None:
            return ""

        # Python Enum
        if isinstance(
            value,
            Enum,
        ):

            try:
                value = value.value
            except Exception:
                value = value.name

        # Enum-like object
        elif hasattr(
            value,
            "value",
        ):

            try:
                value = value.value
            except Exception:
                pass

        value = str(
            value
        ).strip().lower()

        # Examples:
        #
        # DiscrepancyType.QUANTITY_MISMATCH
        # Severity.MEDIUM
        #
        if "." in value:
            value = value.split(
                "."
            )[-1]

        return value

    # ========================================================
    # MISSING PO DETECTION
    # ========================================================

    @staticmethod
    def _detect_missing_po(
        context: Dict[str, Any],
    ) -> bool:

        # Explicit boolean signals
        for key in [
            "missing_po",
            "po_missing",
            "missing_po_reference",
            "po_reference_missing",
        ]:

            value = context.get(
                key
            )

            if value is True:
                return True

        # PO number/reference
        for key in [
            "po_number",
            "purchase_order_number",
            "po_reference",
            "purchase_order_reference",
        ]:

            if key in context:

                value = context.get(
                    key
                )

                if value is None:
                    return True

                if str(
                    value
                ).strip() == "":
                    return True

        # Check discrepancies passed directly
        # through context
        discrepancy_types = context.get(
            "discrepancy_types",
            [],
        )

        if discrepancy_types:

            for dtype in discrepancy_types:

                dtype = str(
                    dtype
                ).lower()

                if (
                    "missing_po" in dtype
                    or "po_missing" in dtype
                ):
                    return True

        return False

    # ========================================================
    # CONTEXT VALUE
    # ========================================================

    @staticmethod
    def _get_context_value(
        context: Dict[str, Any],
        *keys,
        default=None,
    ):

        for key in keys:

            if key in context:

                value = context.get(
                    key
                )

                if value is not None:
                    return value

        return default

    # ========================================================
    # SAFE FLOAT
    # ========================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> float:

        try:

            return float(
                value
            )

        except Exception:

            return 0.0

    # ========================================================
    # BUILD RESPONSE
    # ========================================================

    def _build_response(
        self,
        action: ResolutionAction,
        confidence: float,
        reasoning_steps: List[str],
        discrepancies: List[Any],
        invoice_id: Optional[str],
        summary_reason: str,
    ) -> ResolutionRecommendation:

        confidence = min(
            1.0,
            max(
                0.0,
                float(confidence)
            )
        )

        # ----------------------------------------------------
        # Discrepancy type summary
        # ----------------------------------------------------

        types = []

        for discrepancy in discrepancies:

            if isinstance(
                discrepancy,
                dict,
            ):

                dtype = discrepancy.get(
                    "discrepancy_type"
                )

            else:

                dtype = getattr(
                    discrepancy,
                    "discrepancy_type",
                    None,
                )

            dtype = self._normalize_enum(
                dtype
            )

            if dtype and dtype not in types:

                types.append(
                    dtype
                )

        # ----------------------------------------------------
        # Explanation
        # ----------------------------------------------------

        explanation = (
            f"Resolution recommendation for "
            f"invoice {invoice_id or ''}: "
            f"{action.value.upper()}\n\n"
            f"Reason: {summary_reason}\n\n"
            "Reasoning:\n"
            +
            "\n".join(
                f"- {step}"
                for step in reasoning_steps
            )
        )

        # ----------------------------------------------------
        # Logging
        # ----------------------------------------------------

        logger.info(
            "Resolution completed: "
            "action=%s, confidence=%.2f, "
            "discrepancies=%d",
            action.value,
            confidence,
            len(discrepancies),
        )

        # ----------------------------------------------------
        # Return
        # ----------------------------------------------------

        return ResolutionRecommendation(

            action=action,

            confidence_score=confidence,

            explanation=explanation,

            discrepancy_summary={
                "total_discrepancies":
                    len(discrepancies),

                "types":
                    types,
            },

            reasoning_steps=
                reasoning_steps,
        )