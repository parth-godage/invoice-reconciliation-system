import os
import json
import re
import sys
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Finance Controller",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
INVOICE_DIR = BASE_DIR / "data" / "invoices"


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>
/* ============================================================
   ENTERPRISE FINANCE UI
   ============================================================ */

:root {
    --bg: #070b12;
    --panel: #0d1420;
    --panel-2: #101927;
    --border: rgba(148, 163, 184, 0.14);
    --border-strong: rgba(148, 163, 184, 0.22);
    --text: #f8fafc;
    --muted: #8b9ab0;
    --muted-2: #64748b;
    --accent: #7dd3fc;
    --green: #4ade80;
    --amber: #fbbf24;
    --red: #fb7185;
}

/* App shell */
.stApp {
    background:
        radial-gradient(circle at 85% 0%, rgba(56, 189, 248, 0.07), transparent 28%),
        radial-gradient(circle at 0% 20%, rgba(99, 102, 241, 0.05), transparent 25%),
        var(--bg);
    color: var(--text);
}

.block-container {
    max-width: 1500px;
    padding: 2rem 2.5rem 4rem;
}

#MainMenu, footer {
    visibility: hidden;
}

header[data-testid="stHeader"] {
    background: transparent;
}

/* Typography */
html, body, [class*="css"] {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.section {
    margin: 32px 0 14px;
    color: var(--text);
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.2px;
}

/* Top application header */
.app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 0 26px;
}

.brand-wrap {
    display: flex;
    align-items: center;
    gap: 14px;
}

.brand-mark {
    width: 46px;
    height: 46px;
    border-radius: 13px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(145deg, #172235, #0e1725);
    border: 1px solid var(--border-strong);
    box-shadow: 0 10px 30px rgba(0,0,0,.22);
    font-size: 21px;
}

.brand-title {
    color: var(--text);
    font-size: 25px;
    font-weight: 760;
    letter-spacing: -0.7px;
    line-height: 1.1;
}

.brand-subtitle {
    color: var(--muted);
    font-size: 12px;
    margin-top: 4px;
    letter-spacing: .1px;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 999px;
    background: rgba(34, 197, 94, .07);
    border: 1px solid rgba(74, 222, 128, .20);
    color: #86efac;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .5px;
}

.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 10px rgba(74, 222, 128, .7);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #080e18;
    border-right: 1px solid rgba(148, 163, 184, .10);
}

section[data-testid="stSidebar"] > div {
    padding: 1.25rem 1rem;
}

.sidebar-brand {
    padding: 8px 4px 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 18px;
}

.sidebar-brand-title {
    color: var(--text);
    font-size: 16px;
    font-weight: 750;
}

.sidebar-brand-subtitle {
    color: var(--muted-2);
    font-size: 11px;
    margin-top: 4px;
}

.sidebar-module {
    margin-top: 18px;
    padding: 14px;
    border-radius: 13px;
    background: rgba(15, 23, 42, .55);
    border: 1px solid var(--border);
}

.sidebar-module-title {
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .8px;
    margin-bottom: 10px;
}

.sidebar-item {
    color: #94a3b8;
    font-size: 12px;
    padding: 5px 0;
}

/* Pipeline */
.pipeline-shell {
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 18px;
    background: rgba(13, 20, 32, .72);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
}

