import React, { useState } from "react";
import { AlertTriangle, Check, ShieldAlert, X, Eye, FileCode } from "lucide-react";
import { PillButton } from "./PillButton";

export interface ApprovalCardProps {
  requestId: string;
  agentId: string;
  recipientId: string;
  amountMinor: number;
  currency: string;
  purpose: string;
  intentDigest: string;
  createdAtUtc: string;
  isAgentRole?: boolean;
  onApprove: (requestId: string, digest: string) => Promise<void> | void;
  onDecline: (requestId: string, digest: string) => Promise<void> | void;
  isActionLoading?: boolean;
  className?: string;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  requestId,
  agentId,
  recipientId,
  amountMinor,
  currency,
  purpose,
  intentDigest,
  createdAtUtc,
  isAgentRole = false,
  onApprove,
  onDecline,
  isActionLoading = false,
  className = "",
}) => {
  const [showDiff, setShowDiff] = useState(false);
  const [simulatedTamper, setSimulatedTamper] = useState(false);

  const formattedAmount = (amountMinor / 100).toLocaleString("en-US", {
    style: "currency",
    currency: currency || "USD",
  });

  const activeDigest = simulatedTamper ? "0".repeat(64) : intentDigest;

  return (
    <article className={`approval-card card ${className}`.trim()} data-testid="approval-card">
      <div className="approval-card-header">
        <div className="approval-title-box">
          <div className="approval-badge-wrap">
            <AlertTriangle className="text-stepup" size={18} aria-hidden="true" />
            <span className="approval-tag">Step-Up Required</span>
          </div>
          <span className="approval-request-id mono">{requestId}</span>
        </div>
        <div className="approval-amount-tag tabular-nums">{formattedAmount}</div>
      </div>

      <div className="approval-body">
        <div className="approval-details-grid">
          <div>
            <span className="meta-label">RECIPIENT PAYEE</span>
            <span className="meta-val">{recipientId}</span>
          </div>
          <div>
            <span className="meta-label">REQUESTING AGENT</span>
            <span className="meta-val mono">{agentId}</span>
          </div>
          <div>
            <span className="meta-label">REQUESTED AT</span>
            <span className="meta-val mono">{createdAtUtc}</span>
          </div>
          <div className="full-width">
            <span className="meta-label">STATED PURPOSE</span>
            <p className="approval-purpose">{purpose}</p>
          </div>
        </div>

        <div className="approval-digest-box">
          <div className="digest-header">
            <span className="meta-label">
              <FileCode size={12} className="inline-icon" aria-hidden="true" /> BOUND RFC 8785 INTENT DIGEST (SHA-256)
            </span>
            <button
              type="button"
              className="diff-toggle-btn"
              onClick={() => setShowDiff(!showDiff)}
              aria-expanded={showDiff}
            >
              <Eye size={12} className="inline-icon" aria-hidden="true" /> {showDiff ? "Hide Digest Inspection" : "Inspect Diff"}
            </button>
          </div>
          <code className="digest-code mono" title={activeDigest}>
            {activeDigest}
          </code>
        </div>

        {showDiff && (
          <div className="diff-view-box">
            <div className="diff-header-bar">
              <span className="diff-title">Cryptographic Lock Canonical Integrity</span>
              <button
                type="button"
                className="tamper-sim-btn"
                onClick={() => setSimulatedTamper(!simulatedTamper)}
              >
                {simulatedTamper ? "Reset True Digest" : "Test Digest Tamper Diff"}
              </button>
            </div>
            {simulatedTamper ? (
              <div className="diff-tamper-alert">
                <ShieldAlert size={16} />
                <span>
                  Tamper detected: Digest mismatch. Expected <code>{intentDigest.slice(0, 16)}...</code> but received{" "}
                  <code>{activeDigest.slice(0, 16)}...</code>. Policy engine will fail closed.
                </span>
              </div>
            ) : (
              <div className="diff-clean-alert">
                <Check size={16} aria-hidden="true" />
                <span>Byte-for-byte canonical RFC 8785 match. Ready for cryptographic approval.</span>
              </div>
            )}
          </div>
        )}

        {isAgentRole && (
          <div className="warning-banner" role="alert">
            <ShieldAlert size={16} className="warning-icon" aria-hidden="true" />
            <span>
              Autonomous agent persona active: Agents are strictly prohibited from approving their own step-ups. Switch to Approver role.
            </span>
          </div>
        )}

        <div className="approval-actions">
          <PillButton
            variant="secondary"
            size="md"
            icon={<X size={16} aria-hidden="true" />}
            disabled={isAgentRole || isActionLoading}
            onClick={() => onDecline(requestId, activeDigest)}
          >
            Decline
          </PillButton>
          <PillButton
            variant="primary"
            size="md"
            icon={<Check size={16} aria-hidden="true" />}
            disabled={isAgentRole || isActionLoading}
            loading={isActionLoading}
            onClick={() => onApprove(requestId, activeDigest)}
          >
            Authorize Transaction
          </PillButton>
        </div>
      </div>
    </article>
  );
};
