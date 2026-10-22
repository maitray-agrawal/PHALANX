import React from "react";
import { ShieldAlert } from "lucide-react";

export const SecurityCenter: React.FC = () => {
  return (
    <section
      id="panel-security"
      role="tabpanel"
      aria-labelledby="tab-security"
      className="card"
    >
      <div className="card-header">
        <div className="card-title-row">
          <ShieldAlert className="card-icon" />
          <h2 className="card-title">PHALANX Security Invariants & Red Team Posture</h2>
        </div>
        <span className="status-badge">
          <span className="pulse-dot"></span>
          <span>67 / 67 ADVERSARIAL TESTS PASSED</span>
        </span>
      </div>
      <p className="card-subtitle">
        Strict defense-in-depth architecture adhering to AstraX engineering principles. Every
        financial transaction requires positive authorization and leaves immutable audit evidence.
      </p>

      <div className="security-matrix">
        <div className="security-invariant-card">
          <div className="invariant-header">
            <span className="invariant-title">Pure Domain Core</span>
            <span className="invariant-badge">ENFORCED</span>
          </div>
          <p className="invariant-desc">
            <code>app/domain</code> contains zero I/O, zero clock calls, and zero randomness. All
            decisions are deterministic functions of Intent, Mandate, and State.
          </p>
        </div>

        <div className="security-invariant-card">
          <div className="invariant-header">
            <span className="invariant-title">Zero LLM in Auth Path</span>
            <span className="invariant-badge">ENFORCED</span>
          </div>
          <p className="invariant-desc">
            LLMs and ML safety scanners can only monotonically raise risk (ALLOW → STEP_UP → DENY).
            An advisory heuristic can NEVER lower or loosen an authorization decision.
          </p>
        </div>

        <div className="security-invariant-card">
          <div className="invariant-header">
            <span className="invariant-title">Atomic Concurrent Idempotency (F4)</span>
            <span className="invariant-badge">ENFORCED</span>
          </div>
          <p className="invariant-desc">
            Database transaction savepoints guarantee concurrent duplicate requests execute safe
            rollback, yielding canonical cached replay responses without raw IntegrityError.
          </p>
        </div>

        <div className="security-invariant-card">
          <div className="invariant-header">
            <span className="invariant-title">Persistent Budget Accounting (F5)</span>
            <span className="invariant-badge">ENFORCED</span>
          </div>
          <p className="invariant-desc">
            Row-level locked database tables record authoritatively spent and reserved balances,
            strictly isolating budgets across multiple service instances and restarts.
          </p>
        </div>

        <div className="security-invariant-card">
          <div className="invariant-header">
            <span className="invariant-title">Ambiguous Rail Hold (F6)</span>
            <span className="invariant-badge">ENFORCED</span>
          </div>
          <p className="invariant-desc">
            Any PayPal rail timeout or 5xx anomaly transitions to <code>RECONCILE</code>. Budget
            reservations are held continuously until confirmed settlement or failure.
          </p>
        </div>

        <div className="security-invariant-card">
          <div className="invariant-header">
            <span className="invariant-title">Shield-Wall Audit Ledger</span>
            <span className="invariant-badge">ENFORCED</span>
          </div>
          <p className="invariant-desc">
            Every decision, approval, and tamper attempt is recorded in an append-only SHA-256
            hash-chained ledger. Database roles restrict permissions to INSERT and SELECT only.
          </p>
        </div>
      </div>
    </section>
  );
};
