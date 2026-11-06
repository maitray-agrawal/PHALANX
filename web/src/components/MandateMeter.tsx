import React from "react";
import { Lock, CheckCircle2, ShieldCheck } from "lucide-react";
import type { MandateResponse } from "../api";

export interface MandateMeterProps {
  mandate: MandateResponse | null;
  isLoading?: boolean;
  className?: string;
}

export const MandateMeter: React.FC<MandateMeterProps> = ({
  mandate,
  isLoading: _isLoading = false,
  className = "",
}) => {
  if (!mandate) {
    return (
      <div className={`mandate-meter-card card ${className}`.trim()}>
        <div className="card-header">
          <div className="card-title-row">
            <Lock size={18} className="card-icon" />
            <h3 className="card-title">Active Ed25519 Authority Mandate</h3>
          </div>
          <span className="status-pill active">ACTIVE</span>
        </div>
        <p className="card-subtitle">Loading mandate parameters...</p>
      </div>
    );
  }

  const lifetimeTotal = mandate.lifetime_budget_minor || 2500000;
  const spent = mandate.spent_budget_minor || 0;
  const remaining = Math.max(0, lifetimeTotal - spent);
  const spentPct = Math.min(100, Math.round((spent / lifetimeTotal) * 100));

  const formatMoney = (minor: number) =>
    (minor / 100).toLocaleString("en-US", {
      style: "currency",
      currency: mandate.currency || "USD",
    });

  return (
    <article className={`mandate-meter-card card ${className}`.trim()} data-testid="mandate-meter">
      <div className="card-header">
        <div className="card-title-row">
          <Lock size={20} className="card-icon text-accent" aria-hidden="true" />
          <div>
            <h3 className="card-title">Active Ed25519 Authority Mandate</h3>
            <span className="mandate-id-sub mono">
              {mandate.mandate_id} (v{mandate.version})
            </span>
          </div>
        </div>
        <div className="mandate-status-tags">
          <span className="status-pill active">ACTIVE</span>
          <span className="signature-pill verified">
            <CheckCircle2 size={12} className="inline-icon" aria-hidden="true" /> ED25519 SEALED
          </span>
        </div>
      </div>

      <p className="card-subtitle">
        Cryptographically signed authority parameters issued by Treasury Principal.
        Defines operational envelope and budget constraints for autonomous financial agents.
      </p>

      {/* Budget Progress Meter */}
      <div className="meter-section">
        <div className="meter-labels">
          <span className="meter-caption">Budget Utilization</span>
          <span className="meter-numbers tabular-nums">
            {formatMoney(spent)} / {formatMoney(lifetimeTotal)} ({spentPct}%)
          </span>
        </div>
        <div
          className="progress-track"
          role="progressbar"
          aria-label="Mandate lifetime authority budget utilization"
          aria-valuenow={spentPct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={`progress-fill ${spentPct > 90 ? "fill-danger" : spentPct > 70 ? "fill-warning" : "fill-primary"}`}
            style={{ width: `${spentPct}%` }}
          />
        </div>
        <div className="meter-footer">
          <span className="remaining-text">
            Remaining Authority: <strong className="tabular-nums">{formatMoney(remaining)}</strong>
          </span>
        </div>
      </div>

      {/* Read-Only Parameter Grid */}
      <div className="mandate-grid">
        <div className="spec-card">
          <span className="spec-label">SINGLE TRANSACTION CAP</span>
          <span className="spec-val tabular-nums">{formatMoney(mandate.single_limit_minor)}</span>
          <span className="spec-hint">Hard ceiling per request</span>
        </div>

        <div className="spec-card">
          <span className="spec-label">INSTANT AUTONOMOUS THRESHOLD</span>
          <span className="spec-val tabular-nums">{formatMoney(mandate.instant_threshold_minor)}</span>
          <span className="spec-hint">Exceeding triggers human step-up</span>
        </div>

        <div className="spec-card">
          <span className="spec-label">AUTHORIZED AGENT</span>
          <span className="spec-val mono">{mandate.agent_id}</span>
          <span className="spec-hint">Autonomous agent subject</span>
        </div>

        <div className="spec-card">
          <span className="spec-label">ISSUING PRINCIPAL</span>
          <span className="spec-val mono">{mandate.principal_id}</span>
          <span className="spec-hint">Treasury governance identity</span>
        </div>
      </div>

      {/* Allowed Payees & Purposelist */}
      <div className="allowlist-grid">
        <div className="allowlist-box">
          <span className="allowlist-heading">REGISTERED PAYEES ALLOWLIST</span>
          <div className="chips-container">
            {mandate.allowed_payees && mandate.allowed_payees.length > 0 ? (
              mandate.allowed_payees.map((payee) => (
                <span key={payee} className="spec-chip mono">
                  <ShieldCheck size={11} className="inline-icon" aria-hidden="true" /> {payee}
                </span>
              ))
            ) : (
              <span className="spec-hint">No payees registered</span>
            )}
          </div>
        </div>

        <div className="allowlist-box">
          <span className="allowlist-heading">AUTHORIZED PURPOSES</span>
          <div className="chips-container">
            {mandate.allowed_purposes && mandate.allowed_purposes.length > 0 ? (
              mandate.allowed_purposes.map((p) => (
                <span key={p} className="spec-chip">
                  {p}
                </span>
              ))
            ) : (
              <span className="spec-hint">All legitimate business expenses</span>
            )}
          </div>
        </div>
      </div>

      {/* Validity & Signature Status */}
      <div className="mandate-footer-meta">
        <div className="footer-meta-item">
          <span className="meta-label">VALIDITY WINDOW</span>
          <span className="meta-val tabular-nums">
            {mandate.valid_from_utc} → {mandate.valid_until_utc}
          </span>
        </div>
        <div className="footer-meta-item">
          <span className="meta-label">ED25519 SIGNATURE SEAL</span>
          <code className="sig-code mono" title={mandate.signature}>
            {mandate.signature.slice(0, 32)}...
          </code>
        </div>
      </div>
    </article>
  );
};
