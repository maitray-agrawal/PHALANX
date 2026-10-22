import React from "react";
import { ShieldCheck, RefreshCw, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { PendingStepUpItem } from "../api";
import type { Role } from "../App";

export interface ApprovalQueueProps {
  role: Role;
  stepUps: PendingStepUpItem[];
  isLoadingApprovals: boolean;
  loadApprovals: () => Promise<void>;
  tamperedItemMap: Record<string, boolean>;
  toggleTamper: (reqId: string) => void;
  approvingRequestId: string | null;
  handleApprovalDecision: (
    reqId: string,
    digest: string,
    decision: "ALLOW" | "DENY",
    reason: string
  ) => Promise<void>;
}

export const ApprovalQueue: React.FC<ApprovalQueueProps> = ({
  role,
  stepUps,
  isLoadingApprovals,
  loadApprovals,
  tamperedItemMap,
  toggleTamper,
  approvingRequestId,
  handleApprovalDecision,
}) => {
  return (
    <section
      id="panel-approvals"
      role="tabpanel"
      aria-labelledby="tab-approvals"
      className="card approvals-card"
    >
      <div className="card-header">
        <div className="card-title-row">
          <ShieldCheck className="card-icon" aria-hidden="true" />
          <h2 className="card-title">Human Step-Up Supervisor Queue</h2>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="refresh-btn"
            onClick={loadApprovals}
            disabled={isLoadingApprovals}
            aria-label="Refresh Approvals Queue"
          >
            <RefreshCw
              size={14}
              className={isLoadingApprovals ? "spin-icon" : ""}
              aria-hidden="true"
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>
      <p className="card-subtitle">
        Transactions exceeding instant thresholds require human authorization bound to the RFC 8785
        canonical intent digest. Any tamper with the parameters breaks approval integrity.
      </p>

      {/* Role Notice Banner */}
      {role === "agent" && (
        <div className="warning-banner" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          <span>Role: AGENT — Approval actions disabled (Manual 18: Agents cannot approve).</span>
        </div>
      )}

      {/* Pending Step-Up Requests List */}
      <div className="stepup-list" role="feed" aria-label="Pending Approvals">
        {stepUps.length === 0 ? (
          <div className="empty-state">
            <CheckCircle2 size={32} className="success-icon" aria-hidden="true" />
            <span>No pending step-up requests in queue.</span>
          </div>
        ) : (
          stepUps.map((item) => {
            const isTampered = !!tamperedItemMap[item.request_id];
            const effectiveDigest = isTampered
              ? "0000000000000000000000000000000000000000000000000000000000000000"
              : item.intent_digest;

            return (
              <article key={item.request_id} className="stepup-item">
                <div className="stepup-header">
                  <span className="stepup-id">{item.request_id}</span>
                  <span className="status-pill step_up">PENDING REVIEW</span>
                </div>

                <div className="stepup-body">
                  <div className="detail-row">
                    <span className="detail-key">Agent:</span>
                    <span className="detail-val mono">{item.agent_id}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">Payee:</span>
                    <span className="detail-val mono">{item.recipient_id}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">Amount:</span>
                    <span className="detail-val mono tabular-nums highlight">
                      ${(item.amount_minor / 100).toFixed(2)} {item.currency}
                    </span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">Purpose:</span>
                    <span className="detail-val">{item.purpose}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-key">RFC 8785 Digest Seal:</span>
                    <span className="detail-val mono">
                      {effectiveDigest.slice(0, 16)}...
                      {isTampered && <span className="tamper-tag"> [MUTATED]</span>}
                    </span>
                  </div>
                </div>

                {/* Supervisor Action Toolbar */}
                <div className="stepup-actions">
                  <button
                    type="button"
                    className="approve-action-btn"
                    disabled={role === "agent" || approvingRequestId === item.request_id}
                    onClick={() =>
                      handleApprovalDecision(
                        item.request_id,
                        effectiveDigest,
                        "ALLOW",
                        "Supervisor approved via web console"
                      )
                    }
                  >
                    <CheckCircle2 size={16} aria-hidden="true" />
                    <span>Authorize Transaction</span>
                  </button>

                  <button
                    type="button"
                    className="deny-action-btn"
                    disabled={role === "agent" || approvingRequestId === item.request_id}
                    onClick={() =>
                      handleApprovalDecision(
                        item.request_id,
                        effectiveDigest,
                        "DENY",
                        "Supervisor rejected exception"
                      )
                    }
                  >
                    <XCircle size={16} aria-hidden="true" />
                    <span>Deny Exception</span>
                  </button>

                  <button
                    type="button"
                    className={`tamper-toggle-btn ${isTampered ? "active" : ""}`}
                    onClick={() => toggleTamper(item.request_id)}
                    title="Simulate modifying intent details after submission"
                  >
                    {isTampered ? "Reset True Digest" : "Simulate Digest Tamper"}
                  </button>
                </div>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
};
