import { useEffect, useMemo, useState } from "react";

const API_BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

function Icon({ name, size = 20 }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.8",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };

  const paths = {
    spark: <><path d="m12 3-1.2 4.2L7 8.5l3.8 1.3L12 14l1.2-4.2L17 8.5l-3.8-1.3L12 3Z"/><path d="m19 13-.7 2.3L16 16l2.3.7L19 19l.7-2.3L22 16l-2.3-.7L19 13Z"/><path d="M5 15l-.5 1.5L3 17l1.5.5L5 19l.5-1.5L7 17l-1.5-.5L5 15Z"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h6"/></>,
    play: <path d="m9 6 9 6-9 6V6Z"/>,
    refresh: <><path d="M20 11a8.1 8.1 0 0 0-14.7-4L3 10"/><path d="M3 5v5h5"/><path d="M4 13a8.1 8.1 0 0 0 14.7 4L21 14"/><path d="M21 19v-5h-5"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    alert: <><path d="M10.3 3.6 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></>,
    chevron: <path d="m6 9 6 6 6-6"/>,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
  };

  return <svg {...common}>{paths[name] || paths.file}</svg>;
}

function prettyAction(value) {
  const raw = typeof value === "string" ? value : value?.action;
  return (raw || "unknown").toString().replaceAll("_", " ").toUpperCase();
}

function confidence(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (Number.isNaN(n)) return null;
  return n <= 1 ? Math.round(n * 100) : Math.round(n);
}

