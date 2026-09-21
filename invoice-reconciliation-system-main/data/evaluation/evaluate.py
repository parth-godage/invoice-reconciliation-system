"""
AI Finance Controller - Batch Evaluation

Runs the existing LangGraph reconciliation engine against
the synthetic evaluation invoice dataset and compares AI
predictions with independent ground truth.

Run from project root:

    python data/evaluation/evaluate.py
"""

import json
import re
import sys
import traceback
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ============================================================
# PROJECT ROOT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ============================================================
# IMPORT EXISTING LANGGRAPH
# ============================================================

from graph.orchestration import run_reconciliation
from models import PurchaseOrder


# ============================================================
# PATHS
# ============================================================

EVALUATION_DIR = BASE_DIR / "data" / "evaluation"

INVOICE_DIR = EVALUATION_DIR / "invoices"

PO_FILE = EVALUATION_DIR / "purchase_orders.json"

GROUND_TRUTH_FILE = EVALUATION_DIR / "ground_truth.json"

RESULTS_FILE = EVALUATION_DIR / "results.json"


# ============================================================
# GENERAL HELPERS
# ============================================================

def get_value(obj: Any, *keys, default=None):
    """
    Get a value from:
        - dict
        - object
        - dataclass
        - Enum
    """

    if obj is None:
        return default

    for key in keys:

        # Dictionary
        if isinstance(obj, dict):

            if key in obj:
                return obj[key]

        # Object
        else:

            if hasattr(obj, key):

                try:
                    return getattr(obj, key)
                except Exception:
                    pass

    return default


# ============================================================

def object_to_dict(obj: Any):
    """
    Convert common Python result objects into dictionaries.
    Used only for inspection / extraction.
    """

    if obj is None:
        return None

    if isinstance(obj, dict):
        return obj

    if is_dataclass(obj):

        try:
            return asdict(obj)
        except Exception:
            pass

    if hasattr(obj, "__dict__"):

        try:
            return vars(obj)
        except Exception:
            pass

    return None


# ============================================================
# ACTION NORMALIZATION
# ============================================================

def normalize_action(value: Any) -> Optional[str]:
    """
    Normalize all action representations into:

        APPROVE
        REVIEW
        ESCALATE
    """

    if value is None:
        return None

    # Enum
    if isinstance(value, Enum):

        try:
            value = value.value
        except Exception:
            value = value.name

    # Objects with .value
    elif hasattr(value, "value"):

        try:
            value = value.value
        except Exception:
            pass

    value = str(value).strip().upper()

    # Enum string:
    # ResolutionAction.APPROVE
    # RESOLUTIONACTION.APPROVE
    if "." in value:
        value = value.split(".")[-1]

    replacements = {
        "APPROVED": "APPROVE",
        "APPROVE": "APPROVE",

        "REVIEW_REQUIRED": "REVIEW",
        "NEEDS_REVIEW": "REVIEW",
        "REVIEW": "REVIEW",

        "ESCALATION": "ESCALATE",
        "ESCALATED": "ESCALATE",
        "ESCALATE": "ESCALATE",
    }

    return replacements.get(value, value)


# ============================================================
# PO NORMALIZATION
# ============================================================

def normalize_po(value: Any) -> Optional[str]:
    """
    Normalize PO numbers into a logical PO identifier.

    Examples:

        PO-0001       -> PO-1
        po-0001       -> PO-1
        PO-2024-001   -> PO-1
        PO-2024-003   -> PO-3

    This makes the evaluator consistent with the Matching Agent,
    where different formatting can represent the same PO.
    """

    if value is None:
        return None

    # PurchaseOrder object
    if not isinstance(value, (str, int, float)):

        nested = get_value(
            value,
            "po_number",
            "po_id",
            "number",
            "purchase_order_number",
            default=None,
        )

        if nested is not None:
            value = nested

        elif isinstance(value, Enum):

            value = value.value

        else:

            value = str(value)

    value = str(value).strip().upper()

    if not value:
        return None

    # Remove spaces
    value = re.sub(r"\s+", "", value)

    # Extract numeric groups
    numbers = re.findall(r"\d+", value)

    if numbers:

        # The final numeric group represents the PO sequence
        # for this synthetic dataset.
        sequence = numbers[-1]

        try:
            sequence_number = int(sequence)
        except Exception:
            sequence_number = sequence

        return f"PO-{sequence_number}"

    # Fallback
    return value


