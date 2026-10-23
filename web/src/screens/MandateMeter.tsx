import React from "react";
import { Lock, RefreshCw } from "lucide-react";
import type { MandateResponse } from "../api";

export interface MandateMeterProps {
  mandate: MandateResponse | null;
  isLoadingMandate: boolean;
}

export const MandateMeter: React.FC<MandateMeterProps> = ({ mandate, isLoadingMandate }) => {
  return (
    <section
      id="panel-mandate"
      role="tabpanel"
      aria-labelledby="tab-mandate"
      className="card mandate-card"
    >
      <div className="card-header">
        <div className="card-title-row">
          <Lock className="card-icon" aria-hidden="true" />
          <h2 className="card-title">Active Ed25519 Authority Mandate</h2>
        </div>
        <span className="status-pill active">ACTIVE</span>
      </div>
      <p className="card-subtitle">
        Cryptographically signed authority parameters issued by Authorized Treasury Principal.
        Defines operational envelope and budget constraints for autonomous agents.
      </p>

      {isLoadingMandate && !mandate ? (
        <div className="loading-state" aria-busy="true">
          <RefreshCw className="spin-icon" size={20} aria-hidden="true" />
          <span>Fetching active Ed25519 mandate parameters...</span>
        </div>
      ) : mandate ? (
        <>
          <div className="mandate-specs">
            <div className="spec-item">
              <span className="spec-label">Mandate ID</span>
              <span className="spec-value mono">
                {mandate.mandate_id} (v{mandate.version})
              </span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Principal Identity</span>
              <span className="spec-value mono">{mandate.principal_id}</span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Authorized Agent</span>
              <span className="spec-value mono">{mandate.agent_id}</span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Single Transaction Cap</span>
              <span className="spec-value tabular-nums">
                ${(mandate.single_limit_minor / 100).toFixed(2)} {mandate.currency}
              </span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Instant Autonomous Threshold</span>
              <span className="spec-value tabular-nums">
                ${(mandate.instant_threshold_minor / 100).toFixed(2)} {mandate.currency}
              </span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Lifetime Budget Cap</span>
              <span className="spec-value tabular-nums">
                ${(mandate.lifetime_budget_minor / 100).toFixed(2)} {mandate.currency}
              </span>
            </div>
            <div className="spec-item highlight">
              <span className="spec-label">Remaining Budget</span>
              <span className="spec-value tabular-nums highlight">
                ${(mandate.remaining_budget_minor / 100).toFixed(2)} {mandate.currency}
              </span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Validity Window</span>
              <span className="spec-value tabular-nums">
                {mandate.valid_from_utc.slice(0, 10)} to {mandate.valid_until_utc.slice(0, 10)} (UTC)
              </span>
            </div>
          </div>

          <div className="spec-lists">
            <div>
              <span className="spec-label">Allowlisted Payees:</span>
              <ul className="spec-bullets mono">
                {mandate.allowed_payees.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </div>
            <div>
              <span className="spec-label">Allowlisted Purposes:</span>
              <ul className="spec-bullets">
                {mandate.allowed_purposes.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="signature-box">
            <span className="spec-label">
              Ed25519 Cryptographic Integrity Seal (Key ID: {mandate.key_id}):
            </span>
            <div className="sig-code mono">{mandate.signature}</div>
            <span className="seal-disclaimer">
              Note: Signature is an integrity seal, not human non-repudiation (AGENTS.md).
            </span>
          </div>
        </>
      ) : (
        <div className="empty-state">No mandate found.</div>
      )}
    </section>
  );
};
