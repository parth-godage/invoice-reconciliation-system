from resolution_agent import (
    ResolutionAgent,
    DiscrepancyResult,
    ResolutionAction
)

def run_test():
    # Step 1: Create fake discrepancy output (from Discrepancy Detection Agent)
    discrepancies = [
        DiscrepancyResult(
            field_name="unit_price",
            expected_value=125.00,
            actual_value=137.50,
            discrepancy_type="price_mismatch",
            confidence_score=0.90,
            severity="low",
            description="Price increased by 10%"
        )
    ]

    # Optional context (high value invoices logic ke liye)
    context = {
        "invoice_amount": 8000
    }

    # Step 2: Create agent
    agent = ResolutionAgent()

    # Step 3: Run resolution
    result = agent.resolve(
        discrepancies=discrepancies,
        invoice_id="INV-2024-1001",
        context=context
    )

    # Step 4: Print output
    print("\n====== RESOLUTION RESULT ======")
    print(f"Action: {result.action.value}")
    print(f"Confidence: {result.confidence_score}")
    print("\nExplanation:\n")
    print(result.explanation)

    print("\nReasoning Steps:")
    for step in result.reasoning_steps:
        print("-", step)

    print("\nSummary:")
    print(result.discrepancy_summary)


if __name__ == "__main__":
    run_test()