# ============================================================
# FLOAT
# ============================================================

def safe_float(value: Any) -> Optional[float]:

    if value is None:
        return None

    try:
        return float(value)

    except Exception:
        return None


# ============================================================
# RECURSIVE SEARCH
# ============================================================

def recursive_find(
    obj: Any,
    target_keys: Set[str],
    visited=None,
):
    """
    Recursively search dictionaries/objects/lists for one
    of the requested keys.

    Important because LangGraph may return nested state
    and result objects.
    """

    if visited is None:
        visited = set()

    if obj is None:
        return None

    object_id = id(obj)

    if object_id in visited:
        return None

    visited.add(object_id)

    # --------------------------------------------------------
    # Dictionary
    # --------------------------------------------------------

    if isinstance(obj, dict):

        # Direct keys first
        for key in target_keys:

            if key in obj:

                value = obj[key]

                if value is not None:
                    return value

        # Then recursively search values
        for value in obj.values():

            found = recursive_find(
                value,
                target_keys,
                visited,
            )

            if found is not None:
                return found

        return None

    # --------------------------------------------------------
    # List / Tuple
    # --------------------------------------------------------

    if isinstance(obj, (list, tuple)):

        for item in obj:

            found = recursive_find(
                item,
                target_keys,
                visited,
            )

            if found is not None:
                return found

        return None

    # --------------------------------------------------------
    # Enum
    # --------------------------------------------------------

    if isinstance(obj, Enum):
        return None

    # --------------------------------------------------------
    # Dataclass
    # --------------------------------------------------------

    if is_dataclass(obj):

        try:

            data = asdict(obj)

            found = recursive_find(
                data,
                target_keys,
                visited,
            )

            if found is not None:
                return found

        except Exception:
            pass

    # --------------------------------------------------------
    # Normal object
    # --------------------------------------------------------

    if hasattr(obj, "__dict__"):

        try:

            data = vars(obj)

            # Direct attributes
            for key in target_keys:

                if key in data:

                    value = data[key]

                    if value is not None:
                        return value

            # Nested attributes
            for value in data.values():

                found = recursive_find(
                    value,
                    target_keys,
                    visited,
                )

                if found is not None:
                    return found

        except Exception:
            pass

    return None


# ============================================================
# LOAD PURCHASE ORDERS
# ============================================================

def load_purchase_orders(
    json_path: Path,
) -> List[PurchaseOrder]:

    with open(
        json_path,
        "r",
        encoding="utf-8",
    ) as f:

        raw_data = json.load(f)

    purchase_orders = []

    raw_purchase_orders = raw_data.get(
        "purchase_orders",
        [],
    )

    for po_data in raw_purchase_orders:

        po_date = po_data.get("po_date")

        if po_date:

            try:

                po_date = datetime.fromisoformat(
                    str(po_date)
                ).date()

            except Exception:

                po_date = None

        po = PurchaseOrder(
            po_number=str(
                po_data.get(
                    "po_number",
                    "",
                )
            ),

            vendor_name=str(
                po_data.get(
                    "supplier",
                    "",
                )
            ),

            total_amount=float(
                po_data.get(
                    "total",
                    0.0,
                )
            ),

            po_date=po_date,

            line_items=po_data.get(
                "line_items",
                [],
            ),

            vendor_address=po_data.get(
                "vendor_address"
            ),

            description=po_data.get(
                "description"
            ),
        )

        purchase_orders.append(po)

    return purchase_orders


# ============================================================
# VALIDATE DATASET
# ============================================================

