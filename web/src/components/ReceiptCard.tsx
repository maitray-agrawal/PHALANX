import React from "react";
import { ShieldCheck, ShieldAlert, FileText, CheckCircle2 } from "lucide-react";
import type { ReceiptResponse } from "../api";
import { DecisionBadge } from "./DecisionBadge";
import { PillButton } from "./PillButton";

export interface ReceiptCardProps {
  receipt: ReceiptResponse;
  onVerify?: (receiptId: string) => void;
  className?: string;
}

export const ReceiptCard: React.FC<ReceiptCardProps> = ({
  receipt,
  onVerify,
  className = "",
}) => {
  const formattedAmount = (receipt.amount_minor / 100).toLocaleString("en-US", {
    style: "currency",
    currency: receipt.currency || "USD",
  });

  const proof = receipt.hash_chain_proof;

  return (
    <article className={`receipt-card card ${className}`.trim()} data-testid="receipt-card">
      <div className="receipt-header">
        <div className="receipt-title-box">
          <FileText size={20} className="text-accent" aria-hidden="true" />
          <div>
            <h3 className="card-title">Cryptographic Transaction Receipt</h3>
            <span className="receipt-id-sub mono">{receipt.receipt_id}</span>
          </div>
        </div>
        <div className="receipt-amount-box">
          <span className="receipt-amount-text tabular-nums">{formattedAmount}</span>
          <DecisionBadge decision={receipt.decision} size="sm" />
        </div>
      </div>

      <div className="receipt-body">
        {/* Core fields */}
        <div className="receipt-summary-grid">
          <div>
            <span className="meta-label">RECIPIENT PAYEE</span>
            <span className="meta-val">{receipt.payee}</span>
          </div>
          <div>
            <span className="meta-label">LEDGER SEQUENCE</span>
            <span className="meta-val mono">Block #{receipt.ledger_sequence}</span>
          </div>
          <div>
            <span className="meta-label">MANDATE ID & VERSION</span>
            <span className="meta-val mono">
              {receipt.mandate_id} (v{receipt.mandate_version})
            </span>
          </div>
          <div>
            <span className="meta-label">RECORDED AT (UTC)</span>
            <span className="meta-val tabular-nums">{receipt.created_at_utc}</span>
          </div>
        </div>

        {/* Reason Codes */}
        <div className="receipt-reasons-box">
          <span className="meta-label">EVALUATED POLICY REASONS</span>
          <div className="chips-container">
            {receipt.reason_codes.map((code) => (
              <span key={code} className="spec-chip mono">
                <CheckCircle2 size={11} className="inline-icon" aria-hidden="true" /> {code}
              </span>
            ))}
          </div>
        </div>

        {/* Cryptographic Hash Chain Proof Box */}
        <div className="receipt-proof-box">
          <div className="proof-header">
            <span className="meta-label">CRYPTOGRAPHIC HASH CHAIN PROOF</span>
            <span className={`proof-validity-tag ${proof.is_valid ? "valid" : "invalid"}`}>
              {proof.is_valid ? (
                <>
                  <ShieldCheck size={12} className="inline-icon" aria-hidden="true" /> Link Valid
                </>
              ) : (
                <>
                  <ShieldAlert size={12} className="inline-icon" aria-hidden="true" /> Broken Link
                </>
              )}
            </span>
          </div>

          <div className="proof-hashes-grid">
            <div className="hash-item">
              <span className="hash-key">Canonical Payload Digest:</span>
              <code className="hash-val mono" title={proof.canonical_payload_hash}>
                {proof.canonical_payload_hash}
              </code>
            </div>
            <div className="hash-item">
              <span className="hash-key">Previous Block Hash:</span>
              <code className="hash-val mono" title={proof.prev_hash}>
                {proof.prev_hash}
              </code>
            </div>
            <div className="hash-item">
              <span className="hash-key">Current Block Hash:</span>
              <code className="hash-val mono" title={proof.event_hash}>
                {proof.event_hash}
              </code>
            </div>
          </div>
        </div>

        {/* Verify Action */}
        {onVerify && (
          <div className="receipt-action-row">
            <PillButton
              variant="secondary"
              size="md"
              icon={<ShieldCheck size={16} />}
              onClick={() => onVerify(receipt.receipt_id)}
            >
              Verify Receipt on Public Ledger
            </PillButton>
          </div>
        )}
      </div>
    </article>
  );
};
