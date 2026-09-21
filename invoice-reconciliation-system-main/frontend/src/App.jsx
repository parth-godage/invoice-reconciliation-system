import { useEffect, useState } from "react";
import "./index.css";

const API = "http://127.0.0.1:8000";

const agents = [
  {
    key: "extract_document",
    number: "01",
    title: "Document Intelligence",
    description: "Extract invoice data",
  },
  {
    key: "match_invoice",
    number: "02",
    title: "PO Matching",
    description: "Match invoice against PO",
  },
  {
    key: "detect_discrepancies",
    number: "03",
    title: "Discrepancy Detection",
    description: "Identify mismatches",
  },
  {
    key: "resolve",
    number: "04",
    title: "Resolution Agent",
    description: "Recommend next action",
  },
];

function App() {
  const [invoices, setInvoices] = useState([]);
  const [selected, setSelected] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function loadInvoices() {
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API}/invoices`);

      if (!res.ok) {
        throw new Error(`Backend returned ${res.status}`);
      }

      const data = await res.json();

      const list = data.invoices || [];

      setInvoices(list);

      if (list.length && !selected) {
        setSelected(list[0].filename);
      }
    } catch (err) {
      setError(
        "FastAPI connection failed. Make sure the backend is running on port 8000."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInvoices();
  }, []);

  async function runAgent() {
    if (!selected) return;

    setRunning(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch(
        `${API}/reconcile?invoice_filename=${encodeURIComponent(selected)}`,
        {
          method: "POST",
        }
      );

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Reconciliation failed");
      }

      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  const trace = result?.execution_trace || [];

  const resolution =
    result?.resolution_recommendation?.action ||
    result?.action ||
    "";

  const decision = resolution
    ? String(resolution).replaceAll("_", " ").toUpperCase()
    : "WAITING";

  const extraction =
    result?.document_result?.confidence ??
    result?.extraction_confidence;

  const matching =
    result?.matching_result?.confidence ??
    result?.matching_confidence;

  const discrepancy =
    result?.discrepancy_result?.discrepancy_count ??
    result?.discrepancy_result?.discrepancies?.length ??
    0;

  const percentage = (value) => {
    if (value === undefined || value === null) return "—";

    const number = Number(value);

    if (Number.isNaN(number)) return "—";

    return `${Math.round(
      number <= 1 ? number * 100 : number
    )}%`;
  };

  return (
    <div className="app">

      {/* SIDEBAR */}

      <aside className="sidebar">

        <div className="logo-area">
          <div className="logo-mark">
            ✦
          </div>

          <div>
            <div className="logo-name">
              Reconcile<span>AI</span>
            </div>

            <div className="logo-sub">
              Autonomous finance
            </div>
          </div>
        </div>

        <div className="sidebar-label">
          WORKSPACE
        </div>

        <div className="sidebar-item active">
          <span>◈</span>
          Invoice Reconciliation
        </div>

        <div className="sidebar-label second">
          SYSTEM
        </div>

        <div className="system-card">
          <div className="online-dot" />

          <div>
            <strong>System Online</strong>
            <small>FastAPI · LangGraph</small>
          </div>
        </div>

        <div className="sidebar-footer">
          AI Finance Controller
          <span>v1.0</span>
        </div>

      </aside>

      {/* CONTENT */}

      <main className="content">

        {/* TOP BAR */}

        <header className="topbar">

          <div>
            <div className="overline">
              AI FINANCE OPERATIONS
            </div>

            <h1>
              Invoice Reconciliation
            </h1>

            <p>
              Autonomous verification powered by
              multi-agent AI.
            </p>
          </div>

          <div className="top-status">
            <span className="status-dot" />
            AI ENGINE READY
          </div>

        </header>

        {/* ERROR */}

        {error && (
          <div className="error-box">
            <div className="error-icon">!</div>

            <div>
              <strong>Backend connection issue</strong>
              <p>{error}</p>
            </div>

            <button onClick={loadInvoices}>
              Retry
            </button>
          </div>
        )}

        {/* HERO WORKSPACE */}

        <section className="workspace">

          <div className="workspace-top">

            <div>
              <div className="section-label">
                RECONCILIATION RUN
              </div>

              <h2>
                Start an AI reconciliation
              </h2>

              <p>
                Select an invoice and let the agent
                workflow verify it against your
                purchase-order data.
              </p>
            </div>

            <div className="ai-chip">
              <span>✦</span>
              LANGGRAPH
            </div>

          </div>

          <div className="action-row">

            <div className="invoice-selector">

              <div className="file-icon">
                PDF
              </div>

              <div className="invoice-select-content">

                <label>
                  INVOICE
                </label>

                <select
                  value={selected}
                  onChange={(e) => {
                    setSelected(e.target.value);
                    setResult(null);
                  }}
                  disabled={loading || running}
                >

                  {loading && (
                    <option>
                      Loading invoices...
                    </option>
                  )}

                  {!loading &&
                    invoices.length === 0 && (
                      <option>
                        No invoices available
                      </option>
                    )}

                  {invoices.map((invoice) => (
                    <option
                      key={invoice.filename}
                      value={invoice.filename}
                    >
                      {invoice.filename}
                    </option>
                  ))}

                </select>

              </div>

              <span className="select-arrow">
                ↓
              </span>

            </div>

            <button
              className="execute"
              onClick={runAgent}
              disabled={
                !selected ||
                running ||
                loading
              }
            >

              {running ? (
                <>
                  <span className="loader" />
                  Agents Running
                </>
              ) : (
                <>
                  Run AI Agent
                  <span>→</span>
                </>
              )}

            </button>

          </div>

        </section>

        {/* AGENT PIPELINE */}

        <section className="pipeline-section">

          <div className="section-heading">

            <div>
              <div className="section-label">
                MULTI-AGENT ORCHESTRATION
              </div>

              <h2>
                Autonomous workflow
              </h2>
            </div>

            {running && (
              <div className="running">
                <span />
                Processing invoice
              </div>
            )}

          </div>

          <div className="agent-grid">

            {agents.map((agent, index) => {

              const completed =
                trace.includes(agent.key);

              const active =
                running &&
                !completed &&
                index === trace.length;

              return (
                <div
                  className={`agent-card ${
                    completed
                      ? "completed"
                      : active
                      ? "active"
                      : ""
                  }`}
                  key={agent.key}
                >

                  <div className="agent-number">
                    {agent.number}
                  </div>

                  <div className="agent-status">
                    {completed
                      ? "✓"
                      : active
                      ? "●"
                      : "○"}
                  </div>

                  <h3>
                    {agent.title}
                  </h3>

                  <p>
                    {agent.description}
                  </p>

                  <div className="agent-footer">

                    <span>
                      {completed
                        ? "COMPLETED"
                        : active
                        ? "RUNNING"
                        : "WAITING"}
                    </span>

                    <span>→</span>

                  </div>

                </div>
              );
            })}

          </div>

        </section>

        {/* RESULTS */}

        <section className="results-section">

          <div className="section-heading">

            <div>
              <div className="section-label">
                INTELLIGENCE OUTPUT
              </div>

              <h2>
                Reconciliation insights
              </h2>
            </div>

            {result && (
              <span className="result-ready">
                RESULT READY
              </span>
            )}

          </div>

          <div className="metrics">

            <div className="metric-card">

              <span>EXTRACTION</span>

              <strong>
                {percentage(extraction)}
              </strong>

              <small>
                Document Intelligence
              </small>

            </div>

            <div className="metric-card">

              <span>PO MATCH</span>

              <strong>
                {percentage(matching)}
              </strong>

              <small>
                Matching confidence
              </small>

            </div>

            <div className="metric-card">

              <span>DISCREPANCIES</span>

              <strong>
                {result ? discrepancy : "—"}
              </strong>

              <small>
                Issues detected
              </small>

            </div>

            <div className="metric-card decision-card">

              <span>FINAL DECISION</span>

              <strong className={decision.toLowerCase()}>
                {decision}
              </strong>

              <small>
                Resolution Agent
              </small>

            </div>

          </div>

        </section>

        {/* TRACE + DECISION */}

        <section className="bottom-grid">

          {/* TRACE */}

          <div className="panel">

            <div className="panel-header">

              <div>
                <div className="section-label">
                  AGENT TRACE
                </div>

                <h2>
                  Execution timeline
                </h2>
              </div>

              <span>
                {trace.length} / 4
              </span>

            </div>

            <div className="timeline">

              {agents.map((agent, index) => {

                const completed =
                  trace.includes(agent.key);

                return (
                  <div
                    className="timeline-item"
                    key={agent.key}
                  >

                    <div
                      className={`timeline-dot ${
                        completed
                          ? "done"
                          : ""
                      }`}
                    >
                      {completed
                        ? "✓"
                        : agent.number}
                    </div>

                    <div className="timeline-content">

                      <strong>
                        {agent.title}
                      </strong>

                      <span>
                        {completed
                          ? "Agent completed successfully"
                          : "Waiting for execution"}
                      </span>

                    </div>

                  </div>
                );
              })}

            </div>

          </div>

          {/* DECISION */}

          <div className="panel">

            <div className="panel-header">

              <div>
                <div className="section-label">
                  RESOLUTION AGENT
                </div>

                <h2>
                  AI recommendation
                </h2>
              </div>

              <span className="decision-symbol">
                ✦
              </span>

            </div>

            <div
              className={`decision ${
                decision.toLowerCase()
              }`}
            >

              <div className="decision-label">
                RECOMMENDED ACTION
              </div>

              <div className="decision-value">
                {decision}
              </div>

              <p>
                {result
                  ? "The resolution agent has evaluated the reconciliation workflow and produced a recommendation."
                  : "Run the reconciliation workflow to generate an AI recommendation."}
              </p>

            </div>

            {result && (
              <details className="raw-data">

                <summary>
                  View execution data
                </summary>

                <pre>
                  {JSON.stringify(
                    result,
                    null,
                    2
                  )}
                </pre>

              </details>
            )}

          </div>

        </section>

        <footer>
          <span>
            ReconcileAI © 2026
          </span>

          <span>
            React · FastAPI · LangGraph · Multi-Agent AI
          </span>
        </footer>

      </main>

    </div>
  );
}

export default App;