def validate_dataset(
    invoices: List[Path],
    purchase_orders: List[PurchaseOrder],
    ground_truth: Dict[str, Any],
):
    """
    Validate basic dataset integrity before running the expensive
    LangGraph evaluation.

    This does NOT try to determine whether an invoice is correct.
    It only checks structural consistency.
    """

    print()
    print("=" * 70)
    print("DATASET VALIDATION")
    print("=" * 70)

    problems = []

    # --------------------------------------------------------
    # Ground truth coverage
    # --------------------------------------------------------

    invoice_names = {
        invoice.name
        for invoice in invoices
    }

    gt_names = set(ground_truth.keys())

    missing_gt = sorted(
        invoice_names - gt_names
    )

    extra_gt = sorted(
        gt_names - invoice_names
    )

    if missing_gt:

        problems.append(
            f"Missing ground truth for: {missing_gt}"
        )

    if extra_gt:

        problems.append(
            f"Ground truth contains unknown invoices: {extra_gt}"
        )

    # --------------------------------------------------------
    # PO uniqueness
    # --------------------------------------------------------

    normalized_pos = {}

    for po in purchase_orders:

        po_number = normalize_po(
            get_value(
                po,
                "po_number",
                "po_id",
                default=None,
            )
        )

        if po_number is None:
            continue

        if po_number in normalized_pos:

            problems.append(
                "Duplicate logical PO detected: "
                f"{po_number}"
            )

        normalized_pos[po_number] = po

    # --------------------------------------------------------
    # Ground truth PO references
    # --------------------------------------------------------

    for filename, gt in ground_truth.items():

        if not isinstance(gt, dict):

            problems.append(
                f"{filename}: ground truth is not an object"
            )

            continue

        source_po = normalize_po(
            gt.get("source_po")
        )

        expected_po = normalize_po(
            gt.get("expected_po")
        )

        # Missing PO scenario is allowed to have
        # expected_po = None.
        if source_po is not None:

            if source_po not in normalized_pos:

                problems.append(
                    f"{filename}: source PO "
                    f"{source_po} does not exist "
                    f"in purchase_orders.json"
                )

        # If both exist, they normally identify the same logical PO.
        # Keep this as a warning rather than a hard failure because
        # some deliberately adversarial scenarios may use a different
        # expected PO.
        if (
            source_po is not None
            and expected_po is not None
            and source_po != expected_po
        ):
            print(
                f"WARNING: {filename}: "
                f"source_po={source_po}, "
                f"expected_po={expected_po}"
            )

    # --------------------------------------------------------
    # Print result
    # --------------------------------------------------------

    if problems:

        print()
        print("DATASET VALIDATION FAILED")
        print()

        for problem in problems:
            print(" -", problem)

        print()
        print(
            "Fix the dataset before trusting evaluation metrics."
        )

        return False

    print("Dataset structure: OK")
    print(
        f"Invoices: {len(invoices)}"
    )
    print(
        f"Ground truth records: {len(ground_truth)}"
    )
    print(
        f"Purchase orders: {len(purchase_orders)}"
    )

    print("=" * 70)

    return True


# ============================================================
# EXTRACT PREDICTION
# ============================================================

