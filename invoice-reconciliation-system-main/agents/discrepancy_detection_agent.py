"""
Discrepancy Detection Agent
===========================

Deterministic invoice-vs-purchase-order discrepancy detection.

Supported discrepancy types:
    - price_mismatch
    - quantity_mismatch
    - missing_line_item
    - extra_line_item
    - unit_mismatch

Line-item matching priority:
    1. Exact normalized item ID
    2. Exact normalized description
    3. Fuzzy description similarity

Only after reliable matching are missing/extra items reported.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from decimal import Decimal, InvalidOperation
from enum import Enum
import logging
import re
from difflib import SequenceMatcher


logger = logging.getLogger(__name__)


# ============================================================
# ENUMS
# ============================================================

class DiscrepancyType(Enum):
    PRICE_MISMATCH = "price_mismatch"
    QUANTITY_MISMATCH = "quantity_mismatch"
    MISSING_LINE_ITEM = "missing_line_item"
    EXTRA_LINE_ITEM = "extra_line_item"
    UNIT_MISMATCH = "unit_mismatch"


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class LineItem:
    item_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    unit: str

    def __post_init__(self):
        self.item_id = str(self.item_id or "").strip()
        self.description = str(self.description or "").strip()
        self.unit = str(self.unit or "").strip()

        try:
            self.quantity = Decimal(str(self.quantity))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(
                f"Invalid quantity for item '{self.item_id}'"
            )

        try:
            self.unit_price = Decimal(str(self.unit_price))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(
                f"Invalid unit price for item '{self.item_id}'"
            )

        if not self.item_id:
            raise ValueError("Item ID cannot be empty")

        if not self.quantity.is_finite():
            raise ValueError(
                f"Quantity must be finite for item '{self.item_id}'"
            )

        if not self.unit_price.is_finite():
            raise ValueError(
                f"Unit price must be finite for item '{self.item_id}'"
            )

        if self.quantity < 0:
            raise ValueError(
                f"Quantity cannot be negative for item '{self.item_id}'"
            )

        if self.unit_price < 0:
            raise ValueError(
                f"Unit price cannot be negative for item '{self.item_id}'"
            )


@dataclass
class Discrepancy:
    discrepancy_type: DiscrepancyType
    severity: Severity
    item_id: str
    invoice_value: Optional[Any]
    po_value: Optional[Any]
    difference: Optional[Decimal]
    percentage_diff: Optional[float]
    explanation: str
    confidence: float


@dataclass
class DiscrepancyDetectionResult:
    discrepancies: List[Discrepancy]
    overall_confidence: float
    summary: str
    total_discrepancies: int


# ============================================================
# AGENT
# ============================================================

class DiscrepancyDetectionAgent:

    def __init__(
        self,
        price_tolerance_percent: Decimal = Decimal("1.0"),
        quantity_tolerance_percent: Decimal = Decimal("1.0"),
        description_match_threshold: float = 0.88,
    ):
        """
        Args:
            price_tolerance_percent:
                Maximum acceptable percentage price difference.

            quantity_tolerance_percent:
                Maximum acceptable percentage quantity difference.

            description_match_threshold:
                Minimum fuzzy description similarity required to pair
                invoice and PO line items.
        """

        self.price_tolerance_percent = Decimal(
            str(price_tolerance_percent)
        )
        self.quantity_tolerance_percent = Decimal(
            str(quantity_tolerance_percent)
        )
        self.description_match_threshold = float(
            description_match_threshold
        )

        if (
            not self.price_tolerance_percent.is_finite()
            or self.price_tolerance_percent < 0
        ):
            raise ValueError(
                "Price tolerance must be a finite non-negative number"
            )

        if (
            not self.quantity_tolerance_percent.is_finite()
            or self.quantity_tolerance_percent < 0
        ):
            raise ValueError(
                "Quantity tolerance must be a finite non-negative number"
            )

        if not 0.0 <= self.description_match_threshold <= 1.0:
            raise ValueError(
                "Description match threshold must be between 0 and 1"
            )

    # ========================================================
    # MAIN ENTRY
    # ========================================================

    def detect_discrepancies(
        self,
        invoice_items: List[LineItem],
        po_items: List[LineItem],
    ) -> DiscrepancyDetectionResult:

        invoice_items = invoice_items or []
        po_items = po_items or []

        discrepancies: List[Discrepancy] = []

        # ----------------------------------------------------
        # COERCE INPUTS
        # ----------------------------------------------------

        normalized_invoice_items = [
            self._ensure_line_item(item)
            for item in invoice_items
        ]

        normalized_po_items = [
            self._ensure_line_item(item)
            for item in po_items
        ]

        # ----------------------------------------------------
        # EMPTY DATA
        # ----------------------------------------------------

        if not normalized_invoice_items and not normalized_po_items:
            return DiscrepancyDetectionResult(
                discrepancies=[],
                overall_confidence=0.95,
                summary="No line items available for comparison.",
                total_discrepancies=0,
            )

        # If PO has no line items but invoice does, every invoice
        # item is extra. If invoice has no line items but PO does,
        # every PO item is missing.
        matches, unmatched_invoice, unmatched_po = (
            self._match_line_items(
                normalized_invoice_items,
                normalized_po_items,
            )
        )

        logger.debug(
            "Line-item matching completed: "
            "%d matched, %d unmatched invoice, %d unmatched PO",
            len(matches),
            len(unmatched_invoice),
            len(unmatched_po),
        )

        # ====================================================
        # MISSING LINE ITEMS
        # ====================================================

        for po_item in unmatched_po:
            discrepancies.append(
                Discrepancy(
                    discrepancy_type=DiscrepancyType.MISSING_LINE_ITEM,
                    # IMPORTANT:
                    # Missing/omitted items are structural review issues,
                    # not automatically high-risk financial failures.
                    severity=Severity.MEDIUM,
                    item_id=po_item.item_id,
                    invoice_value=None,
                    po_value=po_item.quantity,
                    difference=None,
                    percentage_diff=None,
                    explanation=(
                        f"PO item '{po_item.description or po_item.item_id}' "
                        f"is missing from invoice"
                    ),
                    confidence=1.0,
                )
            )

        # ====================================================
        # EXTRA LINE ITEMS
        # ====================================================

        for invoice_item in unmatched_invoice:
            discrepancies.append(
                Discrepancy(
                    discrepancy_type=DiscrepancyType.EXTRA_LINE_ITEM,
                    severity=Severity.MEDIUM,
                    item_id=invoice_item.item_id,
                    invoice_value=invoice_item.quantity,
                    po_value=None,
                    difference=None,
                    percentage_diff=None,
                    explanation=(
                        f"Invoice item "
                        f"'{invoice_item.description or invoice_item.item_id}' "
                        f"is not present in PO"
                    ),
                    confidence=1.0,
                )
            )

        # ====================================================
        # COMPARE MATCHED ITEMS
        # ====================================================

        for invoice_item, po_item, match_method, match_score in matches:

            # ------------------------------------------------
            # UNIT CHECK
            # ------------------------------------------------

            invoice_unit = self._normalize_unit(
                invoice_item.unit
            )
            po_unit = self._normalize_unit(
                po_item.unit
            )

            if invoice_unit != po_unit:
                discrepancies.append(
                    Discrepancy(
                        discrepancy_type=DiscrepancyType.UNIT_MISMATCH,
                        severity=Severity.MEDIUM,
                        item_id=invoice_item.item_id,
                        invoice_value=invoice_item.unit,
                        po_value=po_item.unit,
                        difference=None,
                        percentage_diff=None,
                        explanation=(
                            f"Unit mismatch for "
                            f"'{invoice_item.description or invoice_item.item_id}': "
                            f"invoice={invoice_item.unit}, PO={po_item.unit}"
                        ),
                        confidence=self._match_confidence(
                            match_method,
                            match_score,
                        ),
                    )
                )

            # ------------------------------------------------
            # PRICE CHECK
            # ------------------------------------------------

            price_diff = abs(
                invoice_item.unit_price - po_item.unit_price
            )

            price_percent = self._percentage_difference(
                invoice_item.unit_price,
                po_item.unit_price,
            )

            if price_percent > float(
                self.price_tolerance_percent
            ):
                severity = self._price_severity(price_percent)

                direction = (
                    "increased"
                    if invoice_item.unit_price > po_item.unit_price
                    else "decreased"
                )

                discrepancies.append(
                    Discrepancy(
                        discrepancy_type=DiscrepancyType.PRICE_MISMATCH,
                        severity=severity,
                        item_id=invoice_item.item_id,
                        invoice_value=invoice_item.unit_price,
                        po_value=po_item.unit_price,
                        difference=price_diff,
                        percentage_diff=price_percent,
                        explanation=(
                            f"Price {direction} by "
                            f"{price_percent:.2f}% for item "
                            f"'{invoice_item.description or invoice_item.item_id}'"
                        ),
                        confidence=self._calculate_confidence(
                            price_percent
                        ),
                    )
                )

            # ------------------------------------------------
            # QUANTITY CHECK
            # ------------------------------------------------

            quantity_diff = abs(
                invoice_item.quantity - po_item.quantity
            )

            quantity_percent = self._percentage_difference(
                invoice_item.quantity,
                po_item.quantity,
            )

            if quantity_percent > float(
                self.quantity_tolerance_percent
            ):
                severity = self._quantity_severity(
                    quantity_percent
                )

                direction = (
                    "increased"
                    if invoice_item.quantity > po_item.quantity
                    else "decreased"
                )

                discrepancies.append(
                    Discrepancy(
                        discrepancy_type=DiscrepancyType.QUANTITY_MISMATCH,
                        severity=severity,
                        item_id=invoice_item.item_id,
                        invoice_value=invoice_item.quantity,
                        po_value=po_item.quantity,
                        difference=quantity_diff,
                        percentage_diff=quantity_percent,
                        explanation=(
                            f"Quantity {direction} by "
                            f"{quantity_percent:.2f}% for item "
                            f"'{invoice_item.description or invoice_item.item_id}'"
                        ),
                        confidence=self._calculate_confidence(
                            quantity_percent
                        ),
                    )
                )

        # ====================================================
        # OVERALL CONFIDENCE
        # ====================================================

        if discrepancies:
            overall_confidence = (
                sum(
                    float(d.confidence)
                    for d in discrepancies
                )
                / len(discrepancies)
            )
        else:
            overall_confidence = 0.95

        overall_confidence = min(
            1.0,
            max(0.0, overall_confidence),
        )

        # ====================================================
        # SUMMARY
        # ====================================================

        summary = self._build_summary(discrepancies)

        # ====================================================
        # LOGGING
        # ====================================================

        logger.info(
            "Discrepancy detection completed: "
            "%d discrepancies, confidence=%.2f",
            len(discrepancies),
            overall_confidence,
        )

        # ====================================================
        # RESULT
        # ====================================================

        return DiscrepancyDetectionResult(
            discrepancies=discrepancies,
            overall_confidence=round(
                overall_confidence,
                4,
            ),
            summary=summary,
            total_discrepancies=len(discrepancies),
        )

    # ========================================================
    # LINE ITEM MATCHING
    # ========================================================

    def _match_line_items(
        self,
        invoice_items: List[LineItem],
        po_items: List[LineItem],
    ) -> Tuple[
        List[Tuple[LineItem, LineItem, str, float]],
        List[LineItem],
        List[LineItem],
    ]:
        """
        Pair invoice items with PO items.

        Matching priority:
            0. Unique quantity + unit-price fingerprint
            1. Exact normalized item ID
            2. Exact normalized description
            3. Conservative fuzzy description similarity

        Each item can be matched only once.
        """

        matches: List[
            Tuple[LineItem, LineItem, str, float]
        ] = []

        remaining_invoice = list(invoice_items)
        remaining_po = list(po_items)

        # ----------------------------------------------------
        # PASS 0: UNIQUE NUMERIC FINGERPRINT
        # ----------------------------------------------------
        # PDF table extraction can occasionally corrupt item IDs or
        # descriptions while preserving quantity and unit price.
        # Use the numeric pair only when it identifies exactly ONE
        # remaining PO item.  This avoids accidentally pairing two
        # different products that happen to share the same numbers.
        for invoice_item in list(remaining_invoice):
            candidates = [
                po_item
                for po_item in remaining_po
                if (
                    invoice_item.quantity == po_item.quantity
                    and invoice_item.unit_price == po_item.unit_price
                )
            ]

            if len(candidates) == 1:
                found_po = candidates[0]
                matches.append(
                    (
                        invoice_item,
                        found_po,
                        "numeric_fingerprint",
                        1.0,
                    )
                )
                remaining_invoice.remove(invoice_item)
                remaining_po.remove(found_po)

        # ----------------------------------------------------
        # PASS 1: EXACT ITEM ID
        # ----------------------------------------------------

        for invoice_item in list(remaining_invoice):

            invoice_id = self._normalize_item_id(
                invoice_item.item_id
            )

            if not invoice_id:
                continue

            found_po = None

            for po_item in remaining_po:
                po_id = self._normalize_item_id(
                    po_item.item_id
                )

                if invoice_id == po_id:
                    found_po = po_item
                    break

            if found_po is not None:
                matches.append(
                    (
                        invoice_item,
                        found_po,
                        "exact_id",
                        1.0,
                    )
                )

                remaining_invoice.remove(invoice_item)
                remaining_po.remove(found_po)

        # ----------------------------------------------------
        # PASS 2: EXACT DESCRIPTION
        # ----------------------------------------------------

        for invoice_item in list(remaining_invoice):

            invoice_description = self._normalize_description(
                invoice_item.description
            )

            if not invoice_description:
                continue

            found_po = None

            for po_item in remaining_po:

                po_description = self._normalize_description(
                    po_item.description
                )

                if (
                    invoice_description
                    and invoice_description == po_description
                ):
                    found_po = po_item
                    break

            if found_po is not None:
                matches.append(
                    (
                        invoice_item,
                        found_po,
                        "exact_description",
                        1.0,
                    )
                )

                remaining_invoice.remove(invoice_item)
                remaining_po.remove(found_po)

        # ----------------------------------------------------
        # PASS 3: FUZZY DESCRIPTION
        # ----------------------------------------------------
        # Fuzzy matching is deliberately conservative.  A match is
        # accepted only when:
        #   1. similarity reaches the configured threshold, AND
        #   2. the best candidate is meaningfully better than the
        #      second-best candidate.
        #
        # This prevents unrelated line items from being paired merely
        # because their descriptions share common words.
        for invoice_item in list(remaining_invoice):
            invoice_description = self._normalize_description(
                invoice_item.description
            )

            if not invoice_description:
                continue

            scored = []
            for po_item in remaining_po:
                po_description = self._normalize_description(
                    po_item.description
                )

                if not po_description:
                    continue

                score = self._description_similarity(
                    invoice_description,
                    po_description,
                )

                scored.append((score, po_item))

            if not scored:
                continue

            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_po = scored[0]
            second_score = scored[1][0] if len(scored) > 1 else 0.0

            # Require a clear winner.  For a single remaining candidate,
            # the margin requirement is naturally satisfied.
            margin_ok = (
                len(scored) == 1
                or (best_score - second_score) >= 0.08
            )

            if (
                best_po is not None
                and best_score >= self.description_match_threshold
                and margin_ok
            ):
                matches.append(
                    (
                        invoice_item,
                        best_po,
                        "fuzzy_description",
                        best_score,
                    )
                )

                remaining_invoice.remove(invoice_item)
                remaining_po.remove(best_po)

        return (
            matches,
            remaining_invoice,
            remaining_po,
        )

    # ========================================================
    # NORMALIZATION HELPERS
    # ========================================================

    @staticmethod
    def _normalize_item_id(item_id: Any) -> str:
        if item_id is None:
            return ""

        value = str(item_id).strip().lower()

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value

    @staticmethod
    def _normalize_description(description: Any) -> str:
        if description is None:
            return ""

        value = str(description).strip().lower()

        # Replace punctuation with spaces.
        value = re.sub(
            r"[^a-z0-9]+",
            " ",
            value,
        )

        # Remove common filler words.
        stop_words = {
            "the",
            "a",
            "an",
            "item",
            "product",
            "description",
        }

        tokens = [
            token
            for token in value.split()
            if token not in stop_words
        ]

        return " ".join(tokens)

    @staticmethod
    def _description_similarity(left: str, right: str) -> float:
        """
        Compare descriptions using both character similarity and token
        overlap.  Token overlap is more robust to reordered words while
        SequenceMatcher protects against unrelated partial matches.
        """
        if not left or not right:
            return 0.0

        char_score = SequenceMatcher(None, left, right).ratio()

        left_tokens = set(left.split())
        right_tokens = set(right.split())

        if not left_tokens or not right_tokens:
            token_score = 0.0
        else:
            intersection = len(left_tokens & right_tokens)
            union = len(left_tokens | right_tokens)
            token_score = intersection / union if union else 0.0

        # Character similarity remains the primary signal.
        return (0.65 * char_score) + (0.35 * token_score)

    @staticmethod
    def _normalize_unit(unit: Any) -> str:
        if unit is None:
            return ""

        value = str(unit).strip().lower()

        aliases = {
            "pcs": "piece",
            "pc": "piece",
            "pieces": "piece",
            "ea": "each",
            "each": "each",
            "kgs": "kg",
            "kilogram": "kg",
            "kilograms": "kg",
            "litres": "liter",
            "liters": "liter",
            "l": "liter",
            "nos": "each",
            "no": "each",
            "units": "unit",
        }

        return aliases.get(
            value,
            value,
        )

    # ========================================================
    # COERCION
    # ========================================================

    @staticmethod
    def _ensure_line_item(item: Any) -> LineItem:

        if isinstance(item, LineItem):
            return item

        if isinstance(item, dict):

            item_id = item.get(
                "item_id",
                item.get(
                    "id",
                    item.get(
                        "sku",
                        "",
                    ),
                ),
            )

            description = item.get(
                "description",
                item.get(
                    "name",
                    "",
                ),
            )

            quantity = item.get(
                "quantity",
                0,
            )

            unit_price = item.get(
                "unit_price",
                item.get(
                    "price",
                    0,
                ),
            )

            unit = item.get(
                "unit",
                "",
            )

            return LineItem(
                item_id=str(item_id or ""),
                description=str(description or ""),
                quantity=self._to_decimal(quantity, "quantity", item_id),
                unit_price=self._to_decimal(unit_price, "unit_price", item_id),
                unit=str(unit or ""),
            )

        raise TypeError(
            "Line item must be a LineItem or dictionary."
        )

    # ========================================================
    # PERCENTAGE
    # ========================================================

    @staticmethod
    def _to_decimal(value: Any, field_name: str, item_id: str) -> Decimal:
        """Convert numeric input safely and reject non-finite values."""
        if value is None or str(value).strip() == "":
            raise ValueError(
                f"Missing {field_name} for item '{item_id}'"
            )

        try:
            result = Decimal(str(value).replace(",", "").strip())
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(
                f"Invalid {field_name} for item '{item_id}'"
            )

        if not result.is_finite():
            raise ValueError(
                f"{field_name} must be finite for item '{item_id}'"
            )

        return result

    @staticmethod
    def _percentage_difference(
        value: Decimal,
        base: Decimal,
    ) -> float:

        value = Decimal(str(value))
        base = Decimal(str(base))

        if base == 0:
            if value == 0:
                return 0.0

            return 100.0

        difference = abs(value - base)

        percentage = (
            difference
            / abs(base)
            * Decimal("100")
        )

        return float(percentage)

    # ========================================================
    # MATCH CONFIDENCE
    # ========================================================

    @staticmethod
    def _match_confidence(
        match_method: str,
        match_score: float,
    ) -> float:
        """
        Confidence in a discrepancy tied to the line-item pairing.

        Exact ID/description matches are deterministic.
        Fuzzy matches use their similarity score.
        """

        if match_method in {
            "exact_id",
            "exact_description",
            "numeric_fingerprint",
        }:
            return 1.0

        return min(
            1.0,
            max(
                0.0,
                float(match_score),
            ),
        )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    @staticmethod
    def _calculate_confidence(
        percentage: float,
    ) -> float:
        """
        Larger deviations provide stronger evidence that
        a discrepancy is genuine.

        Approximate behavior:
            1%  -> 0.81
            5%  -> 0.85
            10% -> 0.90
            20% -> 1.00
        """

        confidence = (
            0.80
            + (
                percentage
                / 100.0
            )
        )

        return min(
            1.0,
            max(
                0.0,
                confidence,
            ),
        )

    # ========================================================
    # PRICE SEVERITY
    # ========================================================

    @staticmethod
    def _price_severity(
        percent: float,
    ) -> Severity:

        if percent >= 50:
            return Severity.CRITICAL

        if percent >= 20:
            return Severity.HIGH

        if percent >= 10:
            return Severity.MEDIUM

        if percent >= 5:
            return Severity.LOW

        return Severity.INFO

    # ========================================================
    # QUANTITY SEVERITY
    # ========================================================

    @staticmethod
    def _quantity_severity(
        percent: float,
    ) -> Severity:

        if percent >= 50:
            return Severity.CRITICAL

        if percent >= 25:
            return Severity.HIGH

        if percent >= 10:
            return Severity.MEDIUM

        if percent >= 5:
            return Severity.LOW

        return Severity.INFO

    # ========================================================
    # SUMMARY
    # ========================================================

    @staticmethod
    def _build_summary(
        discrepancies: List[Discrepancy],
    ) -> str:

        if not discrepancies:
            return "No discrepancies found."

        type_counts: Dict[str, int] = {}

        for discrepancy in discrepancies:

            name = (
                discrepancy
                .discrepancy_type
                .value
            )

            type_counts[name] = (
                type_counts.get(
                    name,
                    0,
                )
                + 1
            )

        parts = []

        for name, count in type_counts.items():
            parts.append(
                f"{count} {name}"
            )

        return (
            f"{len(discrepancies)} "
            f"discrepancy(s) detected: "
            f"{', '.join(parts)}."
        )
