import React from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import { FileText, RefreshCw, Eye, CheckCircle2, AlertTriangle } from "lucide-react";
import type { LedgerEventItem } from "../api";

export interface AuditLedgerProps {
  ledgerEvents: LedgerEventItem[];
  isLoadingLedger: boolean;
  isVerifyingChain: boolean;
  chainIntegrity: {
    isValid: boolean;
    message: string;
    brokenIndex: number | null;
  };
  loadLedger: () => Promise<void>;
  handleVerifyChain: () => Promise<void>;
  handleTamperLedger: () => Promise<void>;
  handleRestoreLedger: () => Promise<void>;
  ledgerColDefs: ColDef<LedgerEventItem>[];
}

export const AuditLedger: React.FC<AuditLedgerProps> = ({
  ledgerEvents,
  isLoadingLedger,
  isVerifyingChain,
  chainIntegrity,
  loadLedger,
  handleVerifyChain,
  handleTamperLedger,
  handleRestoreLedger,
  ledgerColDefs,
}) => {
  return (
    <section
      id="panel-ledger"
      role="tabpanel"
      aria-labelledby="tab-ledger"
      className="card ledger-card"
    >
      <div className="card-header">
        <div className="card-title-row">
          <FileText className="card-icon" aria-hidden="true" />
          <h2 className="card-title">Cryptographic Shield-Wall Ledger</h2>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="refresh-btn"
            onClick={loadLedger}
            disabled={isLoadingLedger}
            aria-label="Refresh Ledger Entries"
          >
            <RefreshCw
              size={14}
              className={isLoadingLedger ? "spin-icon" : ""}
              aria-hidden="true"
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>
      <p className="card-subtitle">
        Append-only cryptographic hash chain (<code>prev_hash</code> → <code>event_hash</code>).
        PostgreSQL database role is restricted to INSERT and SELECT only.
      </p>

      {/* Verification & Tamper Simulation Toolbar */}
      <div className="ledger-toolbar">
        <div
          className={`chain-status-badge ${chainIntegrity.isValid ? "valid" : "broken"}`}
          role="status"
          aria-live="polite"
        >
          {chainIntegrity.isValid ? (
            <CheckCircle2 size={16} aria-hidden="true" />
          ) : (
            <AlertTriangle size={16} aria-hidden="true" />
          )}
          <span>{chainIntegrity.message}</span>
        </div>

        <div className="toolbar-buttons">
          <button
            type="button"
            className="verify-btn"
            onClick={handleVerifyChain}
            disabled={isVerifyingChain}
          >
            <Eye size={16} aria-hidden="true" />
            <span>
              {isVerifyingChain
                ? "Verifying..."
                : chainIntegrity.isValid
                  ? "Verify Chain (Intact)"
                  : "Chain Broken!"}
            </span>
          </button>
          <button
            type="button"
            className="tamper-btn"
            onClick={chainIntegrity.isValid ? handleTamperLedger : handleRestoreLedger}
          >
            {chainIntegrity.isValid ? "Simulate Database Tamper" : "Restore True Ledger"}
          </button>
        </div>
      </div>

      {/* Chain-of-blocks Visual sequence turning RED at the first broken link */}
      {isLoadingLedger && ledgerEvents.length === 0 ? (
        <div className="loading-state" aria-busy="true">
          <RefreshCw className="spin-icon" size={20} aria-hidden="true" />
          <span>Loading cryptographic audit ledger events...</span>
        </div>
      ) : (
        <div className="chain-visual-container" aria-label="Cryptographic Block Sequence">
          <span className="chain-title">Chain-of-Blocks Linkage Sequence:</span>
          <div className="chain-blocks">
            {ledgerEvents.map((evt, idx) => {
              const isBrokenBlock =
                !chainIntegrity.isValid &&
                chainIntegrity.brokenIndex !== null &&
                idx >= chainIntegrity.brokenIndex;
              const minor = evt.payload?.amount_minor;
              const amtStr = typeof minor === "number" ? `$${(minor / 100).toFixed(2)}` : "$0.00";

              return (
                <React.Fragment key={evt.event_id}>
                  <div className={`chain-block ${isBrokenBlock ? "tampered" : ""}`}>
                    <div className="block-num">Block #{idx + 1}</div>
                    <div className="block-id mono tabular-nums">{evt.event_id}</div>
                    <div className="block-hash mono">Hash: {evt.event_hash.slice(0, 10)}...</div>
                    <div className="block-amount tabular-nums">{amtStr}</div>
                  </div>
                  {idx < ledgerEvents.length - 1 && (
                    <div className={`chain-link ${isBrokenBlock ? "broken" : ""}`}>
                      ➔
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      )}

      {/* Enterprise Audit Log (AG Grid Component) */}
      <div className="grid-container" style={{ height: 380, width: "100%" }}>
        <AgGridReact<LedgerEventItem>
          rowData={ledgerEvents}
          columnDefs={ledgerColDefs}
          theme="legacy"
          className="ag-theme-alpine-dark"
          pagination={true}
          paginationPageSize={10}
          paginationPageSizeSelector={[10, 20, 50]}
          domLayout="autoHeight"
        />
      </div>
    </section>
  );
};
