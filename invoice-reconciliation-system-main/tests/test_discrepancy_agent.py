from decimal import Decimal
from discrepancy_detection_agent import (
    DiscrepancyDetectionAgent,
    LineItem
)

def run_test():
    agent = DiscrepancyDetectionAgent(
        price_tolerance_percent=0.01,
        quantity_tolerance_percent=0.01
    )

    # -------- Invoice items --------
    invoice_items = [
        LineItem(
            item_id="API-001",
            description="Paracetamol BP 500mg",
            quantity=Decimal("50"),
            unit_price=Decimal("137.50"),  # ❌ 10% increased
            unit="kg"
        )
    ]

    # -------- PO items --------
    po_items = [
        LineItem(
            item_id="API-001",
            description="Paracetamol BP 500mg",
            quantity=Decimal("50"),
            unit_price=Decimal("125.00"),
            unit="kg"
        )
    ]

    result = agent.detect_discrepancies(
        invoice_items=invoice_items,
        po_items=po_items
    )

    print("\n====== DISCREPANCY RESULT ======")
    print("Summary:", result.summary)
    print("Overall confidence:", result.overall_confidence)

    for d in result.discrepancies:
        print("\n--- Discrepancy ---")
        print("Type:", d.discrepancy_type.value)
        print("Severity:", d.severity.value)
        print("Item:", d.item_id)
        print("Explanation:", d.explanation)
        print("Confidence:", d.confidence)

if __name__ == "__main__":
    run_test()