.pipeline-card {
    background: linear-gradient(145deg, #111b2a, #0c1420);
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 14px 10px;
    text-align: center;
    min-height: 76px;
}

.pipeline-icon {
    font-size: 18px;
    opacity: .95;
}

.pipeline-name {
    margin-top: 7px;
    font-weight: 650;
    color: #dbe4ef;
    font-size: 11px;
}

.arrow {
    text-align: center;
    padding-top: 24px;
    color: #475569;
    font-size: 17px;
}

/* Metric cards */
.metric-box {
    background: linear-gradient(145deg, rgba(16, 25, 39, .95), rgba(11, 18, 29, .95));
    border: 1px solid var(--border);
    border-radius: 15px;
    padding: 17px 18px;
    min-height: 105px;
    box-shadow: 0 8px 24px rgba(0,0,0,.10);
}

.metric-label {
    color: var(--muted);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: .9px;
    font-weight: 650;
}

.metric-number {
    margin-top: 9px;
    font-size: 27px;
    font-weight: 760;
    color: var(--text);
    letter-spacing: -.5px;
}

/* Result cards */
.result-card {
    background: rgba(13, 20, 32, .78);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 17px 18px;
    min-height: 76px;
}

.result-label {
    color: var(--muted-2);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: .8px;
    font-weight: 650;
}

.result-value {
    margin-top: 6px;
    font-size: 15px;
    font-weight: 650;
    color: #e5edf7;
    word-break: break-word;
}

/* Decision cards */
.approve, .review, .escalate {
    border-radius: 14px;
    padding: 16px 18px;
    min-height: 105px;
}

.approve {
    border: 1px solid rgba(74, 222, 128, .24);
    background: rgba(22, 101, 52, .14);
    color: #86efac;
}

.review {
    border: 1px solid rgba(251, 191, 36, .24);
    background: rgba(146, 95, 0, .12);
    color: #fde68a;
}

.escalate {
    border: 1px solid rgba(251, 113, 133, .24);
    background: rgba(127, 29, 29, .13);
    color: #fda4af;
}

/* Streamlit controls */
.stButton > button {
    border-radius: 11px !important;
    min-height: 44px;
    font-weight: 700 !important;
    border: 1px solid rgba(125, 211, 252, .22) !important;
    background: linear-gradient(135deg, #14283a, #102033) !important;
    color: #e0f2fe !important;
    transition: all .18s ease;
}

.stButton > button:hover {
    border-color: rgba(125, 211, 252, .45) !important;
    transform: translateY(-1px);
    box-shadow: 0 8px 24px rgba(14, 165, 233, .10);
}

.stDownloadButton > button {
    border-radius: 10px !important;
    font-weight: 650 !important;
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    background: #0d1522 !important;
    border-color: var(--border-strong) !important;
    border-radius: 10px !important;
}

/* Dataframes */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 13px;
    overflow: hidden;
}

/* Tabs / expanders */
[data-testid="stExpander"] {
    background: rgba(13, 20, 32, .58);
    border: 1px solid var(--border);
    border-radius: 13px;
    margin-bottom: 9px;
}

[data-testid="stExpander"] summary {
    font-weight: 650;
}

/* Info / alert boxes */
[data-testid="stAlert"] {
    border-radius: 12px;
    border: 1px solid var(--border);
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: rgba(13, 20, 32, .55);
    border: 1px dashed rgba(148, 163, 184, .24);
    border-radius: 14px;
    padding: 8px;
}

/* Small responsive cleanup */
@media (max-width: 900px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .brand-title {
        font-size: 21px;
    }
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

def percent(value):
    """
    Convert values such as:
      0.75 -> 75.00%
      75 -> 75.00%
    """
    if value is None:
        return "N/A"

    try:
        value = float(value)

        if value <= 1:
            value *= 100

        return f"{value:.2f}%"

    except Exception:
        return "N/A"


def extract_result(output):
    """
    Extract structured information from the existing
    example_usage terminal output.

    This is only a compatibility layer while the backend
    still prints results instead of returning a Python object.
    """

    data = {
        "step": "N/A",
        "trace": "N/A",
        "extraction_confidence": None,
        "matching_confidence": None,
        "discrepancies": None,
        "resolution": "N/A",
        "matched_po": "N/A",
        "matching_method": "N/A",
        "extraction_explanation": "",
        "matching_explanation": "",
        "discrepancy_summary": "",
        "resolution_explanation": "",
    }

    # Current step
    m = re.search(
        r"Current Step\s*:\s*(.+)",
        output,
        re.IGNORECASE,
    )

    if m:
        data["step"] = m.group(1).strip()

    # Execution trace
    m = re.search(
        r"Execution Trace\s*:\s*(.+)",
        output,
        re.IGNORECASE,
    )

    if m:
        data["trace"] = m.group(1).strip()

    # Extraction confidence
    m = re.search(
        r"Document Extraction.*?"
        r"Confidence\s*:\s*([\d.]+)%",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["extraction_confidence"] = float(m.group(1))

    # Matching method
    m = re.search(
        r"Method\s*:\s*(.+)",
        output,
        re.IGNORECASE,
    )

    if m:
        data["matching_method"] = m.group(1).strip()

    # Matching confidence
    m = re.search(
        r"Matching Result.*?"
        r"Confidence\s*:\s*([\d.]+)%",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["matching_confidence"] = float(m.group(1))

    # Matched PO
    m = re.search(
        r"Matched PO\s*:\s*(.+)",
        output,
        re.IGNORECASE,
    )

    if m:
        data["matched_po"] = m.group(1).strip()

    # Discrepancies
    m = re.search(
        r"Discrepancy Analysis.*?"
        r"Total\s*:\s*(\d+)",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["discrepancies"] = int(m.group(1))

    # Resolution
    m = re.search(
        r"Resolution Recommendation.*?"
        r"Action\s*:\s*([A-Za-z_]+)",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["resolution"] = m.group(1).upper()

    # Explanation blocks
    m = re.search(
        r"Document Extraction.*?"
        r"Explanation:\s*(.*?)(?=\n\s*\n|🔗|Matching Result)",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["extraction_explanation"] = m.group(1).strip()

    m = re.search(
        r"Matching Result.*?"
        r"Explanation:\s*(.*?)(?=\n\s*\n|⚠️|Discrepancy Analysis)",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["matching_explanation"] = m.group(1).strip()

    m = re.search(
        r"Discrepancy Analysis.*?"
        r"Summary\s*:\s*(.*?)(?=\n\s*\n|✅|Resolution Recommendation)",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["discrepancy_summary"] = m.group(1).strip()

    m = re.search(
        r"Resolution Recommendation.*?"
        r"Explanation:\s*(.*?)(?=\n={5,}|Invoice reconciliation completed)",
        output,
        re.IGNORECASE | re.DOTALL,
    )

    if m:
        data["resolution_explanation"] = m.group(1).strip()

    return data


def run_reconciliation(invoice_path):
    """
    Run the existing LangGraph application.

    IMPORTANT:
    We pass the selected invoice to the backend through
    INVOICE_PATH.

    example_usage.py must read this environment variable.
    """

    env = os.environ.copy()

    # Fix Windows encoding problem.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    # Pass selected invoice to backend.
    env["INVOICE_PATH"] = str(invoice_path)

    command = [
        sys.executable,
        "-m",
        "graph.example_usage",
    ]

    try:

        process = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=180,
        )

        stdout = process.stdout or ""
        stderr = process.stderr or ""

        output = stdout

        if stderr.strip():
            output += "\n\n" + stderr

        return process.returncode, output

    except subprocess.TimeoutExpired:

        return (
            -1,
            "The reconciliation process timed out after 180 seconds.",
        )

    except Exception as e:

        return (
            -1,
            f"Could not start reconciliation:\n\n{e}",
        )


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="app-header">
        <div class="brand-wrap">
            <div class="brand-mark">◈</div>
            <div>
                <div class="brand-title">AI Finance Controller</div>
                <div class="brand-subtitle">
                    Autonomous invoice reconciliation · LangGraph multi-agent workflow
                </div>
            </div>
        </div>
        <div class="status-pill">
            <span class="status-dot"></span>
            SYSTEM OPERATIONAL
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown(
    """
    <div class="sidebar-brand">
        <div class="sidebar-brand-title">Finance Operations</div>
        <div class="sidebar-brand-subtitle">AI-powered reconciliation workspace</div>
    </div>
    """,
    unsafe_allow_html=True,
)

mode = st.sidebar.radio(
    "Workspace",
    [
        "Single Invoice",
        "Batch Evaluation",
    ],
)

st.sidebar.markdown(
    """
    <div class="sidebar-module">
        <div class="sidebar-module-title">AI Pipeline</div>
        <div class="sidebar-item">◈ LangGraph orchestration</div>
        <div class="sidebar-item">▣ Document intelligence</div>
        <div class="sidebar-item">↗ Purchase-order matching</div>
        <div class="sidebar-item">⚠ Discrepancy detection</div>
        <div class="sidebar-item">◆ Risk-aware resolution</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown(
    """
    <div class="sidebar-module">
        <div class="sidebar-module-title">Controls</div>
        <div class="sidebar-item">Confidence-aware decisions</div>
        <div class="sidebar-item">Auditable execution trace</div>
        <div class="sidebar-item">Ground-truth evaluation</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.caption(
    "AI Finance Controller · Reconciliation Platform"
)


# ============================================================
# PIPELINE
# ============================================================

st.markdown(
    '<div class="section">Reconciliation Workflow</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="pipeline-shell">', unsafe_allow_html=True)

p1, a1, p2, a2, p3, a3, p4 = st.columns(
    [1.6, 0.3, 1.6, 0.3, 1.6, 0.3, 1.6]
)

with p1:
    st.markdown(
        """
        <div class="pipeline-card">
            <div class="pipeline-icon">▣</div>
            <div class="pipeline-name">DOCUMENT INTELLIGENCE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with a1:
    st.markdown('<div class="arrow">›</div>', unsafe_allow_html=True)

with p2:
    st.markdown(
        """
        <div class="pipeline-card">
            <div class="pipeline-icon">↗</div>
            <div class="pipeline-name">PO MATCHING</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with a2:
    st.markdown('<div class="arrow">›</div>', unsafe_allow_html=True)

with p3:
    st.markdown(
        """
        <div class="pipeline-card">
            <div class="pipeline-icon">⚠</div>
            <div class="pipeline-name">DISCREPANCY ANALYSIS</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with a3:
    st.markdown('<div class="arrow">›</div>', unsafe_allow_html=True)

with p4:
    st.markdown(
        """
        <div class="pipeline-card">
            <div class="pipeline-icon">◆</div>
            <div class="pipeline-name">RISK RESOLUTION</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('</div>', unsafe_allow_html=True)



# ============================================================
# SINGLE INVOICE
# ============================================================

if mode == "Single Invoice":

    st.markdown(
        '<div class="section">Single Invoice Analysis</div>',
        unsafe_allow_html=True,
    )

    if not INVOICE_DIR.exists():

        st.error(
            f"Invoice directory not found:\n\n{INVOICE_DIR}"
        )

        st.stop()

    invoices = sorted(INVOICE_DIR.glob("*.pdf"))

    if not invoices:

        st.warning(
            "No PDF invoices found in data/invoices."
        )

        st.stop()

    selected_invoice = st.selectbox(
        "Select invoice",
        invoices,
        format_func=lambda x: x.name,
    )

    st.markdown(
        f"""
        <div class="result-card">
            <div class="result-label">SELECTED DOCUMENT</div>
            <div class="result-value">
                {selected_invoice.name}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    run = st.button(
        "🚀 Run AI Reconciliation",
        type="primary",
        use_container_width=True,
    )

    if run:

        with st.spinner(
            f"Analyzing {selected_invoice.name}..."
        ):

            return_code, output = run_reconciliation(
                selected_invoice
            )

        st.session_state["last_output"] = output
        st.session_state["last_invoice"] = str(
            selected_invoice
        )
        st.session_state["last_return_code"] = return_code

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    if "last_output" in st.session_state:

        output = st.session_state["last_output"]
        return_code = st.session_state["last_return_code"]

        result = extract_result(output)

        st.markdown(
            '<div class="section">Reconciliation Results</div>',
            unsafe_allow_html=True,
        )

        # ====================================================
        # ERROR HANDLING
        # ====================================================

        if return_code != 0:

            st.error(
                "The backend process returned an error."
            )

            with st.expander(
                "View backend output",
                expanded=True,
            ):
                st.code(
                    output,
                    language="text",
                )

        # ====================================================
        # KPI
        # ====================================================

        k1, k2, k3, k4 = st.columns(4)

        with k1:

            value = percent(
                result["extraction_confidence"]
            )

            st.markdown(
                f"""
                <div class="metric-box">
                    <div class="metric-label">
                        Extraction Confidence
                    </div>
                    <div class="metric-number">
                        {value}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with k2:

            value = percent(
                result["matching_confidence"]
            )

            st.markdown(
                f"""
                <div class="metric-box">
                    <div class="metric-label">
                        Match Confidence
                    </div>
                    <div class="metric-number">
                        {value}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with k3:

            value = (
                str(result["discrepancies"])
                if result["discrepancies"] is not None
                else "N/A"
            )

            st.markdown(
                f"""
                <div class="metric-box">
                    <div class="metric-label">
                        Discrepancies
                    </div>
                    <div class="metric-number">
                        {value}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with k4:

            decision = result["resolution"]

            if decision == "APPROVE":
                css = "approve"

            elif decision == "ESCALATE":
                css = "escalate"

            else:
                css = "review"

            st.markdown(
                f"""
                <div class="{css}">
                    <div class="metric-label">
                        FINAL DECISION
                    </div>
                    <div class="metric-number">
                        {decision}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ====================================================
        # DECISION DETAILS
        # ====================================================

        st.markdown(
            '<div class="section">Decision Details</div>',
            unsafe_allow_html=True,
        )

        d1, d2, d3 = st.columns(3)

        with d1:

            st.markdown(
                f"""
                <div class="result-card">
                    <div class="result-label">
                        CURRENT STEP
                    </div>
                    <div class="result-value">
                        {result["step"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with d2:

            st.markdown(
                f"""
                <div class="result-card">
                    <div class="result-label">
                        MATCHED PURCHASE ORDER
                    </div>
                    <div class="result-value">
                        {result["matched_po"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with d3:

            st.markdown(
                f"""
                <div class="result-card">
                    <div class="result-label">
                        MATCHING METHOD
                    </div>
                    <div class="result-value">
                        {result["matching_method"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ====================================================
        # EXPLANATIONS
        # ====================================================

        st.markdown(
            '<div class="section">AI Analysis</div>',
            unsafe_allow_html=True,
        )

        with st.expander(
            "📄 Document Extraction",
            expanded=True,
        ):

            if result["extraction_explanation"]:
                st.write(
                    result["extraction_explanation"]
                )
            else:
                st.info(
                    "No extraction explanation returned."
                )

        with st.expander(
            "🔗 Purchase Order Matching",
            expanded=True,
        ):

            if result["matching_explanation"]:
                st.write(
                    result["matching_explanation"]
                )
            else:
                st.info(
                    "No matching explanation returned."
                )

        with st.expander(
            "⚠️ Discrepancy Analysis",
            expanded=True,
        ):

            if result["discrepancy_summary"]:
                st.write(
                    result["discrepancy_summary"]
                )
            else:
                st.info(
                    "No discrepancy summary returned."
                )

        with st.expander(
            "🛡️ Resolution Reasoning",
            expanded=True,
        ):

            if result["resolution_explanation"]:
                st.write(
                    result["resolution_explanation"]
                )
            else:
                st.info(
                    "No resolution explanation returned."
                )

        # ====================================================
        # TRACE
        # ====================================================

        st.markdown(
            '<div class="section">Execution Trace</div>',
            unsafe_allow_html=True,
        )

        if result["trace"] != "N/A":

            trace_parts = [
                x.strip()
                for x in result["trace"].split("->")
            ]

            trace_df = pd.DataFrame(
                {
                    "Step": range(
                        1,
                        len(trace_parts) + 1,
                    ),
                    "Agent / Node": trace_parts,
                }
            )

            st.dataframe(
                trace_df,
                hide_index=True,
                use_container_width=True,
            )

        with st.expander(
            "View raw backend output"
        ):

            st.code(
                output,
                language="text",
            )


# ============================================================
# BATCH EVALUATION
# ============================================================

else:

    EVALUATION_DIR = BASE_DIR / "data" / "evaluation"
    EVALUATOR_FILE = EVALUATION_DIR / "evaluate.py"
    RESULTS_FILE = EVALUATION_DIR / "results.json"
    EVALUATION_INVOICE_DIR = EVALUATION_DIR / "invoices"

    st.markdown(
        '<div class="section">Batch Invoice Evaluation</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "Run the real LangGraph batch evaluator against the "
        "evaluation dataset. Results are loaded from the "
        "generated results.json file — no metrics are hardcoded."
    )

    # --------------------------------------------------------
    # DATASET STATUS
    # --------------------------------------------------------

    invoice_files = sorted(
        EVALUATION_INVOICE_DIR.glob("*.pdf")
    ) if EVALUATION_INVOICE_DIR.exists() else []

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "Evaluation Invoices",
            len(invoice_files),
        )

    with c2:
        st.metric(
            "Evaluator",
            "READY" if EVALUATOR_FILE.exists() else "MISSING",
        )

    with c3:
        st.metric(
            "Previous Results",
            "AVAILABLE" if RESULTS_FILE.exists() else "NONE",
        )

    st.write("")

    # --------------------------------------------------------
    # RUN BATCH
    # --------------------------------------------------------

    run_batch = st.button(
        "🚀 Run Batch Evaluation",
        type="primary",
        use_container_width=True,
    )

    if run_batch:

        if not EVALUATOR_FILE.exists():
            st.error(
                f"Evaluation script not found:\n\n"
                f"{EVALUATOR_FILE}"
            )
            st.stop()

        if not invoice_files:
            st.error(
                "No evaluation invoices were found in:\n\n"
                f"{EVALUATION_INVOICE_DIR}"
            )
            st.stop()

        with st.spinner(
            f"Running LangGraph evaluation on "
            f"{len(invoice_files)} invoices..."
        ):

            try:

                process = subprocess.run(
                    [
                        sys.executable,
                        str(EVALUATOR_FILE),
                    ],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env={
                        **os.environ,
                        "PYTHONIOENCODING": "utf-8",
                        "PYTHONUTF8": "1",
                    },
                    timeout=1800,
                )

                stdout = process.stdout or ""
                stderr = process.stderr or ""

                combined_output = stdout

                if stderr.strip():
                    combined_output += (
                        "\n\n" + stderr
                    )

                st.session_state[
                    "batch_output"
                ] = combined_output

                st.session_state[
                    "batch_return_code"
                ] = process.returncode

                # Force a fresh result read after the evaluator
                # finishes.
                if RESULTS_FILE.exists():
                    st.session_state[
                        "batch_results_timestamp"
                    ] = RESULTS_FILE.stat().st_mtime

            except subprocess.TimeoutExpired:

                st.session_state[
                    "batch_output"
                ] = (
                    "Batch evaluation timed out after "
                    "30 minutes."
                )

                st.session_state[
                    "batch_return_code"
                ] = -1

            except Exception as exc:

                st.session_state[
                    "batch_output"
                ] = (
                    f"Could not start batch evaluation:\n\n"
                    f"{exc}"
                )

                st.session_state[
                    "batch_return_code"
                ] = -1

    # --------------------------------------------------------
    # LOAD RESULTS
    # --------------------------------------------------------

    batch_data = None

    if RESULTS_FILE.exists():

        try:

            with open(
                RESULTS_FILE,
                "r",
                encoding="utf-8",
            ) as f:
                batch_data = json.load(f)

        except Exception as exc:

            st.warning(
                "results.json exists but could not be read."
            )

            with st.expander(
                "View results loading error"
            ):
                st.code(
                    str(exc),
                    language="text",
                )

    # --------------------------------------------------------
    # EVALUATION ERROR
    # --------------------------------------------------------

    if (
        "batch_return_code" in st.session_state
        and st.session_state["batch_return_code"] != 0
    ):

        st.error(
            "The batch evaluator returned an error."
        )

        with st.expander(
            "View evaluator output",
            expanded=True,
        ):

            st.code(
                st.session_state.get(
                    "batch_output",
                    "",
                ),
                language="text",
            )

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    if batch_data:

        metrics = (
            batch_data.get(
                "metrics",
                {}
            )
            or {}
        )

        dataset = (
            batch_data.get(
                "dataset",
                {}
            )
            or {}
        )

        st.markdown(
            '<div class="section">Evaluation Metrics</div>',
            unsafe_allow_html=True,
        )

        total = metrics.get(
            "total_invoices",
            dataset.get(
                "invoice_count",
                len(invoice_files),
            ),
        )

        successful = metrics.get(
            "successful",
            0,
        )

        failed = metrics.get(
            "failed",
            0,
        )

        po_accuracy = metrics.get(
            "po_match_accuracy_percent"
        )

        decision_accuracy = metrics.get(
            "decision_accuracy_percent"
        )

        discrepancy_accuracy = metrics.get(
            "discrepancy_accuracy_percent"
        )

        missing_po_accuracy = metrics.get(
            "missing_po_detection_accuracy_percent"
        )

        avg_extraction = metrics.get(
            "average_extraction_confidence"
        )

        avg_matching = metrics.get(
            "average_matching_confidence"
        )

        avg_resolution = metrics.get(
            "average_resolution_confidence"
        )

        # First KPI row
        k1, k2, k3, k4 = st.columns(4)

        with k1:
            st.metric(
                "Total Invoices",
                total,
            )

        with k2:
            st.metric(
                "Successful",
                successful,
            )

        with k3:
            st.metric(
                "Failed",
                failed,
            )

        with k4:
            st.metric(
                "PO Match Accuracy",
                percent(po_accuracy),
            )

        # Second KPI row
        k5, k6, k7, k8 = st.columns(4)

        with k5:
            st.metric(
                "Decision Accuracy",
                percent(decision_accuracy),
            )

        with k6:
            st.metric(
                "Discrepancy Accuracy",
                percent(discrepancy_accuracy),
            )

        with k7:
            st.metric(
                "Missing PO Detection",
                percent(missing_po_accuracy),
            )

        with k8:
            st.metric(
                "Avg Resolution Confidence",
                percent(avg_resolution),
            )

        # Confidence row
        st.markdown(
            '<div class="section">Agent Confidence</div>',
            unsafe_allow_html=True,
        )

        q1, q2, q3 = st.columns(3)

        with q1:
            st.metric(
                "Extraction Confidence",
                percent(avg_extraction),
            )

        with q2:
            st.metric(
                "Matching Confidence",
                percent(avg_matching),
            )

        with q3:
            st.metric(
                "Resolution Confidence",
                percent(avg_resolution),
            )

        # ----------------------------------------------------
        # ACTION COUNTS
        # ----------------------------------------------------

        st.markdown(
            '<div class="section">Final Decisions</div>',
            unsafe_allow_html=True,
        )

        action_counts = (
            metrics.get(
                "action_counts",
                {}
            )
            or {}
        )

        a1, a2, a3 = st.columns(3)

        with a1:
            st.metric(
                "APPROVE",
                action_counts.get(
                    "APPROVE",
                    0,
                ),
            )

        with a2:
            st.metric(
                "REVIEW",
                action_counts.get(
                    "REVIEW",
                    0,
                ),
            )

        with a3:
            st.metric(
                "ESCALATE",
                action_counts.get(
                    "ESCALATE",
                    0,
                ),
            )

        # ----------------------------------------------------
        # SCENARIO BREAKDOWN
        # ----------------------------------------------------

        scenario_metrics = (
            metrics.get(
                "scenario_metrics",
                {}
            )
            or {}
        )

        if scenario_metrics:

            st.markdown(
                '<div class="section">Scenario Breakdown</div>',
                unsafe_allow_html=True,
            )

            scenario_rows = []

            for scenario, stats in sorted(
                scenario_metrics.items()
            ):

                scenario_rows.append(
                    {
                        "Scenario": scenario,
                        "Total": stats.get(
                            "total",
                            0,
                        ),
                        "PO Accuracy": percent(
                            stats.get(
                                "po_accuracy_percent"
                            )
                        ),
                        "Decision Accuracy": percent(
                            stats.get(
                                "decision_accuracy_percent"
                            )
                        ),
                        "Discrepancy Accuracy": percent(
                            stats.get(
                                "discrepancy_accuracy_percent"
                            )
                        ),
                    }
                )

            st.dataframe(
                pd.DataFrame(
                    scenario_rows
                ),
                hide_index=True,
                use_container_width=True,
            )

        # ----------------------------------------------------
        # PER-INVOICE RESULTS
        # ----------------------------------------------------

        records = (
            batch_data.get(
                "results",
                []
            )
            or []
        )

        st.markdown(
            '<div class="section">Invoice Results</div>',
            unsafe_allow_html=True,
        )

        if records:

            rows = []

            for record in records:

                rows.append(
                    {
                        "Invoice": record.get(
                            "invoice",
                            "N/A",
                        ),
                        "Scenario": record.get(
                            "scenario",
                            "N/A",
                        ),
                        "Expected PO": record.get(
                            "expected_po",
                            "N/A",
                        ),
                        "Predicted PO": record.get(
                            "predicted_po",
                            "N/A",
                        ),
                        "Expected Action": record.get(
                            "expected_action",
                            "N/A",
                        ),
                        "Predicted Action": record.get(
                            "predicted_action",
                            "N/A",
                        ),
                        "PO Correct": (
                            "✓"
                            if record.get(
                                "po_match_correct"
                            ) is True
                            else "✗"
                        ),
                        "Decision Correct": (
                            "✓"
                            if record.get(
                                "decision_correct"
                            ) is True
                            else "✗"
                        ),
                        "Discrepancy Correct": (
                            "✓"
                            if record.get(
                                "discrepancy_correct"
                            ) is True
                            else "✗"
                        ),
                        "Extraction": percent(
                            record.get(
                                "extraction_confidence"
                            )
                        ),
                        "Matching": percent(
                            record.get(
                                "matching_confidence"
                            )
                        ),
                        "Resolution": percent(
                            record.get(
                                "resolution_confidence"
                            )
                        ),
                    }
                )

            results_df = pd.DataFrame(rows)

            st.dataframe(
                results_df,
                hide_index=True,
                use_container_width=True,
            )

            # CSV export
            csv_data = results_df.to_csv(
                index=False
            )

            st.download_button(
                "⬇️ Export Batch Results CSV",
                data=csv_data,
                file_name="invoice_batch_results.csv",
                mime="text/csv",
                use_container_width=True,
            )

        else:

            st.info(
                "No per-invoice results are available."
            )

        # ----------------------------------------------------
        # RAW EVALUATOR OUTPUT
        # ----------------------------------------------------

        if "batch_output" in st.session_state:

            with st.expander(
                "🔍 View Batch Evaluator Output"
            ):

                st.code(
                    st.session_state[
                        "batch_output"
                    ],
                    language="text",
                )

    else:

        st.markdown(
            '<div class="section">Evaluation Metrics</div>',
            unsafe_allow_html=True,
        )

        st.info(
            "No batch results loaded yet. "
            "Click **Run Batch Evaluation** to run "
            "the complete evaluation dataset."
        )

        empty_df = pd.DataFrame(
            columns=[
                "Invoice",
                "Scenario",
                "Expected PO",
                "Predicted PO",
                "Expected Action",
                "Predicted Action",
                "PO Correct",
                "Decision Correct",
                "Discrepancy Correct",
                "Extraction",
                "Matching",
                "Resolution",
            ]
        )

        st.dataframe(
            empty_df,
            hide_index=True,
            use_container_width=True,
        )