def extract_prediction(
    result: Any,
) -> Dict[str, Any]:

    # ========================================================
    # RESOLUTION
    # ========================================================

    resolution = recursive_find(
        result,
        {
            "resolution",
            "resolution_result",
            "resolution_recommendation",
            "recommendation",
            "resolution_response",
        },
    )

    # --------------------------------------------------------
    # Action
    # --------------------------------------------------------

    action = recursive_find(
        resolution,
        {
            "action",
            "decision",
            "resolution_action",
            "final_decision",
        },
    )

    if action is None:

        action = recursive_find(
            result,
            {
                "action",
                "decision",
                "resolution_action",
                "final_decision",
            },
        )

    action = normalize_action(action)

    # ========================================================
    # MATCHING
    # ========================================================

    matching = recursive_find(
        result,
        {
            "matching",
            "matching_result",
            "po_matching",
            "match_result",
            "matching_response",
        },
    )

    matched_po = recursive_find(
        matching,
        {
            "matched_po",
            "matched_po_number",
            "po_number",
            "purchase_order",
            "matched_purchase_order",
        },
    )

    if matched_po is None:

        matched_po = recursive_find(
            result,
            {
                "matched_po",
                "matched_po_number",
                "matched_purchase_order",
            },
        )

    matched_po = normalize_po(matched_po)

    # ========================================================
    # DOCUMENT EXTRACTION
    # ========================================================

    extraction = recursive_find(
        result,
        {
            "document_extraction",
            "extraction",
            "extraction_result",
            "document_result",
        },
    )

    extraction_confidence = recursive_find(
        extraction,
        {
            "confidence",
            "confidence_score",
            "extraction_confidence",
            "overall_confidence",
            "score",
        },
    )

    if extraction_confidence is None:

        extraction_confidence = recursive_find(
            result,
            {
                "extraction_confidence",
            },
        )

    extraction_confidence = safe_float(
        extraction_confidence
    )

    # ========================================================
    # MATCHING CONFIDENCE
    # ========================================================

    matching_confidence = recursive_find(
        matching,
        {
            "confidence",
            "matching_confidence",
            "match_confidence",
            "overall_confidence",
        },
    )

    if matching_confidence is None:

        matching_confidence = recursive_find(
            result,
            {
                "confidence",
                "confidence_score",
                "matching_confidence",
                "match_confidence",
                "overall_confidence",
                "score",
            },
        )

    matching_confidence = safe_float(
        matching_confidence
    )

    # ========================================================
    # RESOLUTION CONFIDENCE
    # ========================================================

    resolution_confidence = recursive_find(
        resolution,
        {
            "confidence",
            "confidence_score",
            "resolution_confidence",
            "decision_confidence",
            "overall_confidence",
            "score",
        },
    )

    if resolution_confidence is None:

        resolution_confidence = recursive_find(
            result,
            {
                "confidence",
                "confidence_score",
                "resolution_confidence",
                "decision_confidence",
                "overall_confidence",
                "score",
            },
        )

    resolution_confidence = safe_float(
        resolution_confidence
    )

    # ========================================================
    # DISCREPANCIES
    # ========================================================

    discrepancy_result = recursive_find(
        result,
        {
            "discrepancy_result",
            "discrepancy_results",
            "discrepancies",
            "discrepancy",
            "detected_discrepancies",
            "discrepancy_detection",
        },
    )

    discrepancies = []

    if discrepancy_result is None:

        discrepancies = []

    elif isinstance(
        discrepancy_result,
        (list, tuple),
    ):

        discrepancies = list(
            discrepancy_result
        )

    else:

        nested_discrepancies = recursive_find(
            discrepancy_result,
            {
                "discrepancies",
                "discrepancy_results",
                "detected_discrepancies",
            },
        )

        if nested_discrepancies is None:

            discrepancies = []

        elif isinstance(
            nested_discrepancies,
            (list, tuple),
        ):

            discrepancies = list(
                nested_discrepancies
            )

        else:

            discrepancies = [
                nested_discrepancies
            ]

    # ========================================================
    # EXPLANATION
    # ========================================================

    explanation = recursive_find(
        resolution,
        {
            "explanation",
            "reasoning",
            "reason",
        },
    )

    if explanation is None:

        explanation = recursive_find(
            result,
            {
                "explanation",
                "reasoning",
                "reason",
            },
        )

    if explanation is not None:

        explanation = str(explanation)

    # ========================================================
    # RETURN
    # ========================================================

    return {

        "predicted_po":
            matched_po,

        "predicted_action":
            action,

        "extraction_confidence":
            extraction_confidence,

        "matching_confidence":
            matching_confidence,

        "resolution_confidence":
            resolution_confidence,

        "discrepancies":
            discrepancies,

        "explanation":
            explanation,
    }


# ============================================================
# DISCREPANCY NORMALIZATION
# ============================================================

def normalize_discrepancy(
    discrepancy: Any,
) -> Optional[str]:

    if discrepancy is None:
        return None

    if isinstance(discrepancy, Enum):

        try:
            discrepancy = discrepancy.value
        except Exception:
            discrepancy = discrepancy.name

    elif not isinstance(
        discrepancy,
        (str, int, float),
    ):

        nested = get_value(
            discrepancy,
            "type",
            "category",
            "discrepancy_type",
            "code",
            "name",
            default=None,
        )

        if nested is not None:
            discrepancy = nested

        else:
            discrepancy = str(discrepancy)

    value = str(
        discrepancy
    ).strip().lower()

    # Normalize Enum-style strings such as:
    #   DiscrepancyType.QUANTITY_MISMATCH
    #   discrepancytype.quantity_mismatch
    # into the actual logical value:
    #   quantity_mismatch
    if "." in value:
        value = value.split(".")[-1]

    value = value.replace(
        "-",
        "_",
    ).replace(
        " ",
        "_",
    )

    # Common aliases
    aliases = {

        "missing_po":
            "missing_po_reference",

        "missing_po_ref":
            "missing_po_reference",

        "po_missing":
            "missing_po_reference",

        "price":
            "price_mismatch",

        "price_difference":
            "price_mismatch",

        "quantity":
            "quantity_mismatch",

        "qty_mismatch":
            "quantity_mismatch",

        "missing_item":
            "missing_line_item",

        "extra_item":
            "extra_line_item",
    }

    return aliases.get(
        value,
        value,
    )


