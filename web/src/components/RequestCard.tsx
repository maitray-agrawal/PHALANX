import React from "react";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { DecisionBadge } from "./DecisionBadge";

export interface RequestCardProps {
  agentId: string;
  recipientId: string;
  amountMinor: number;
  currency: string;
  purpose: string;
  idempotencyKey: string;
  decision?: "ALLOW" | "STEP_UP" | "DENY";
  payoutId?: string | null;
  timestamp?: string;
  className?: string;
}

export const RequestCard: React.FC<RequestCardProps> = ({
  agentId,
  recipientId,
  amountMinor,
  currency,
  purpose,
  idempotencyKey,
  decision,
  payoutId,
  timestamp,
  className = "",
}) => {
  const formattedAmount = (amountMinor / 100).toLocaleString("en-US", {
    style: "currency",
    currency: currency || "USD",
  });

  return (
    <article className={`request-card card ${className}`.trim()} data-testid="request-card">
      <div className="request-card-header">
        <div className="request-payee-info">
          <div className="request-icon-wrap" aria-hidden="true">
            <ArrowUpRight size={18} />
          </div>
          <div>
            <h4 className="request-payee-title">{recipientId}</h4>
            <span className="request-agent-subtitle mono">Agent: {agentId}</span>
          </div>
        </div>
        <div className="request-amount-box">
          <span className="request-amount-value tabular-nums">{formattedAmount}</span>
          {decision && <DecisionBadge decision={decision} size="sm" />}
        </div>
      </div>

      <div className="request-card-body">
        <p className="request-purpose-text">{purpose}</p>

        <div className="request-meta-grid">
          <div className="request-meta-item">
            <span className="meta-label">IDEMPOTENCY KEY</span>
            <span className="meta-val mono" title={idempotencyKey}>
              {idempotencyKey}
            </span>
          </div>
          {payoutId && (
            <div className="request-meta-item">
              <span className="meta-label">PAYPAL SANDBOX PAYOUT</span>
              <span className="meta-val mono payout-id">
                <ShieldCheck size={12} className="inline-icon" /> {payoutId}
              </span>
            </div>
          )}
          {timestamp && (
            <div className="request-meta-item">
              <span className="meta-label">EVALUATED AT</span>
              <span className="meta-val tabular-nums">{timestamp}</span>
            </div>
          )}
        </div>
      </div>
    </article>
  );
};
