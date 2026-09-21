"""
Production Matching Agent for Invoice Reconciliation.

Matching priority:
1. Exact PO reference
2. Normalized PO reference
3. Strong evidence-based fuzzy matching
4. Safe vendor-only fallback
5. No-match when evidence is insufficient

Designed for:
- PO references such as PO-0003 and PO-2024-003
- Vendor name variations
- Small amount deviations
- Date variations
- Missing PO references
- Synthetic evaluation datasets
- Explainable matching decisions
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
import logging
import re

from models import InvoiceData, PurchaseOrder, MatchingResult


logger = logging.getLogger(__name__)


class MatchingAgent:
    """
    Intelligent invoice-to-PO matching agent.

    The agent is deliberately conservative:
    - Never lets weak fuzzy similarity masquerade as an exact match.
    - Never selects a random PO merely because one candidate has the
      highest score.
    - Exact PO references always have priority.
    """

    # ---------------------------------------------------------
    # CONFIDENCE / MATCHING CONFIGURATION
    # ---------------------------------------------------------

    EXACT_MATCH_CONFIDENCE = 1.00
    NORMALIZED_EXACT_CONFIDENCE = 0.98

    FUZZY_MATCH_CONFIDENCE_BASE = 0.60
    FUZZY_MATCH_CONFIDENCE_MAX = 0.95

    # Minimum evidence required for fuzzy matching
    MIN_FUZZY_CONFIDENCE = 0.76
    MIN_VENDOR_SIMILARITY = 0.85
    MIN_VENDOR_SIMILARITY_WITH_AMOUNT = 0.65

    # Amount tolerance = 2%
    AMOUNT_TOLERANCE_PERCENT = 0.02

    # Invoice and PO dates are considered close within 30 days
    DATE_TOLERANCE_DAYS = 30

    # Difference between best and second-best candidate
    # required to call a fuzzy match reliable.
    MIN_SCORE_MARGIN = 0.03

    # ---------------------------------------------------------
    # INITIALIZATION
    # ---------------------------------------------------------

    def __init__(
        self,
        exact_match_confidence: float = None,
        fuzzy_match_confidence_base: float = None,
        vendor_similarity_threshold: float = None,
        amount_tolerance_percent: float = None,
        date_tolerance_days: int = None,
    ):
        if exact_match_confidence is not None:
            self.EXACT_MATCH_CONFIDENCE = exact_match_confidence

        if fuzzy_match_confidence_base is not None:
            self.FUZZY_MATCH_CONFIDENCE_BASE = fuzzy_match_confidence_base

        if vendor_similarity_threshold is not None:
            self.MIN_VENDOR_SIMILARITY = vendor_similarity_threshold

        if amount_tolerance_percent is not None:
            self.AMOUNT_TOLERANCE_PERCENT = amount_tolerance_percent

        if date_tolerance_days is not None:
            self.DATE_TOLERANCE_DAYS = date_tolerance_days

    # =========================================================
    # PUBLIC API
    # =========================================================

    def match(
        self,
        invoice: InvoiceData,
        purchase_orders: List[PurchaseOrder],
    ) -> MatchingResult:
        """
        Match an invoice against available purchase orders.
        """

        try:
            # -------------------------------------------------
            # INPUT VALIDATION
            # -------------------------------------------------

            if not purchase_orders:
                return self._create_no_match_result(
                    "No purchase orders available for matching."
                )

            if invoice is None:
                return self._create_no_match_result(
                    "Invoice data is missing or invalid."
                )

            # -------------------------------------------------
            # STRATEGY 1 + 2:
            # EXACT / NORMALIZED PO REFERENCE
            # -------------------------------------------------

            if invoice.po_reference:
                exact_match = self._exact_match_by_po_reference(
                    invoice,
                    purchase_orders,
                )

                if exact_match:
                    return exact_match

            # -------------------------------------------------
            # STRATEGY 3:
            # EVIDENCE-BASED FUZZY MATCHING
            # -------------------------------------------------

            fuzzy_match = self._fuzzy_match(
                invoice,
                purchase_orders,
            )

            if fuzzy_match:
                return fuzzy_match

            # -------------------------------------------------
            # STRATEGY 4:
            # SAFE VENDOR FALLBACK
            # -------------------------------------------------

            vendor_match = self._vendor_only_match(
                invoice,
                purchase_orders,
            )

            if vendor_match:
                return vendor_match

            # -------------------------------------------------
            # NO MATCH
            # -------------------------------------------------

            return self._create_no_match_result(
                "No sufficiently reliable purchase order match found."
            )

        except Exception as exc:
            logger.error(
                "Error during invoice-to-PO matching: %s",
                exc,
                exc_info=True,
            )

            return self._create_no_match_result(
                f"Matching failed due to error: {exc}"
            )

    # =========================================================
    # EXACT PO MATCHING
    # =========================================================

    def _exact_match_by_po_reference(
        self,
        invoice: InvoiceData,
        purchase_orders: List[PurchaseOrder],
    ) -> Optional[MatchingResult]:
        """
        Match using the PO reference.

        Supports:
            PO-0003
            PO-2024-003

        Both normalize to the same logical PO identifier.
        """

        invoice_ref = self._normalize_po_reference(
            invoice.po_reference
        )

        if not invoice_ref:
            return None

        # -----------------------------------------------------
        # PASS 1:
        # TRUE STRING EXACT MATCH
        # -----------------------------------------------------

        invoice_raw = self._clean_po_reference(
            invoice.po_reference
        )

        for po in purchase_orders:

            po_raw = self._clean_po_reference(
                po.po_number
            )

            if invoice_raw and po_raw and invoice_raw == po_raw:

                explanation = (
                    f"Exact PO reference match: invoice reference "
                    f"'{invoice.po_reference}' matches PO "
                    f"'{po.po_number}'."
                )

                return MatchingResult(
                    matched_po=po,
                    confidence_score=self.EXACT_MATCH_CONFIDENCE,
                    explanation=explanation,
                    matching_method="exact",
                    match_details={
                        "po_reference": invoice.po_reference,
                        "po_number": po.po_number,
                        "match_type": "exact_po_reference",
                        "normalized_reference": invoice_ref,
                    },
                )

        # -----------------------------------------------------
        # PASS 2:
        # NORMALIZED LOGICAL PO MATCH
        # -----------------------------------------------------

        for po in purchase_orders:

            po_ref = self._normalize_po_reference(
                po.po_number
            )

            if po_ref and po_ref == invoice_ref:

                explanation = (
                    f"Normalized PO reference match: invoice "
                    f"reference '{invoice.po_reference}' and PO "
                    f"'{po.po_number}' refer to the same PO identifier "
                    f"'{invoice_ref}'."
                )

                return MatchingResult(
                    matched_po=po,
                    confidence_score=self.NORMALIZED_EXACT_CONFIDENCE,
                    explanation=explanation,
                    matching_method="exact",
                    match_details={
                        "po_reference": invoice.po_reference,
                        "po_number": po.po_number,
                        "match_type": "normalized_po_reference",
                        "normalized_reference": invoice_ref,
                    },
                )

        return None

    # =========================================================
    # PO REFERENCE NORMALIZATION
    # =========================================================

    @staticmethod
    def _clean_po_reference(value: Any) -> str:
        """
        Basic normalization.

        Example:
            ' po-0003 ' -> 'PO-0003'
        """

        if value is None:
            return ""

        return str(value).strip().upper()

    @staticmethod
    def _normalize_po_reference(value: Any) -> Optional[str]:
        """
        Convert equivalent PO references to a common logical ID.

        Examples:

            PO-0003       -> PO-3
            PO-003        -> PO-3
            PO-2024-003   -> PO-3
            po 2024 003   -> PO-3

        This allows evaluation data and production PO data to use
        different year/padding conventions without breaking matching.
        """

        if value is None:
            return None

        raw = str(value).strip().upper()

        if not raw:
            return None

        # Prefer the numeric identifier attached to the PO token itself.
        # This prevents contaminated OCR strings such as
        # "PO-0045 ... Line Total 313812.57" from using the final
        # invoice amount as the PO identifier.
        po_match = re.search(r"\bPO\s*[-_/]?\s*(?:\d{4}\s*[-_/]\s*)?(\d+)\b", raw)
        if po_match:
            identifier = po_match.group(1)
        else:
            # Fallback for unusual but still numeric PO references.
            numbers = re.findall(r"\\d+", raw)
            if not numbers:
                return raw
            identifier = numbers[-1]

        try:
            identifier = str(int(identifier))
        except ValueError:
            identifier = identifier.lstrip("0") or "0"

        return f"PO-{identifier}"

    # =========================================================
    # FUZZY MATCHING
    # =========================================================

    def _fuzzy_match(
        self,
        invoice: InvoiceData,
        purchase_orders: List[PurchaseOrder],
    ) -> Optional[MatchingResult]:
        """
        Evidence-based fuzzy matching.

        A candidate must have meaningful evidence.
        We do NOT accept the highest score blindly.
        """

        candidates = []

        for po in purchase_orders:

            score, details = self._calculate_fuzzy_score(
                invoice,
                po,
            )

            candidates.append(
                {
                    "po": po,
                    "score": score,
                    "details": details,
                }
            )

        if not candidates:
            return None

        # Sort highest score first
        candidates.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        best = candidates[0]

        best_po = best["po"]
        best_score = best["score"]
        best_details = best["details"]

        second_score = (
            candidates[1]["score"]
            if len(candidates) > 1
            else 0.0
        )

        score_margin = best_score - second_score

        # -----------------------------------------------------
        # CHECK WHETHER BEST CANDIDATE HAS REAL EVIDENCE
        # -----------------------------------------------------

        vendor_similarity = best_details["vendor_similarity"]
        amount_match = best_details["amount_match"]
        date_match = best_details["date_match"]

        strong_vendor = (
            vendor_similarity >= self.MIN_VENDOR_SIMILARITY
        )

        moderate_vendor = (
            vendor_similarity >= self.MIN_VENDOR_SIMILARITY_WITH_AMOUNT
        )

        meaningful_evidence = (
            strong_vendor
            or (moderate_vendor and amount_match)
            or (strong_vendor and date_match)
            or (amount_match and date_match and moderate_vendor)
        )

        if not meaningful_evidence:
            return None

        # -----------------------------------------------------
        # CONFIDENCE CHECK
        # -----------------------------------------------------

        if best_score < self.MIN_FUZZY_CONFIDENCE:
            return None

        # -----------------------------------------------------
        # AMBIGUITY CHECK
        # -----------------------------------------------------

        # If several candidates are almost equally good,
        # do not pretend the match is reliable.
        if (
            len(candidates) > 1
            and score_margin < self.MIN_SCORE_MARGIN
            and not amount_match
        ):
            return None

        explanation = self._generate_fuzzy_explanation(
            invoice,
            best_po,
            best_details,
            best_score,
            score_margin,
        )

        return MatchingResult(
            matched_po=best_po,
            confidence_score=min(
                best_score,
                self.FUZZY_MATCH_CONFIDENCE_MAX,
            ),
            explanation=explanation,
            matching_method="fuzzy",
            match_details={
                **best_details,
                "score_margin": score_margin,
                "candidate_count": len(candidates),
                "match_type": "evidence_based_fuzzy",
            },
        )

    # =========================================================
    # FUZZY SCORE
    # =========================================================

    def _calculate_fuzzy_score(
        self,
        invoice: InvoiceData,
        po: PurchaseOrder,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate evidence-based fuzzy score.

        Weights:
            Vendor = 45%
            Amount = 35%
            Date   = 20%
        """

        details = {
            "vendor_match": False,
            "amount_match": False,
            "date_match": False,
            "vendor_similarity": 0.0,
            "amount_difference": None,
            "amount_difference_percent": None,
            "date_difference_days": None,
            "vendor_score": 0.0,
            "amount_score": 0.0,
            "date_score": 0.0,
        }

        # -----------------------------------------------------
        # VENDOR
        # -----------------------------------------------------

        invoice_vendor = getattr(
            invoice,
            "vendor_name",
            None,
        )

        po_vendor = getattr(
            po,
            "vendor_name",
            None,
        )

        vendor_similarity = self._calculate_string_similarity(
            invoice_vendor,
            po_vendor,
        )

        details["vendor_similarity"] = vendor_similarity

        if vendor_similarity >= self.MIN_VENDOR_SIMILARITY:
            details["vendor_match"] = True

        # Full vendor score
        details["vendor_score"] = vendor_similarity * 0.45

        # -----------------------------------------------------
        # AMOUNT
        # -----------------------------------------------------

        invoice_amount = self._to_float(
            getattr(invoice, "total_amount", None)
        )

        po_amount = self._to_float(
            getattr(po, "total_amount", None)
        )

        if (
            invoice_amount is not None
            and po_amount is not None
            and po_amount > 0
        ):

            amount_difference = abs(
                invoice_amount - po_amount
            )

            amount_difference_percent = (
                amount_difference / po_amount
            )

            details["amount_difference"] = amount_difference
            details["amount_difference_percent"] = (
                amount_difference_percent
            )

            if (
                amount_difference_percent
                <= self.AMOUNT_TOLERANCE_PERCENT
            ):
                details["amount_match"] = True
                details["amount_score"] = 0.35

            else:
                # Gradual score reduction.
                closeness = max(
                    0.0,
                    1.0 - amount_difference_percent,
                )

                details["amount_score"] = (
                    0.35 * closeness
                )

        # -----------------------------------------------------
        # DATE
        # -----------------------------------------------------

        invoice_date = getattr(
            invoice,
            "invoice_date",
            None,
        )

        po_date = getattr(
            po,
            "po_date",
            None,
        )

        if invoice_date and po_date:

            try:
                date_difference = abs(
                    (invoice_date - po_date).days
                )

                details["date_difference_days"] = (
                    date_difference
                )

                if date_difference <= self.DATE_TOLERANCE_DAYS:
                    details["date_match"] = True

                    date_score = max(
                        0.0,
                        1.0
                        - (
                            date_difference
                            / self.DATE_TOLERANCE_DAYS
                        ),
                    )

                    details["date_score"] = (
                        0.20 * date_score
                    )

                else:

                    # Small residual credit for moderately
                    # close dates.
                    if date_difference <= 90:

                        date_score = max(
                            0.0,
                            1.0
                            - (
                                date_difference
                                / 90
                            ),
                        )

                        details["date_score"] = (
                            0.20
                            * 0.5
                            * date_score
                        )

            except Exception:
                details["date_score"] = 0.0

        # -----------------------------------------------------
        # RAW EVIDENCE SCORE
        # -----------------------------------------------------

        evidence_score = (
            details["vendor_score"]
            + details["amount_score"]
            + details["date_score"]
        )

        # Convert evidence score into confidence.
        #
        # evidence = 0.0 -> 0.60
        # evidence = 1.0 -> 0.95
        #
        final_score = (
            self.FUZZY_MATCH_CONFIDENCE_BASE
            + (
                evidence_score
                * (
                    self.FUZZY_MATCH_CONFIDENCE_MAX
                    - self.FUZZY_MATCH_CONFIDENCE_BASE
                )
            )
        )

        return min(
            final_score,
            self.FUZZY_MATCH_CONFIDENCE_MAX,
        ), details

    # =========================================================
    # VENDOR-ONLY FALLBACK
    # =========================================================

    def _vendor_only_match(
        self,
        invoice: InvoiceData,
        purchase_orders: List[PurchaseOrder],
    ) -> Optional[MatchingResult]:
        """
        Conservative fallback when PO reference is absent.

        Vendor-only matching is accepted only when:
            - vendor similarity is very high
            - candidate is clearly better than second candidate
        """

        invoice_vendor = getattr(
            invoice,
            "vendor_name",
            None,
        )

        if not invoice_vendor:
            return None

        candidates = []

        for po in purchase_orders:

            similarity = self._calculate_string_similarity(
                invoice_vendor,
                po.vendor_name,
            )

            candidates.append(
                (similarity, po)
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        if not candidates:
            return None

        best_similarity, best_po = candidates[0]

        second_similarity = (
            candidates[1][0]
            if len(candidates) > 1
            else 0.0
        )

        margin = (
            best_similarity
            - second_similarity
        )

        # Very strong vendor similarity required.
        if best_similarity < 0.92:
            return None

        # Avoid ambiguous vendor-only matches.
        if len(candidates) > 1 and margin < 0.05:
            return None

        confidence = min(
            0.60 + best_similarity * 0.25,
            0.85,
        )

        explanation = (
            f"Vendor-based match found with PO "
            f"'{best_po.po_number}' because no reliable PO "
            f"reference match was available. Vendor similarity "
            f"is {best_similarity:.2%}."
        )

        return MatchingResult(
            matched_po=best_po,
            confidence_score=confidence,
            explanation=explanation,
            matching_method="vendor",
            match_details={
                "match_type": "vendor_only",
                "vendor_similarity": best_similarity,
                "score_margin": margin,
            },
        )

    # =========================================================
    # STRING SIMILARITY
    # =========================================================

    @staticmethod
    def _calculate_string_similarity(
        str1: Any,
        str2: Any,
    ) -> float:
        """
        Robust vendor-name similarity.
        """

        if not str1 or not str2:
            return 0.0

        s1 = MatchingAgent._normalize_vendor_name(
            str1
        )

        s2 = MatchingAgent._normalize_vendor_name(
            str2
        )

        if not s1 or not s2:
            return 0.0

        if s1 == s2:
            return 1.0

        # Direct sequence similarity
        sequence_score = SequenceMatcher(
            None,
            s1,
            s2,
        ).ratio()

        # Token similarity helps with reordered names.
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())

        if tokens1 or tokens2:
            intersection = len(
                tokens1 & tokens2
            )

            union = len(
                tokens1 | tokens2
            )

            token_score = (
                intersection / union
                if union
                else 0.0
            )
        else:
            token_score = 0.0

        return max(
            sequence_score,
            token_score,
        )

    @staticmethod
    def _normalize_vendor_name(
        value: Any,
    ) -> str:
        """
        Normalize vendor names.

        Example:

            'PharmaChem Supplies Ltd.'
            ->
            'pharmachem supplies ltd'
        """

        text = str(value).strip().lower()

        # Remove punctuation
        text = re.sub(
            r"[^a-z0-9\s]",
            " ",
            text,
        )

        # Normalize whitespace
        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """
        Safely convert numeric values to float.
        """

        if value is None:
            return None

        try:
            if isinstance(value, Decimal):
                return float(value)

            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    # =========================================================
    # EXPLANATION
    # =========================================================

    def _generate_fuzzy_explanation(
        self,
        invoice: InvoiceData,
        po: PurchaseOrder,
        details: Dict[str, Any],
        confidence: float,
        score_margin: float,
    ) -> str:
        """
        Generate explainable matching reasoning.
        """

        parts = [
            f"Evidence-based fuzzy match found with PO "
            f"'{po.po_number}' "
            f"(confidence: {confidence:.2%})"
        ]

        # -----------------------------------------------------
        # VENDOR
        # -----------------------------------------------------

        vendor_similarity = details.get(
            "vendor_similarity",
            0.0,
        )

        if details.get("vendor_match"):

            parts.append(
                f"Vendor names strongly match "
                f"('{invoice.vendor_name}' ≈ "
                f"'{po.vendor_name}', "
                f"similarity: {vendor_similarity:.2%})"
            )

        elif vendor_similarity >= 0.65:

            parts.append(
                f"Vendor names are moderately similar "
                f"('{invoice.vendor_name}' ≈ "
                f"'{po.vendor_name}', "
                f"similarity: {vendor_similarity:.2%})"
            )

        else:

            parts.append(
                f"Vendor similarity is low "
                f"('{invoice.vendor_name}' vs "
                f"'{po.vendor_name}', "
                f"similarity: {vendor_similarity:.2%})"
            )

        # -----------------------------------------------------
        # AMOUNT
        # -----------------------------------------------------

        if details.get("amount_match"):

            parts.append(
                f"Invoice amount "
                f"${self._to_float(invoice.total_amount):.2f} "
                f"matches PO amount "
                f"${self._to_float(po.total_amount):.2f} "
                f"within the "
                f"{self.AMOUNT_TOLERANCE_PERCENT:.0%} tolerance"
            )

        elif details.get("amount_difference") is not None:

            difference = details[
                "amount_difference"
            ]

            difference_percent = details.get(
                "amount_difference_percent",
                0.0,
            )

            parts.append(
                f"Amount difference is "
                f"${difference:.2f} "
                f"({difference_percent:.2%})"
            )

        # -----------------------------------------------------
        # DATE
        # -----------------------------------------------------

        if details.get("date_match"):

            parts.append(
                f"Invoice and PO dates are within "
                f"{details['date_difference_days']} days"
            )

        elif details.get(
            "date_difference_days"
        ) is not None:

            parts.append(
                f"Invoice and PO dates differ by "
                f"{details['date_difference_days']} days"
            )

        # -----------------------------------------------------
        # CANDIDATE MARGIN
        # -----------------------------------------------------

        parts.append(
            f"Best-candidate score margin: "
            f"{score_margin:.2%}"
        )

        return ". ".join(parts) + "."

    # =========================================================
    # NO MATCH RESULT
    # =========================================================

    def _create_no_match_result(
        self,
        reason: str,
    ) -> MatchingResult:
        """
        Create safe no-match result.
        """

        return MatchingResult(
            matched_po=None,
            confidence_score=0.0,
            explanation=reason,
            matching_method="none",
            match_details={
                "reason": reason,
                "match_type": "no_match",
            },
        )