def normalize_discrepancy_list(
    discrepancies: Any,
) -> Set[str]:

    if discrepancies is None:
        return set()

    if not isinstance(
        discrepancies,
        (list, tuple, set),
    ):
        discrepancies = [
            discrepancies
        ]

    result = set()

    for discrepancy in discrepancies:

        normalized = normalize_discrepancy(
            discrepancy
        )

        if normalized:
            result.add(normalized)

    return result


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:

    total = len(records)

    successful = sum(
        1
        for record in records
        if record.get("status") == "SUCCESS"
    )

    failed = sum(
        1
        for record in records
        if record.get("status") == "FAILED"
    )

    evaluated = [
        record
        for record in records
        if record.get("status") == "SUCCESS"
    ]

    # ========================================================
    # PO MATCHING
    # ========================================================
    #
    # Only invoices with a non-null expected_po are PO-evaluable.
    # Missing-PO-reference scenarios intentionally have
    # expected_po=None and therefore must not lower PO matching
    # accuracy.
    po_evaluable = [
        record
        for record in evaluated
        if record.get("expected_po") is not None
    ]

    po_correct = sum(
        1
        for record in po_evaluable
        if record.get(
            "po_match_correct"
        ) is True
    )

    # ========================================================
    # MISSING PO DETECTION
    # ========================================================
    #
    # Missing-PO scenarios are evaluated separately. The hidden
    # source_po is NOT used as a prediction target.
    missing_po_records = [
        record
        for record in evaluated
        if record.get("scenario") == "missing_po"
    ]

    missing_po_detected_correctly = sum(
        1
        for record in missing_po_records
        if "missing_po_reference"
        in set(record.get("predicted_discrepancies") or [])
    )

    missing_po_detection_accuracy = (
        round(
            missing_po_detected_correctly
            / len(missing_po_records)
            * 100,
            2,
        )
        if missing_po_records
        else None
    )

    # ========================================================
    # DECISION
    # ========================================================

    decision_correct = sum(
        1
        for record in evaluated
        if record.get(
            "decision_correct"
        ) is True
    )

    # ========================================================
    # DISCREPANCIES
    # ========================================================

    discrepancy_correct = sum(
        1
        for record in evaluated
        if record.get(
            "discrepancy_match_correct"
        ) is True
    )

    # ========================================================
    # UNRESOLVED
    # ========================================================

    unresolved = sum(
        1
        for record in evaluated
        if not record.get(
            "predicted_action"
        )
    )

    # ========================================================
    # AVERAGES
    # ========================================================

    def average(field):

        values = []

        for record in evaluated:

            value = safe_float(
                record.get(field)
            )

            if value is not None:
                values.append(value)

        if not values:
            return None

        return round(
            sum(values) / len(values),
            4,
        )

    # ========================================================
    # ACTION COUNTS
    # ========================================================

    action_counts = {
        "APPROVE": 0,
        "REVIEW": 0,
        "ESCALATE": 0,
    }

    for record in evaluated:

        action = normalize_action(
            record.get(
                "predicted_action"
            )
        )

        if action in action_counts:

            action_counts[action] += 1

    # ========================================================
    # SCENARIO METRICS
    # ========================================================

    scenario_stats = {}

    for record in evaluated:

        scenario = record.get(
            "scenario",
            "unknown",
        )

        if scenario not in scenario_stats:

            scenario_stats[scenario] = {
                "total": 0,
                "po_correct": 0,
                "decision_correct": 0,
                "discrepancy_correct": 0,
            }

        stats = scenario_stats[scenario]

        stats["total"] += 1

        if record.get(
            "po_match_correct"
        ) is True:

            stats["po_correct"] += 1

        if record.get(
            "decision_correct"
        ) is True:

            stats["decision_correct"] += 1

        if record.get(
            "discrepancy_match_correct"
        ) is True:

            stats["discrepancy_correct"] += 1

    # Add percentages
    for stats in scenario_stats.values():

        count = stats["total"]

        # PO accuracy is undefined for missing-PO scenarios
        # because expected_po is intentionally None.
        if scenario == "missing_po":
            stats["po_accuracy_percent"] = None
        else:
            stats["po_accuracy_percent"] = (
                round(
                    stats["po_correct"]
                    / count
                    * 100,
                    2,
                )
                if count
                else 0
            )

        stats["decision_accuracy_percent"] = (
            round(
                stats["decision_correct"]
                / count
                * 100,
                2,
            )
            if count
            else 0
        )

        stats["discrepancy_accuracy_percent"] = (
            round(
                stats["discrepancy_correct"]
                / count
                * 100,
                2,
            )
            if count
            else 0
        )

    # ========================================================
    # ACCURACY
    # ========================================================

    po_accuracy = (
        round(
            po_correct
            / len(po_evaluable)
            * 100,
            2,
        )
        if po_evaluable
        else 0
    )

    decision_accuracy = (
        round(
            decision_correct
            / successful
            * 100,
            2,
        )
        if successful
        else 0
    )

    discrepancy_accuracy = (
        round(
            discrepancy_correct
            / successful
            * 100,
            2,
        )
        if successful
        else 0
    )

    # ========================================================
    # RETURN
    # ========================================================

    return {

        "total_invoices":
            total,

        "successful":
            successful,

        "failed":
            failed,

        "unresolved":
            unresolved,

        "po_evaluable":
            len(po_evaluable),

        "correct_po_matches":
            po_correct,

        "incorrect_po_matches":
            len(po_evaluable) - po_correct,

        "po_match_accuracy_percent":
            po_accuracy,

        "missing_po_cases":
            len(missing_po_records),

        "missing_po_detected_correctly":
            missing_po_detected_correctly,

        "missing_po_detection_accuracy_percent":
            missing_po_detection_accuracy,

        "correct_decisions":
            decision_correct,

        "incorrect_decisions":
            successful - decision_correct,

        "decision_accuracy_percent":
            decision_accuracy,

        "correct_discrepancy_predictions":
            discrepancy_correct,

        "incorrect_discrepancy_predictions":
            successful - discrepancy_correct,

        "discrepancy_accuracy_percent":
            discrepancy_accuracy,

        "average_extraction_confidence":
            average(
                "extraction_confidence"
            ),

        "average_matching_confidence":
            average(
                "matching_confidence"
            ),

        "average_resolution_confidence":
            average(
                "resolution_confidence"
            ),

        "action_counts":
            action_counts,

        "scenario_metrics":
            scenario_stats,
    }


