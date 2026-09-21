from datetime import datetime
from matching_agent import MatchingAgent
from models import InvoiceData, PurchaseOrder

def run_test():
    agent = MatchingAgent()

    # 🔥 Invoice without PO reference (Invoice-5 scenario)
    invoice = InvoiceData(
        invoice_number="INV-2024-1005",
        vendor_name="PharmaChem Supplies Ltd",
        total_amount=7977.50,
        invoice_date=datetime(2024, 1, 15),
        po_reference=None
    )

    po_database = [
        PurchaseOrder(
            po_number="PO-2024-001",
            vendor_name="PharmaChem Supplies Limited",
            total_amount=8000.00,
            po_date=datetime(2024, 1, 10)
        ),
        PurchaseOrder(
            po_number="PO-2024-002",
            vendor_name="BioActive Materials UK",
            total_amount=4500.00,
            po_date=datetime(2024, 1, 12)
        )
    ]

    result = agent.match(invoice, po_database)

    print("\n=== MATCHING RESULT ===")
    print("Matched PO:", result.matched_po.po_number if result.matched_po else None)
    print("Confidence:", round(result.confidence_score, 2))
    print("Method:", result.matching_method)
    print("Explanation:", result.explanation)
    print("Details:", result.match_details)


if __name__ == "__main__":
    run_test()
