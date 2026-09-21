"""
Example usage of the Invoice Reconciliation LangGraph

This demonstrates how to use the graph orchestration
to process a single invoice end-to-end.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from graph.orchestration import run_reconciliation
from models import PurchaseOrder


# -------------------------------------------------------------------
# Windows / UTF-8 output fix
# -------------------------------------------------------------------

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# -------------------------------------------------------------------
# Load Purchase Orders
# -------------------------------------------------------------------

def load_purchase_orders(json_path: str) -> List[PurchaseOrder]:
    """
    Load purchase orders from company-provided JSON file.

    Expected format:
    {
      "purchase_orders": [
        {
          "po_number": "...",
          "supplier": "...",
          "date": "YYYY-MM-DD",
          "total": 9573.00,
          "currency": "GBP",
          "line_items": [...]
        }
      ]
    }
    """

    with open(json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    po_list = raw_data.get("purchase_orders", [])
    purchase_orders: List[PurchaseOrder] = []

    for po_data in po_list:
        try:
            # Parse date - handle multiple formats
            date_str = po_data.get("date", "")

            try:
                po_date = datetime.strptime(
                    date_str,
                    "%Y-%m-%d"
                )
            except ValueError:
                try:
                    po_date = datetime.strptime(
                        date_str,
                        "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    raise ValueError(
                        f"Invalid date format: {date_str}"
                    )

            po = PurchaseOrder(
                po_number=str(
                    po_data.get("po_number", "")
                ),
                vendor_name=str(
                    po_data.get("supplier", "")
                ),
                total_amount=float(
                    po_data.get("total", 0.0)
                ),
                po_date=po_date,
                line_items=po_data.get(
                    "line_items",
                    []
                ),
                vendor_address=po_data.get(
                    "vendor_address"
                ),
                description=po_data.get(
                    "description"
                )
            )

            purchase_orders.append(po)

        except Exception as e:
            print(
                f"Warning: Skipping invalid PO entry: {e}"
            )
            continue

    return purchase_orders


# -------------------------------------------------------------------
# Example Reconciliation Run
# -------------------------------------------------------------------

def example_reconciliation():
    """Run invoice reconciliation using LangGraph."""

    # ---------------------------------------------------------------
    # IMPORTANT:
    # Use the invoice selected by Streamlit when INVOICE_PATH exists.
    # Otherwise fall back to invoice5.pdf for direct CLI testing.
    # ---------------------------------------------------------------

    invoice_path = os.environ.get(
        "INVOICE_PATH",
        "data/invoices/invoice5.pdf"
    )

    po_path = "data/purchase_orders.json"

    print("\nStarting invoice reconciliation")
    print("-" * 60)
    print(f"Invoice file      : {invoice_path}")
    print(f"PO database file  : {po_path}")

    # Validate files exist
    if not Path(po_path).exists():
        raise FileNotFoundError(
            f"Purchase order file not found: {po_path}"
        )

    if not Path(invoice_path).exists():
        raise FileNotFoundError(
            f"Invoice file not found: {invoice_path}"
        )

    # Load purchase orders
    try:
        purchase_orders = load_purchase_orders(po_path)

        print(
            f"Loaded purchase orders: "
            f"{len(purchase_orders)}"
        )

    except Exception as e:
        raise RuntimeError(
            f"Failed to load purchase orders: {e}"
        ) from e

    print("-" * 60)

    # ---------------------------------------------------------------
    # Run LangGraph reconciliation
    # ---------------------------------------------------------------

    result = run_reconciliation(
        document_path=invoice_path,
        purchase_orders=purchase_orders,
        checkpoint_memory=True
    )

    # ----------------------------------------------------------------
    # Display Results
    # ----------------------------------------------------------------

    print("\n" + "=" * 60)
    print("RECONCILIATION RESULTS")
    print("=" * 60)

    print(
        f"\nCurrent Step     : "
        f"{result.get('current_step')}"
    )

    print(
        f"Execution Trace  : "
        f"{' -> '.join(result.get('execution_trace', []))}"
    )

    # ----------------------------------------------------------------
    # Errors
    # ----------------------------------------------------------------

    if result.get("errors"):
        print("\n❌ Errors:")

        for err in result["errors"]:
            print(f" - {err}")

        return result

    # ----------------------------------------------------------------
    # Document Extraction
    # ----------------------------------------------------------------

    doc_result = result.get("document_result")

    if doc_result:
        print("\n📄 Document Extraction")

        print(
            f"  Confidence : "
            f"{doc_result.confidence:.2%}"
        )

        print(
            f"  Explanation: "
            f"{doc_result.explanation}"
        )

    # ----------------------------------------------------------------
    # Matching
    # ----------------------------------------------------------------

    matching_result = result.get("matching_result")

    if matching_result:
        print("\n🔗 Matching Result")

        print(
            f"  Method     : "
            f"{matching_result.matching_method}"
        )

        print(
            f"  Confidence : "
            f"{matching_result.confidence_score:.2%}"
        )

        if matching_result.matched_po:
            print(
                f"  Matched PO : "
                f"{matching_result.matched_po.po_number}"
            )

        print(
            f"  Explanation: "
            f"{matching_result.explanation}"
        )

    # ----------------------------------------------------------------
    # Discrepancy Analysis
    # ----------------------------------------------------------------

    discrepancy_result = result.get(
        "discrepancy_result"
    )

    if discrepancy_result:
        print("\n⚠️ Discrepancy Analysis")

        print(
            f"  Total      : "
            f"{discrepancy_result.total_discrepancies}"
        )

        print(
            f"  Confidence : "
            f"{discrepancy_result.overall_confidence:.2%}"
        )

        print(
            f"  Summary    : "
            f"{discrepancy_result.summary}"
        )

    # ----------------------------------------------------------------
    # Resolution
    # ----------------------------------------------------------------

    resolution = result.get(
        "resolution_recommendation"
    )

    if resolution:
        print("\n✅ Resolution Recommendation")

        print(
            f"  Action     : "
            f"{resolution.action.value.upper()}"
        )

        print(
            f"  Confidence : "
            f"{resolution.confidence_score:.2%}"
        )

        print("\nExplanation:")
        print(resolution.explanation)

    # ----------------------------------------------------------------
    # Finished
    # ----------------------------------------------------------------

    print("\n" + "=" * 60)
    print(
        "Invoice reconciliation completed successfully"
    )
    print("=" * 60)

    return result


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

if __name__ == "__main__":
    example_reconciliation()