import React from "react";
import { ArrowUpRight, ExternalLink, Clock } from "lucide-react";
import { DecisionBadge } from "./DecisionBadge";

export interface ActivityRowProps {
  receiptId: string;
  decision: "ALLOW" | "STEP_UP" | "DENY";
  amountMinor: number;
  currency?: string;
  payee: string;
  reasonCode: string;
  providerState: string;
  timestampUtc: string;
  onViewReceipt?: (receiptId: string) => void;
  className?: string;
}

export const ActivityRow: React.FC<ActivityRowProps> = ({
  receiptId,
  decision,
  amountMinor,
  currency = "USD",
  payee,
  reasonCode,
  providerState,
  timestampUtc,
  onViewReceipt,
  className = "",
}) => {
  const formattedAmount = (amountMinor / 100).toLocaleString("en-US", {
    style: "currency",
    currency: currency,
  });

  // Honest display mapping of real PayPal provider states
  let providerDisplay = providerState;
  let providerClass = "provider-default";

  if (providerState === "COMPLETED" || providerState === "SUCCESS") {
    providerDisplay = "Completed";
    providerClass = "provider-completed";
  } else if (
    providerState === "BUYER_APPROVAL_REQUIRED" ||
    providerState === "ORDER_CREATED"
  ) {
    providerDisplay = "Needs buyer approval";
    providerClass = "provider-pending";
  } else if (providerState === "RECONCILE") {
    providerDisplay = "Order created";
    providerClass = "provider-reconcile";
  } else if (providerState === "FAILED") {
    providerDisplay = "Payment failed";
    providerClass = "provider-failed";
  }

  return (
    <div className={`activity-row ${className}`.trim()} data-testid="activity-row">
      <div className="activity-cell-main">
        <div className="activity-icon-box" aria-hidden="true">
          <ArrowUpRight size={16} />
        </div>
        <div className="activity-info">
          <div className="activity-payee-title">{payee}</div>
          <div className="activity-submeta">
            <span className="reason-code-badge mono">{reasonCode}</span>
            <span className="activity-time tabular-nums">
              <Clock size={11} className="inline-icon" /> {timestampUtc}
            </span>
          </div>
        </div>
      </div>

      <div className="activity-cell-decision">
        <DecisionBadge decision={decision} size="sm" />
      </div>

      <div className="activity-cell-state">
        <span className={`provider-state-tag ${providerClass}`}>
          {providerDisplay}
        </span>
      </div>

      <div className="activity-cell-amount">
        <span className="activity-amount-text tabular-nums">{formattedAmount}</span>
        {onViewReceipt && (
          <button
            type="button"
            className="receipt-link-btn"
            onClick={() => onViewReceipt(receiptId)}
            title={`View cryptographic receipt ${receiptId}`}
          >
            <span className="receipt-id-label mono">{receiptId.slice(0, 14)}...</span>
            <ExternalLink size={12} className="inline-icon" />
          </button>
        )}
      </div>
    </div>
  );
};
