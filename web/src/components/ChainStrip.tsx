import React from "react";
import { Link2, ShieldCheck, ShieldAlert, ArrowRight, RefreshCw } from "lucide-react";
import type { LedgerEventItem, LedgerVerificationResponse } from "../api";
import { PillButton } from "./PillButton";

export interface ChainStripProps {
  events: LedgerEventItem[];
  verification: LedgerVerificationResponse | null;
  isVerifying?: boolean;
  onVerify?: () => void;
  onTamperSimulate?: () => void;
  onRestore?: () => void;
  className?: string;
}

export const ChainStrip: React.FC<ChainStripProps> = ({
  events,
  verification,
  isVerifying = false,
  onVerify,
  onTamperSimulate,
  onRestore,
  className = "",
}) => {
  const isChainValid = verification ? verification.is_valid : true;
  const brokenIndex = verification ? verification.broken_index : null;
  const maxDisplay = 20;
  const offset = events.length > maxDisplay ? events.length - maxDisplay : 0;
  const displayEvents = events.slice(offset);

  return (
    <div className={`chain-strip-card card ${className}`.trim()} data-testid="chain-strip">
      <div className="chain-strip-header">
        <div className="chain-header-title-box">
          <Link2 size={18} className="text-accent" aria-hidden="true" />
          <h3 className="card-title">Cryptographic Hash Chain Sequence</h3>
          {offset > 0 && (
            <span className="chain-window-tag mono text-muted">
              (Showing latest {displayEvents.length} of {events.length} blocks)
            </span>
          )}
        </div>
        <div className="chain-strip-actions">
          {onVerify && (
            <PillButton
              variant="secondary"
              size="sm"
              loading={isVerifying}
              icon={<RefreshCw size={14} aria-hidden="true" />}
              onClick={onVerify}
            >
              Verify Chain
            </PillButton>
          )}
          {onTamperSimulate && (
            <PillButton
              variant="danger"
              size="sm"
              onClick={onTamperSimulate}
            >
              Simulate Tamper
            </PillButton>
          )}
          {onRestore && !isChainValid && (
            <PillButton
              variant="primary"
              size="sm"
              onClick={onRestore}
            >
              Restore True Ledger
            </PillButton>
          )}
        </div>
      </div>

      {/* Verification status indicator banner */}
      <div
        className={`integrity-status-bar ${isChainValid ? "green" : "red"}`}
        role="status"
        aria-live="polite"
      >
        {isChainValid ? (
          <div className="status-content">
            <ShieldCheck size={18} aria-hidden="true" />
            <span>
              <strong>Cryptographic Integrity Verified:</strong>{" "}
              {verification ? verification.message : `${events.length}/${events.length} block links intact.`}
            </span>
          </div>
        ) : (
          <div className="status-content">
            <ShieldAlert size={18} aria-hidden="true" />
            <span>
              <strong>Tamper detected:</strong> Hash chain broken at Block #{brokenIndex}. Ledger integrity compromised.
            </span>
          </div>
        )}
      </div>

      {/* Visual Chain of Blocks */}
      <div className="chain-blocks-scroll">
        <div className="chain-blocks">
          {displayEvents.map((ev, i) => {
            const index = offset + i;
            const blockNum = index + 1;
            const isBroken = brokenIndex !== null && blockNum >= brokenIndex;
            return (
              <React.Fragment key={ev.event_id}>
                <div
                  className={`block-node ${isBroken ? "broken-block" : "verified-block"}`}
                  data-block-number={blockNum}
                >
                  <div className="block-header">
                    <span className="block-num">Block #{blockNum}</span>
                    <span className="block-tag mono">{ev.event_type.slice(0, 10)}</span>
                  </div>
                  <div className="block-hashes">
                    <div className="hash-row">
                      <span className="hash-lbl">PREV:</span>
                      <span className="hash-code mono" title={ev.prev_hash}>
                        {ev.prev_hash.slice(0, 8)}...
                      </span>
                    </div>
                    <div className="hash-row">
                      <span className="hash-lbl">HASH:</span>
                      <span className="hash-code mono font-bold" title={ev.event_hash}>
                        {ev.event_hash.slice(0, 8)}...
                      </span>
                    </div>
                  </div>
                  <div className="block-meta">
                    <span className="block-amount tabular-nums">
                      {ev.payload?.amount_minor !== undefined
                        ? `$${(ev.payload.amount_minor / 100).toFixed(2)}`
                        : "GENESIS"}
                    </span>
                    <span className="block-decision">{ev.payload?.decision || "LOG"}</span>
                  </div>
                </div>

                {i < displayEvents.length - 1 && (
                  <div className={`chain-link-connector ${isBroken ? "link-severed" : "link-intact"}`}>
                    <ArrowRight size={14} aria-hidden="true" />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};