# ============================================================
# MAIN BATCH EVALUATION
# ============================================================

def run_batch_evaluation() -> Dict[str, Any]:

    print("=" * 70)
    print(
        "AI FINANCE CONTROLLER - "
        "BATCH EVALUATION"
    )
    print("=" * 70)

    # ========================================================
    # VALIDATE PATHS
    # ========================================================

    if not INVOICE_DIR.exists():

        raise FileNotFoundError(
            f"Evaluation invoice directory not found:\n"
            f"{INVOICE_DIR}"
        )

    if not PO_FILE.exists():

        raise FileNotFoundError(
            f"Purchase order file not found:\n"
            f"{PO_FILE}"
        )

    if not GROUND_TRUTH_FILE.exists():

        raise FileNotFoundError(
            f"Ground truth file not found:\n"
            f"{GROUND_TRUTH_FILE}"
        )

    # ========================================================
    # FIND INVOICES
    # ========================================================

    invoices = sorted(
        INVOICE_DIR.glob("*.pdf")
    )

    if not invoices:

        raise RuntimeError(
            "No evaluation PDF invoices found."
        )

    # ========================================================
    # LOAD DATA
    # ========================================================

    purchase_orders = load_purchase_orders(
        PO_FILE
    )

    with open(
        GROUND_TRUTH_FILE,
        "r",
        encoding="utf-8",
    ) as f:

        ground_truth = json.load(f)

    print(
        f"\nInvoices found: "
        f"{len(invoices)}"
    )

    print(
        f"Purchase orders: "
        f"{len(purchase_orders)}"
    )

    print(
        f"Ground truth records: "
        f"{len(ground_truth)}"
    )

    # ========================================================
    # DATASET VALIDATION
    # ========================================================

    if not validate_dataset(
        invoices,
        purchase_orders,
        ground_truth,
    ):

        raise RuntimeError(
            "Dataset validation failed. "
            "Evaluation stopped."
        )

    print()

    # ========================================================
    # PROCESS INVOICES
    # ========================================================

    records = []

    for index, invoice_path in enumerate(
        invoices,
        start=1,
    ):

        filename = invoice_path.name

        print(
            f"[{index}/{len(invoices)}] "
            f"Processing {filename}..."
        )

        # ----------------------------------------------------
        # GROUND TRUTH
        # ----------------------------------------------------

        gt = ground_truth.get(
            filename
        )

        if gt is None:

            print(
                "  FAILED: Missing ground truth"
            )

            records.append({

                "invoice":
                    filename,

                "status":
                    "FAILED",

                "error":
                    "Missing ground truth",
            })

            continue

        try:

            # =================================================
            # RUN LANGGRAPH
            # =================================================

            result = run_reconciliation(

                document_path=str(
                    invoice_path
                ),

                purchase_orders=
                    purchase_orders,

                checkpoint_memory=True,
            )

            # =================================================
            # EXTRACT PREDICTION
            # =================================================

            prediction = extract_prediction(
                result
            )

            # =================================================
            # EXPECTED VALUES
            # =================================================

            source_po = normalize_po(
                gt.get(
                    "source_po"
                )
            )

            expected_po = normalize_po(
                gt.get(
                    "expected_po"
                )
            )

            expected_action = normalize_action(
                gt.get(
                    "expected_action"
                )
            )

            predicted_po = normalize_po(
                prediction.get(
                    "predicted_po"
                )
            )

            predicted_action = normalize_action(
                prediction.get(
                    "predicted_action"
                )
            )

            # =================================================
            # PO EXPECTATION
            # =================================================

            # IMPORTANT:
            # `expected_po` is what the AI is supposed to predict.
            # `source_po` is only the hidden underlying PO used to
            # generate the synthetic invoice.
            #
            # For a missing-PO-reference scenario:
            #     source_po  = actual hidden PO
            #     expected_po = None
            #
            # The AI must NOT receive credit for guessing the hidden
            # PO when the invoice itself does not contain a PO
            # reference. Therefore we always evaluate against
            # expected_po, never source_po.

            evaluation_expected_po = expected_po

            # =================================================
            # CORRECTNESS
            # =================================================

            po_match_correct = (
                predicted_po
                == evaluation_expected_po
            )

            decision_correct = (
                predicted_action
                == expected_action
            )

            # =================================================
            # DISCREPANCY CORRECTNESS
            # =================================================

            expected_discrepancies = (
                normalize_discrepancy_list(
                    gt.get(
                        "expected_discrepancies",
                        [],
                    )
                )
            )

            predicted_discrepancies = (
                normalize_discrepancy_list(
                    prediction.get(
                        "discrepancies",
                        [],
                    )
                )
            )

            discrepancy_match_correct = (
                expected_discrepancies
                == predicted_discrepancies
            )

            # =================================================
            # RECORD
            # =================================================

            record = {

                "invoice":
                    filename,

                "status":
                    "SUCCESS",

                "scenario":
                    gt.get(
                        "scenario"
                    ),

                "expected_po":
                    evaluation_expected_po,

                "ground_truth_expected_po":
                    expected_po,

                "ground_truth_source_po":
                    source_po,

                "predicted_po":
                    predicted_po,

                "expected_action":
                    expected_action,

                "predicted_action":
                    predicted_action,

                "unresolved":
                    predicted_action is None,

                "po_match_correct":
                    po_match_correct,

                "decision_correct":
                    decision_correct,

                "expected_discrepancies":
                    sorted(
                        expected_discrepancies
                    ),

                "predicted_discrepancies":
                    sorted(
                        predicted_discrepancies
                    ),

                "discrepancy_match_correct":
                    discrepancy_match_correct,

                "extraction_confidence":
                    prediction.get(
                        "extraction_confidence"
                    ),

                "matching_confidence":
                    prediction.get(
                        "matching_confidence"
                    ),

                "resolution_confidence":
                    prediction.get(
                        "resolution_confidence"
                    ),

                "explanation":
                    prediction.get(
                        "explanation"
                    ),
            }

            records.append(
                record
            )

            # =================================================
            # TERMINAL RESULT
            # =================================================

            po_symbol = (
                "OK"
                if po_match_correct
                else "WRONG"
            )

            decision_symbol = (
                "OK"
                if decision_correct
                else "WRONG"
            )

            discrepancy_symbol = (
                "OK"
                if discrepancy_match_correct
                else "WRONG"
            )

            print(
                f"  PO: {po_symbol} | "
                f"Decision: {decision_symbol} | "
                f"Discrepancy: {discrepancy_symbol} | "
                f"Predicted: {predicted_action}"
            )

        except Exception as exc:

            print(
                f"  FAILED: {exc}"
            )

            records.append({

                "invoice":
                    filename,

                "status":
                    "FAILED",

                "scenario":
                    gt.get(
                        "scenario"
                    ),

                "error":
                    str(exc),

                "traceback":
                    traceback.format_exc(),
            })

    # ========================================================
    # METRICS
    # ========================================================

    metrics = calculate_metrics(
        records
    )

    # ========================================================
    # OUTPUT
    # ========================================================

    output = {

        "dataset": {

            "invoice_count":
                len(invoices),

            "ground_truth_count":
                len(ground_truth),

            "purchase_order_count":
                len(purchase_orders),
        },

        "metrics":
            metrics,

        "results":
            records,
    }

    EVALUATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        RESULTS_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print(
        "EVALUATION COMPLETE"
    )
    print("=" * 70)

    print(
        f"Total invoices:       "
        f"{metrics['total_invoices']}"
    )

    print(
        f"Successful:           "
        f"{metrics['successful']}"
    )

    print(
        f"Failed:               "
        f"{metrics['failed']}"
    )

    print(
        f"PO Match Accuracy:    "
        f"{metrics['po_match_accuracy_percent']}%"
    )

    print(
        f"Missing PO Detection: "
        f"{metrics['missing_po_detection_accuracy_percent']}%"
    )

    print(
        f"Decision Accuracy:    "
        f"{metrics['decision_accuracy_percent']}%"
    )

    print(
        f"Discrepancy Accuracy: "
        f"{metrics['discrepancy_accuracy_percent']}%"
    )

    print(
        f"APPROVE:              "
        f"{metrics['action_counts']['APPROVE']}"
    )

    print(
        f"REVIEW:               "
        f"{metrics['action_counts']['REVIEW']}"
    )

    print(
        f"ESCALATE:             "
        f"{metrics['action_counts']['ESCALATE']}"
    )

    print(
        f"Average Extraction:   "
        f"{metrics['average_extraction_confidence']}"
    )

    print(
        f"Average Matching:     "
        f"{metrics['average_matching_confidence']}"
    )

    print(
        f"Average Resolution:   "
        f"{metrics['average_resolution_confidence']}"
    )

    # ========================================================
    # SCENARIO BREAKDOWN
    # ========================================================

    print()
    print("-" * 70)
    print("SCENARIO BREAKDOWN")
    print("-" * 70)

    for scenario, stats in sorted(
        metrics["scenario_metrics"].items()
    ):

        po_pct = stats["po_accuracy_percent"]

        po_display = (
            f"{po_pct:6.2f}%"
            if po_pct is not None
            else "  N/A "
        )

        print(
            f"{scenario:25s} "
            f"Total={stats['total']:3d} | "
            f"PO={po_display} | "
            f"Decision={stats['decision_accuracy_percent']:6.2f}% | "
            f"Discrepancy={stats['discrepancy_accuracy_percent']:6.2f}%"
        )

    # ========================================================
    # RESULTS FILE
    # ========================================================

    print()
    print(
        "Results saved to:"
    )

    print(
        RESULTS_FILE
    )

    print("=" * 70)

    return output


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    run_batch_evaluation()