function safeText(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

function findField(obj, keys) {
  if (!obj || typeof obj !== "object") return null;
  for (const key of keys) {
    if (obj[key] !== undefined && obj[key] !== null) return obj[key];
  }
  return null;
}

function normalizeResult(result) {
  const doc = result?.document_result || {};
  const match = result?.matching_result || {};
  const discrepancy = result?.discrepancy_result || {};
  const resolution = result?.resolution_recommendation || {};

  const extractionConfidence = confidence(
    findField(doc, ["confidence", "extraction_confidence"])
  );
  const matchingConfidence = confidence(
    findField(match, ["confidence", "match_confidence", "matching_confidence"])
  );

  let discrepancyCount = findField(discrepancy, [
    "discrepancy_count",
    "count",
    "total_discrepancies",
  ]);

  if (discrepancyCount === null && Array.isArray(discrepancy?.discrepancies)) {
    discrepancyCount = discrepancy.discrepancies.length;
  }

  const matchedPo = findField(match, [
    "matched_po",
    "matched_po_number",
    "po_number",
  ]);

  const action = prettyAction(resolution);

  return {
    extractionConfidence,
    matchingConfidence,
    discrepancyCount: discrepancyCount ?? 0,
    action,
    matchedPo: safeText(matchedPo),
    trace: Array.isArray(result?.execution_trace) ? result.execution_trace : [],
    errors: Array.isArray(result?.errors) ? result.errors : [],
    raw: result,
  };
}

export default function App() {
  const [invoices, setInvoices] = useState([]);
  const [selectedInvoice, setSelectedInvoice] = useState("");
  const [dataStatus, setDataStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [showRaw, setShowRaw] = useState(false);

  async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, options);
    const text = await response.text();
    let body = {};
    try { body = text ? JSON.parse(text) : {}; } catch { body = { detail: text }; }
    if (!response.ok) {
      throw new Error(body?.detail || `Request failed (${response.status})`);
    }
    return body;
  }

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [status, invoiceData] = await Promise.all([
        api("/data-status"),
        api("/invoices"),
      ]);

      setDataStatus(status);
      setInvoices(invoiceData.invoices || []);
      setSelectedInvoice((current) => current || invoiceData.invoices?.[0]?.filename || "");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function runReconciliation() {
    if (!selectedInvoice) return;

    setRunning(true);
    setError("");
    setResult(null);

    try {
      const encoded = encodeURIComponent(selectedInvoice);
      const response = await api(`/reconcile?invoice_filename=${encoded}`, {
        method: "POST",
      });
      setResult(normalizeResult(response));
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  const selectedLabel = selectedInvoice || "No invoice selected";
  const statusClass = dataStatus && dataStatus.purchase_order_count > 0 ? "online" : "warning";

  const stageState = useMemo(() => {
    const trace = result?.trace || [];
    const names = [
      ["extract_document", "Document Intelligence"],
      ["match_invoice", "PO Matching"],
      ["detect_discrepancies", "Discrepancy Detection"],
      ["resolve", "Resolution"],
    ];

    return names.map(([key, label]) => ({
      key,
      label,
      done: trace.includes(key),
      active: running && trace.length === 0 && key === "extract_document",
    }));
  }, [result, running]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Icon name="spark" size={21} /></div>
          <div>
            <div className="brand-name">Reconcile<span>AI</span></div>
            <div className="brand-subtitle">Invoice intelligence</div>
          </div>
        </div>

        <nav className="nav">
          <button className="nav-item active">
            <Icon name="database" size={18} />
            Reconciliation
          </button>
        </nav>

        <div className="sidebar-bottom">
          <div className={`connection ${statusClass}`}>
            <span className="status-dot" />
            <div>
              <strong>{statusClass === "online" ? "Backend connected" : "Check data"}</strong>
              <span>FastAPI · localhost:8000</span>
            </div>
          </div>
          <div className="sidebar-version">v1.0 · LangGraph</div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">AI FINANCE OPERATIONS</div>
            <h1>Invoice Reconciliation</h1>
            <p>Run your existing invoice through the multi-agent reconciliation workflow.</p>
          </div>
          <button className="icon-button" onClick={loadData} title="Refresh data">
            <Icon name="refresh" size={18} />
          </button>
        </header>

        {error && (
          <div className="error-banner">
            <Icon name="alert" size={19} />
            <div>
              <strong>Something needs attention</strong>
              <span>{error}</span>
            </div>
          </div>
        )}

        <section className="control-card">
          <div className="section-heading">
            <div>
              <div className="eyebrow">RUN RECONCILIATION</div>
              <h2>Choose an existing invoice</h2>
            </div>
            <div className="data-pills">
              <span><Icon name="file" size={15} /> {dataStatus?.invoice_count ?? "—"} invoices</span>
              <span><Icon name="database" size={15} /> {dataStatus?.purchase_order_count ?? "—"} POs</span>
            </div>
          </div>

          <div className="run-row">
            <div className="select-wrap">
              <Icon name="file" size={18} />
              <select
                value={selectedInvoice}
                onChange={(e) => {
                  setSelectedInvoice(e.target.value);
                  setResult(null);
                }}
                disabled={loading || running || invoices.length === 0}
              >
                {invoices.length === 0 ? (
                  <option value="">No invoices found</option>
                ) : (
                  invoices.map((invoice) => (
                    <option key={invoice.filename} value={invoice.filename}>
                      {invoice.filename}
                    </option>
                  ))
                )}
              </select>
              <Icon name="chevron" size={17} />
            </div>

            <button
              className="run-button"
              onClick={runReconciliation}
              disabled={!selectedInvoice || running || loading}
            >
              {running ? (
                <>
                  <span className="spinner" />
                  Running agents…
                </>
              ) : (
                <>
                  <Icon name="play" size={18} />
                  Run reconciliation
                </>
              )}
            </button>
          </div>

          <div className="selected-file">
            <span className="file-dot" />
            <span>Selected:</span>
            <strong>{selectedLabel}</strong>
            <span className="muted">Existing project data · no re-upload required</span>
          </div>
        </section>

        <section className="pipeline-card">
          <div className="section-heading compact">
            <div>
              <div className="eyebrow">AGENT PIPELINE</div>
              <h2>Reconciliation workflow</h2>
            </div>
            {running && <span className="processing-label"><span className="pulse" /> Processing</span>}
          </div>

          <div className="pipeline">
            {stageState.map((stage, index) => (
              <div className="pipeline-item" key={stage.key}>
                <div className={`stage-icon ${stage.done ? "done" : stage.active ? "active" : ""}`}>
                  {stage.done ? <Icon name="check" size={17} /> : <span>{index + 1}</span>}
                </div>
                <div className="stage-copy">
                  <strong>{stage.label}</strong>
                  <span>
                    {stage.done ? "Completed" : stage.active ? "Running" : "Waiting"}
                  </span>
                </div>
                {index < stageState.length - 1 && <div className={`pipeline-line ${stage.done ? "done" : ""}`} />}
              </div>
            ))}
          </div>
        </section>

        <section className="metrics-grid">
          <Metric
            label="Extraction confidence"
            value={result?.extractionConfidence != null ? `${result.extractionConfidence}%` : "—"}
            helper="Document intelligence"
          />
          <Metric
            label="PO match confidence"
            value={result?.matchingConfidence != null ? `${result.matchingConfidence}%` : "—"}
            helper={result?.matchedPo ? `Matched ${result.matchedPo}` : "Purchase-order matching"}
          />
          <Metric
            label="Discrepancies"
            value={result ? result.discrepancyCount : "—"}
            helper="Detected in reconciliation"
          />
          <Metric
            label="Final decision"
            value={result?.action || "—"}
            helper={result ? "Resolution recommendation" : "Awaiting analysis"}
            action
          />
        </section>

        <section className="lower-grid">
          <div className="panel">
            <div className="panel-header">
              <div>
                <div className="eyebrow">EXECUTION TRACE</div>
                <h2>Agent activity</h2>
              </div>
              {result?.trace?.length > 0 && (
                <span className="trace-count">{result.trace.length} steps</span>
              )}
            </div>

            <div className="trace-list">
              {result?.trace?.length ? (
                result.trace.map((step, index) => (
                  <div className="trace-row" key={`${step}-${index}`}>
                    <div className="trace-check"><Icon name="check" size={14} /></div>
                    <div>
                      <strong>{step.replaceAll("_", " ")}</strong>
                      <span>Completed successfully</span>
                    </div>
                    <span className="trace-index">0{index + 1}</span>
                  </div>
                ))
              ) : (
                <EmptyState running={running} />
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <div>
                <div className="eyebrow">DECISION</div>
                <h2>Reconciliation result</h2>
              </div>
            </div>

            <div className={`decision-box ${result?.action?.toLowerCase() || ""}`}>
              <div className="decision-icon">
                {result ? (
                  result.action === "APPROVE" ? <Icon name="check" size={25} /> :
                  result.action === "REVIEW" ? <Icon name="clock" size={25} /> :
                  <Icon name="alert" size={25} />
                ) : <Icon name="spark" size={25} />}
              </div>
              <div>
                <span>Recommended action</span>
                <strong>{result?.action || "Awaiting run"}</strong>
              </div>
            </div>

            {result?.errors?.length > 0 && (
              <div className="result-errors">
                <Icon name="alert" size={17} />
                <div>
                  <strong>Graph reported an issue</strong>
                  {result.errors.map((item, i) => <span key={i}>{item}</span>)}
                </div>
              </div>
            )}

            {result && (
              <button className="raw-toggle" onClick={() => setShowRaw(!showRaw)}>
                {showRaw ? "Hide raw response" : "View raw API response"}
                <Icon name="arrow" size={15} />
              </button>
            )}

            {showRaw && (
              <pre className="raw-json">{JSON.stringify(result.raw, null, 2)}</pre>
            )}
          </div>
        </section>

        <footer>
          <span>ReconcileAI</span>
          <span>FastAPI + LangGraph + React</span>
        </footer>
      </main>
    </div>
  );
}

function Metric({ label, value, helper, action }) {
  const tone = action && value !== "—" ? value.toLowerCase() : "";
  return (
    <div className="metric-card">
      <span className="metric-label">{label}</span>
      <strong className={`metric-value ${tone}`}>{value}</strong>
      <span className="metric-helper">{helper}</span>
    </div>
  );
}

function EmptyState({ running }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon name={running ? "spark" : "clock"} size={20} /></div>
      <strong>{running ? "Agents are processing…" : "No run yet"}</strong>
      <span>{running ? "Your invoice is moving through the LangGraph workflow." : "Choose an invoice above and start reconciliation."}</span>
    </div>
  );
}
