import React from "react";
import { RefreshCw } from "lucide-react";

export interface ReconciliationScreenProps {
  reconcileItems: Array<{
    request_id: string;
    agent_id: string;
    amount_minor: number;
    currency: string;
    payout_id?: string | null;
    state: string;
  }>;
  setReconcileItems: React.Dispatch<
    React.SetStateAction<
      Array<{
        request_id: string;
        agent_id: string;
        amount_minor: number;
        currency: string;
        payout_id?: string | null;
        state: string;
      }>
    >
  >;
  reconcileFeedback: string | null;
  setReconcileFeedback: (msg: string | null) => void;
  handleResolveReconcile: (
    requestId: string,
    status: "SUCCESS" | "FAILED" | "UNKNOWN"
  ) => Promise<void>;
}

export const ReconciliationScreen: React.FC<ReconciliationScreenProps> = ({
  reconcileItems,
  setReconcileItems,
  reconcileFeedback,
  setReconcileFeedback,
  handleResolveReconcile,
}) => {
  return (
    <section
      id="panel-reconcile"
      role="tabpanel"
      aria-labelledby="tab-reconcile"
      className="reconcile-panel"
    >
      <div className="card">
        <div className="card-header">
          <div className="card-title-row">
            <RefreshCw className="card-icon" />
            <h2 className="card-title">Ambiguous Rail Reconciliation (F6 Lifecycle)</h2>
          </div>
          <span className="phalanx-system-badge">BUDGET SAFETY INVARIANT</span>
        </div>
        <p className="card-subtitle">
          When external payment networks (PayPal) return ambiguous outcomes—such as HTTP 504 gateway
          timeouts, connection drops, or transient 5xx errors—PHALANX unconditionally transitions
          the transaction to <code>RECONCILE</code> state. The allocated budget reservation remains
          held and is NEVER released until outcome confirmation.
        </p>

        {/* State Machine Visualization */}
        <div className="reconcile-state-strip">
          <div className="reconcile-state-step">
            <span>1. EXECUTING</span>
            <span>→</span>
          </div>
          <div className="reconcile-state-step current">
            <span>2. RECONCILE (Budget Held)</span>
            <span>→</span>
          </div>
          <div className="reconcile-state-step confirmed">
            <span>3a. Confirmed Success (Settled)</span>
          </div>
          <span style={{ color: "var(--text-muted)" }}>|</span>
          <div className="reconcile-state-step released">
            <span>3b. Confirmed Failure (Released)</span>
          </div>
        </div>

        {reconcileFeedback && (
          <div className="status-badge" style={{ margin: "1rem 0", display: "inline-flex" }}>
            <span className="pulse-dot"></span>
            <span>{reconcileFeedback}</span>
          </div>
        )}

        {/* Held Reservations Table */}
        <h3 style={{ marginTop: "1.5rem", marginBottom: "0.75rem", fontSize: "1rem" }}>
          Held Ambiguous Reservations ({reconcileItems.length})
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table className="reconcile-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Agent ID</th>
                <th>Held Amount</th>
                <th>Payout ID</th>
                <th>State</th>
                <th>Resolution Actions</th>
              </tr>
            </thead>
            <tbody>
              {reconcileItems.map((item) => (
                <tr key={item.request_id}>
                  <td className="mono">{item.request_id}</td>
                  <td className="mono">{item.agent_id}</td>
                  <td className="tabular-nums" style={{ fontWeight: 600 }}>
                    ${(item.amount_minor / 100).toFixed(2)} {item.currency}
                  </td>
                  <td className="mono">{item.payout_id || "PENDING_LOOKUP"}</td>
                  <td>
                    <span
                      className={`decision-badge ${
                        item.state === "SETTLED"
                          ? "allow"
                          : item.state === "FAILED"
                            ? "deny"
                            : "step_up"
                      }`}
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                    >
                      {item.state}
                    </span>
                  </td>
                  <td>
                    <div className="reconcile-action-group">
                      <button
                        type="button"
                        className="preset-btn"
                        style={{
                          borderColor: "var(--accent-emerald)",
                          color: "var(--accent-emerald)",
                        }}
                        disabled={item.state !== "RECONCILE"}
                        onClick={() => handleResolveReconcile(item.request_id, "SUCCESS")}
                      >
                        Confirm Success
                      </button>
                      <button
                        type="button"
                        className="preset-btn warning"
                        disabled={item.state !== "RECONCILE"}
                        onClick={() => handleResolveReconcile(item.request_id, "FAILED")}
                      >
                        Confirm Failure
                      </button>
                      <button
                        type="button"
                        className="preset-btn"
                        disabled={item.state !== "RECONCILE"}
                        onClick={() => handleResolveReconcile(item.request_id, "UNKNOWN")}
                      >
                        Still Unknown (Keep Held)
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Simulator Action */}
        <div
          style={{
            marginTop: "1.5rem",
            display: "flex",
            gap: "0.75rem",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <button
            type="button"
            className="preset-btn warning"
            onClick={() => {
              const newId = `req_ambiguous_${Date.now().toString().slice(-4)}`;
              setReconcileItems((prev) => [
                ...prev,
                {
                  request_id: newId,
                  agent_id: "agent-auto-1",
                  amount_minor: 12500,
                  currency: "USD",
                  payout_id: `PAYOUT_TIMEOUT_${newId}`,
                  state: "RECONCILE",
                },
              ]);
              setReconcileFeedback(`Simulated PayPal 504 Timeout on ${newId}. Budget reserved.`);
            }}
          >
            + Simulate PayPal 504 Gateway Timeout Event
          </button>
          <span className="subtext">
            Demonstrates F6 invariant: funds stay locked and cannot be double spent during network uncertainty.
          </span>
        </div>
      </div>
    </section>
  );
};
