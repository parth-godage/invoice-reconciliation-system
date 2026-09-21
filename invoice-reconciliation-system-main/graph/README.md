# Invoice Reconciliation LangGraph Orchestration

This module implements a LangGraph-based orchestration system for the multi-agent Invoice Reconciliation workflow.

## Architecture

The graph orchestrates four agents in sequence:

1. **Document Intelligence Agent** - Extracts structured data from invoice documents (PDF/images)
2. **Matching Agent** - Matches invoices to purchase orders using exact/fuzzy matching
3. **Discrepancy Detection Agent** - Compares invoice and PO line items for discrepancies
4. **Resolution Agent** - Recommends action (approve/review/escalate) based on discrepancies

## Graph Flow

```
START
  ↓
extract_document (Document Agent)
  ↓ [confidence >= 0.3?]
  ├─→ match_invoice (Matching Agent)
  │     ↓ [match found?]
  │     ├─→ detect_discrepancies (Discrepancy Agent)
  │     │     ↓
  │     │     resolve (Resolution Agent)
  │     │       ↓ [action?]
  │     │       ├─→ approve
  │     │       ├─→ review
  │     │       └─→ escalate
  │     └─→ no_match_handler → escalate
  └─→ review (low confidence extraction)
```

## Usage

### Basic Usage

```python
from graph.orchestration import run_reconciliation
from models import PurchaseOrder
from datetime import datetime

# Prepare purchase orders
purchase_orders = [
    PurchaseOrder(
        po_number="PO-2024-001",
        vendor_name="Vendor Name",
        total_amount=1000.00,
        po_date=datetime(2024, 1, 15),
        line_items=[]
    )
]

# Run reconciliation
result = run_reconciliation(
    document_path="data/invoices/invoice1.pdf",
    purchase_orders=purchase_orders
)

# Access results
print(f"Action: {result['resolution_recommendation'].action.value}")
print(f"Confidence: {result['resolution_recommendation'].confidence_score}")
```

### Advanced Usage with Checkpointing

```python
from graph.orchestration import compile_graph
from models import PurchaseOrder

# Compile graph with checkpointing
graph = compile_graph(checkpoint_memory=True)

# Initialize state
initial_state = {
    "document_path": "invoice.pdf",
    "purchase_orders": [...],
    "document_result": None,
    "extracted_invoice": None,
    "matching_result": None,
    "discrepancy_result": None,
    "resolution_recommendation": None,
    "errors": [],
    "current_step": "start",
    "execution_trace": []
}

# Execute
final_state = graph.invoke(initial_state)
```

## State Schema

The graph state (`GraphState`) contains:

- **Inputs:**
  - `document_path`: Path to invoice document
  - `purchase_orders`: List of PurchaseOrder objects

- **Intermediate Results:**
  - `document_result`: AgentOutput from Document Agent
  - `extracted_invoice`: InvoiceData extracted from document
  - `matching_result`: MatchingResult from Matching Agent
  - `discrepancy_result`: DiscrepancyDetectionResult
  - `resolution_recommendation`: ResolutionRecommendation

- **Metadata:**
  - `errors`: List of error messages
  - `current_step`: Current processing step
  - `execution_trace`: List of executed nodes

## Conditional Routing

### After Document Extraction
- **Confidence >= 0.3**: Continue to matching
- **Confidence < 0.3**: Route to human review

### After Matching
- **Match found**: Continue to discrepancy detection
- **No match**: Route to no_match_handler → escalate

### After Resolution
- **Action = APPROVE**: Route to approve node
- **Action = REVIEW**: Route to review node
- **Action = ESCALATE**: Route to escalate node

## Error Handling

All errors are captured in the `errors` list in state. Error paths route to `error_handler` node, which logs errors and routes to escalation.

## Data Transformations

The graph handles data transformations between agents:

1. **Document Agent → Matching Agent**: Converts document extraction output to `InvoiceData` format, parsing dates
2. **Matching Agent → Discrepancy Agent**: Converts line items to `LineItem` format for discrepancy detection
3. **Discrepancy Agent → Resolution Agent**: Converts `Discrepancy` objects to `DiscrepancyResult` format

## Files

- `state.py`: Graph state schema definition
- `nodes.py`: Node implementations (one per agent + routing nodes)
- `orchestration.py`: Graph construction and execution logic
- `example_usage.py`: Example usage code
