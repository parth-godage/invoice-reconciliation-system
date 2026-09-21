# AI Finance Controller — Multi-Agent Invoice Reconciliation System

> An AI-powered multi-agent finance controller that automates invoice-to-purchase-order reconciliation, detects discrepancies, and recommends auditable resolution actions using LangGraph.

![Python](https://img.shields.io/badge/Python-3.x-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-red)
![Status](https://img.shields.io/badge/Status-Working%20Prototype-success)

---

## Overview

Invoice reconciliation is a repetitive and error-prone finance operation, especially when invoices contain different layouts, OCR noise, incorrect or missing PO references, quantity mismatches, and pricing discrepancies.

This project implements a **multi-agent AI Finance Controller** using **LangGraph** to automate the invoice reconciliation workflow.

The system:

- Extracts structured information from supplier invoices
- Matches invoices against purchase orders
- Detects financial and structural discrepancies
- Evaluates confidence and risk
- Recommends **APPROVE, REVIEW, or ESCALATE**
- Produces an explainable execution trace for auditability

Instead of relying on a single monolithic AI call, the system uses **specialized agents with clearly defined responsibilities** coordinated through a LangGraph workflow.

---

## Problem

Traditional invoice reconciliation requires finance teams to manually:

- Read invoice documents
- Extract vendor, PO, quantity, price, and total information
- Find the corresponding purchase order
- Compare invoice and PO line items
- Identify discrepancies
- Decide whether an invoice should be approved or investigated

This becomes difficult at scale and becomes even more challenging when documents contain:

- OCR errors
- Different invoice layouts
- Rotated or scanned PDFs
- Missing PO references
- Incorrect PO references
- Quantity mismatches
- Price mismatches
- Missing or additional line items

The goal of this project is to automate this workflow while **preserving confidence, reasoning, and human-review paths**.

---

## Solution

The system uses a **multi-agent architecture** where each agent performs a specialized part of the reconciliation process.

```text
                    ┌─────────────────────┐
                    │       Invoice       │
                    │        PDF          │
                    └──────────┬──────────┘
                               │
                               ▼
              ┌─────────────────────────────┐
              │ Document Intelligence Agent │
              │                             │
              │ • Extract invoice data      │
              │ • Parse line items           │
              │ • Calculate confidence       │
              └──────────────┬──────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │   Matching Agent    │
                  │                     │
                  │ • PO matching       │
                  │ • Vendor matching   │
                  │ • Amount/date check │
                  └──────────┬──────────┘
                             │
                             ▼
             ┌──────────────────────────────┐
             │ Discrepancy Detection Agent  │
             │                              │
             │ • Price differences          │
             │ • Quantity differences        │
             │ • Missing/extra items         │
             │ • Severity & confidence      │
             └──────────────┬───────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │ Resolution Recommendation│
              │          Agent           │
              │                          │
              │ APPROVE / REVIEW /       │
              │ ESCALATE                 │
              └─────────────┬────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │ Final Decision  │
                   │ + Reasoning     │
                   │ + Execution Log │
                   └─────────────────┘
```

---

## Multi-Agent Architecture

### 1. Document Intelligence Agent

Responsible for extracting structured information from invoice documents.

**Responsibilities:**

- Extract supplier/vendor information
- Extract invoice number and date
- Extract PO reference
- Extract line items
- Extract quantities and prices
- Extract invoice totals
- Handle different document layouts
- Handle noisy/scanned documents
- Produce extraction confidence

**Output:** A structured representation of the invoice that can be consumed by downstream agents.

---

### 2. Matching Agent

Responsible for identifying the purchase order corresponding to an invoice.

**Matching strategies:**

- Exact PO reference matching
- Normalized PO reference matching
- Vendor name matching
- Fuzzy vendor matching
- Amount comparison
- Date tolerance matching
- Confidence-based matching

The agent also produces **matching reasoning**, allowing the final decision to be explained rather than treated as a black box.

---

### 3. Discrepancy Detection Agent

Compares the extracted invoice against the matched purchase order.

**Detects:**

- Price mismatches
- Quantity mismatches
- Missing line items
- Extra line items
- Structural discrepancies
- Other invoice/PO inconsistencies

Each detected discrepancy can include:

- Type
- Severity
- Confidence
- Expected value
- Actual value
- Reasoning

The system uses conservative matching techniques to reduce false positives caused by noisy document text.

---

### 4. Resolution Recommendation Agent

The final agent converts reconciliation results into an actionable decision.

| Decision | Meaning |
|---|---|
| **APPROVE** | Invoice appears consistent and can proceed |
| **REVIEW** | Invoice requires human verification |
| **ESCALATE** | Invoice contains significant risk or discrepancies |

The recommendation considers:

- Matching confidence
- Extraction confidence
- Discrepancy severity
- Number and type of discrepancies
- Overall reconciliation risk

Every decision includes an explanation.

---

## LangGraph Orchestration

LangGraph coordinates the specialized agents and maintains structured workflow state.

The workflow supports:

- Conditional routing
- Agent-to-agent state passing
- Confidence-aware processing
- Error-handling paths
- Execution tracing
- Structured final outputs

### Workflow

```text
START
  │
  ▼
Document Intelligence
  │
  ├── Low confidence ──► Review / Error Path
  │
  ▼
Matching Agent
  │
  ├── PO not found ──► Exception / Review Path
  │
  ▼
Discrepancy Detection
  │
  ▼
Resolution Recommendation
  │
  ├── APPROVE
  ├── REVIEW
  └── ESCALATE
```

This makes the system an **agentic workflow rather than a simple linear script**.

---

## Evaluation

The system was evaluated against a **120-invoice synthetic evaluation dataset** containing different invoice and reconciliation scenarios.

### Benchmark Results

| Metric | Result |
|---|---:|
| Invoices Successfully Processed | **120 / 120** |
| Decision Accuracy | **88.33%** |
| Discrepancy Accuracy | **75.00%** |
| PO Match Accuracy | **94.55%** |

The evaluation measures reconciliation performance across a larger benchmark rather than relying only on a few manually selected examples.

### Evaluation Coverage

The benchmark includes scenarios involving:

- Correct PO references
- Missing PO references
- PO reference formatting variations
- Vendor variations
- Price discrepancies
- Quantity discrepancies
- Missing/extra items
- Noisy document extraction
- Different invoice formats

---

## Application

The project includes a Streamlit interface for interacting with the reconciliation system.

The interface provides:

- Invoice upload
- AI reconciliation results
- Extracted document information
- PO matching information
- Discrepancy analysis
- Final resolution recommendation
- Confidence information
- Agent execution trace
- Evaluation results

### Run the Application

```bash
python -m streamlit run app.py
```

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/parth-godage/invoice-reconciliation-system.git
cd invoice-reconciliation-system
```

### 2. Create a Virtual Environment

#### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

If the application requires API credentials, create a `.env` file:

```text
API_KEY=your_api_key_here
```

Never commit API keys, passwords, or other secrets to GitHub.

---

## Running the System

### Streamlit Application

```bash
python -m streamlit run app.py
```

### Command-Line Workflow

```bash
python -m graph.example_usage
```

The workflow produces information including:

- Extracted invoice data
- Extraction confidence
- PO matching result
- Matching reasoning
- Detected discrepancies
- Discrepancy severity
- Final resolution
- Execution trace

---

## Example Reconciliation Scenarios

| Scenario | Description |
|---|---|
| Clean invoice | Correct PO and matching values |
| Scanned invoice | OCR/document extraction challenge |
| Different format | Layout and ordering variation |
| Price discrepancy | Invoice price differs from PO |
| Quantity discrepancy | Invoice quantity differs from PO |
| Missing PO | Invoice does not contain a usable PO reference |
| Line-item discrepancy | Missing or additional items |

These scenarios are designed to test the robustness of the reconciliation workflow rather than only successful happy-path cases.

---

## Explainability & Auditability

A major design goal is to make every reconciliation decision understandable.

```text
Invoice Extraction
        ↓
Extraction Confidence
        ↓
PO Matching
        ↓
Matching Reasoning
        ↓
Discrepancy Analysis
        ↓
Severity / Confidence
        ↓
Resolution Recommendation
        ↓
Execution Trace
```

This makes it possible to understand **why** an invoice was approved, reviewed, or escalated.

---

## Fail-Safe Decision Making

The system is designed to avoid blindly approving uncertain invoices.

When confidence is insufficient or significant discrepancies are detected, the workflow can route the invoice toward human review or escalation.

```text
                 ┌───────────┐
                 │  Invoice  │
                 └─────┬─────┘
                       │
              ┌────────▼────────┐
              │ Risk Evaluation │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       APPROVE       REVIEW      ESCALATE
```

This is particularly important for finance workflows where incorrect approvals can have direct financial consequences.

---

## Project Structure

```text
invoice-reconciliation-system/
│
├── agents/
│   ├── document_agent.py
│   ├── matching_agent.py
│   ├── discrepancy_detection_agent.py
│   └── resolution_agent.py
│
├── graph/
│   ├── state.py
│   ├── nodes.py
│   ├── orchestration.py
│   ├── example_usage.py
│   └── README.md
│
├── models/
│   └── schemas.py
│
├── data/
│   ├── invoices/
│   └── purchase_orders.json
│
├── tests/
│
├── app.py
├── requirements.txt
├── IMPLEMENTATION_SUMMARY.md
└── README.md
```

> The exact repository structure may evolve as the project is developed.

---

## Design Principles

### Agent Specialization

Each agent has a focused responsibility instead of placing the entire task inside one large prompt.

### Confidence Awareness

Confidence information is carried through the workflow and considered during decision-making.

### Explainability

Agents provide reasoning alongside structured outputs.

### Fail-Safe Behavior

Uncertain or risky cases should move toward human review rather than being blindly approved.

### Modular Architecture

Agents, state management, orchestration, and data models are separated to make the system easier to extend.

### Benchmark-Driven Development

System improvements are evaluated using a larger synthetic benchmark rather than relying only on manual examples.

---

## Technology Stack

| Technology | Purpose |
|---|---|
| **Python** | Core application and agent logic |
| **LangGraph** | Multi-agent orchestration |
| **Streamlit** | Interactive application UI |
| **PDF/OCR tooling** | Invoice document extraction |
| **JSON** | Purchase-order and evaluation data |
| **Git/GitHub** | Version control and project delivery |

---

## Known Limitations

- OCR quality can decrease on extremely poor-quality scans.
- Handwritten invoices may require human verification.
- Fuzzy matching can still produce ambiguous cases.
- The current system does not continuously learn from human reviewer feedback.
- The evaluation dataset is synthetic and does not represent every possible production invoice format.
- High-volume production deployment would require additional infrastructure and asynchronous processing.

---

## Future Improvements

Potential extensions include:

- Human-in-the-loop feedback agent
- Reviewer feedback learning loop
- OCR ensemble models
- Large-scale PO retrieval and indexing
- Vector-based vendor/entity resolution
- Async batch processing
- Queue-based invoice processing
- Production observability and monitoring
- Role-based access control
- Persistent audit logs
- Integration with ERP/accounting systems

---

## Demo

A 5-minute project walkthrough demonstrates:

1. The problem
2. Multi-agent architecture
3. Invoice processing
4. PO matching
5. Discrepancy detection
6. Resolution recommendation
7. Explainability and execution trace
8. Evaluation results

**Demo Video:**  
_Add your public 5-minute video link here._

---

## Why This Project Matters

Invoice reconciliation is a practical finance operation where AI agents can provide value beyond simple document extraction.

This project demonstrates how specialized AI agents can work together to transform:

```text
Unstructured Invoice
        ↓
Structured Information
        ↓
PO Reconciliation
        ↓
Discrepancy Detection
        ↓
Risk Evaluation
        ↓
Actionable Finance Decision
```

The focus is not only on using an LLM, but on building a **measurable, explainable, and modular agentic system** around a real finance workflow.

---

## Author

**Parth Godage**

AI / GenAI Builder

Built as an **AI Finance Controller / Multi-Agent Invoice Reconciliation System** using Python and LangGraph.

---

## Project Status

**Working Prototype — Internship Submission**

The system processes invoice reconciliation workflows end-to-end and includes a benchmark-driven evaluation pipeline.
