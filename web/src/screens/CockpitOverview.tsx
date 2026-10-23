import React from "react";
import { ShieldCheck } from "lucide-react";
import {
  AuthorizeSubmark,
  PaymentsSubmark,
  OutcomesSubmark,
  MonitorSubmark,
  ProtectSubmark,
  AuditSubmark,
} from "../components/AstraXIcons";
import type { ActiveTab } from "../App";

export interface CockpitOverviewProps {
  stepUpsCount?: number;
  chainIntegrity?: { isValid: boolean };
  ledgerEventsCount?: number;
  setActiveTab?: (tab: ActiveTab) => void;
  onNavigate?: (tab: ActiveTab) => void;
}

export const CockpitOverview: React.FC<CockpitOverviewProps> = ({
  stepUpsCount = 0,
  chainIntegrity = { isValid: true },
  ledgerEventsCount = 3,
  setActiveTab,
  onNavigate,
}) => {
  const handleNav = (tab: ActiveTab) => {
    if (setActiveTab) setActiveTab(tab);
    if (onNavigate) onNavigate(tab);
  };
  return (
    <section id="panel-overview" role="tabpanel" aria-labelledby="tab-overview">
      {/* Top KPI Metrics Deck */}
      <div className="cockpit-grid">
        <div className="metric-card">
          <div className="metric-card-header">
            <span className="metric-card-title">Authority Mandate</span>
            <AuthorizeSubmark size={20} />
          </div>
          <div className="metric-value">1 Active</div>
          <div className="metric-meta">
            <span className="metric-badge-blue">mandate_default_sandbox</span>
            <span className="subtext">Ed25519 Signed</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-card-header">
            <span className="metric-card-title">Volume (24h)</span>
            <PaymentsSubmark size={20} />
          </div>
          <div className="metric-value">$1,225.00</div>
          <div className="metric-meta">
            <span className="metric-badge-green">3 Requests</span>
            <span className="subtext">Minor unit ints</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-card-header">
            <span className="metric-card-title">Autonomous Allow</span>
            <OutcomesSubmark size={20} />
          </div>
          <div className="metric-value">66.7%</div>
          <div className="metric-meta">
            <span className="metric-badge-green">2 Pre-authorized</span>
            <span className="subtext">Under threshold</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-card-header">
            <span className="metric-card-title">Supervisor Step-Ups</span>
            <MonitorSubmark size={20} />
          </div>
          <div className="metric-value">{stepUpsCount} Pending</div>
          <div className="metric-meta">
            <span className="metric-badge-amber">Human In Loop</span>
            <span className="subtext">req_stepup_1001</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-card-header">
            <span className="metric-card-title">Adversarial Blocks</span>
            <ProtectSubmark size={20} />
          </div>
          <div className="metric-value">67 / 67</div>
          <div className="metric-meta">
            <span className="metric-badge-green">100% Red Team Pass</span>
            <span className="subtext">Zero leakage</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-card-header">
            <span className="metric-card-title">Ledger Integrity</span>
            <AuditSubmark size={20} />
          </div>
          <div className="metric-value">
            {chainIntegrity.isValid ? "100% Intact" : "Tamper Detected"}
          </div>
          <div className="metric-meta">
            <span className={chainIntegrity.isValid ? "metric-badge-green" : "metric-badge-amber"}>
              SHA-256 Chained
            </span>
            <span className="subtext">{ledgerEventsCount} Verified Blocks</span>
          </div>
        </div>
      </div>

      {/* Architecture Pipeline Flow Diagram */}
      <div className="pipeline-container">
        <div className="pipeline-header">
          <div className="pipeline-title">
            <ShieldCheck size={22} className="card-icon" />
            <span>PHALANX Operational Authorization Pipeline</span>
          </div>
          <span className="phalanx-system-badge">DETERMINISTIC ZERO-IO ENGINE</span>
        </div>
        <div className="pipeline-flow">
          <div className="pipeline-node active">
            <span className="node-step">01. Ingestion</span>
            <span className="node-title">Intent Delimiters</span>
            <span className="node-desc">Rigid boundary parsing; injection resistant</span>
          </div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-node active">
            <span className="node-step">02. Authority</span>
            <span className="node-title">Ed25519 Mandate</span>
            <span className="node-desc">Cryptographic envelope & budget ceilings</span>
          </div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-node active">
            <span className="node-step">03. Determinism</span>
            <span className="node-title">Pure Policy Core</span>
            <span className="node-desc">Zero clock, zero I/O, pure domain model</span>
          </div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-node active">
            <span className="node-step">04. Heuristics</span>
            <span className="node-title">ML Safety Signal</span>
            <span className="node-desc">Monotonic escalation only (never loosens)</span>
          </div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-node active">
            <span className="node-step">05. Execution</span>
            <span className="node-title">Idempotent Rail</span>
            <span className="node-desc">PayPal Sandbox; savepoint concurrency</span>
          </div>
          <div className="pipeline-arrow">→</div>
          <div className="pipeline-node active">
            <span className="node-step">06. Evidence</span>
            <span className="node-title">Audit Ledger</span>
            <span className="node-desc">SHA-256 immutable shield-wall hash chain</span>
          </div>
        </div>
      </div>

      {/* Interactive Control Shortcuts */}
      <div
        className="cockpit-shortcuts-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "1rem",
        }}
      >
        <div className="card">
          <h3 className="card-title">Direct Console Dispatch</h3>
          <p className="card-subtitle">
            Test prompt injection, single-transaction limits, and instant autonomous approvals.
          </p>
          <button
            type="button"
            className="tab-btn active"
            style={{ width: "100%", justifyContent: "center", display: "flex" }}
            onClick={() => handleNav("console")}
          >
            Launch Request Console →
          </button>
        </div>

        <div className="card">
          <h3 className="card-title">Pending Human Review ({stepUpsCount})</h3>
          <p className="card-subtitle">
            Review and sign off on escalated out-of-policy requests with digest validation.
          </p>
          <button
            type="button"
            className="tab-btn active"
            style={{ width: "100%", justifyContent: "center", display: "flex" }}
            onClick={() => handleNav("approvals")}
          >
            Open Step-Up Approvals →
          </button>
        </div>

        <div className="card">
          <h3 className="card-title">Shield-Wall Verification</h3>
          <p className="card-subtitle">
            Cryptographically verify hash chain continuity or simulate SQL injection tamper.
          </p>
          <button
            type="button"
            className="tab-btn active"
            style={{ width: "100%", justifyContent: "center", display: "flex" }}
            onClick={() => handleNav("ledger")}
          >
            Inspect Audit Ledger →
          </button>
        </div>
      </div>
    </section>
  );
};
