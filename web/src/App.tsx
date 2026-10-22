import React, { useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import { ModuleRegistry, AllCommunityModule } from "ag-grid-community";

// Register AG Grid Community modules
ModuleRegistry.registerModules([AllCommunityModule]);

interface LedgerEventRow {
  eventId: string;
  agentId: string;
  recipientId: string;
  amountMinor: number;
  currency: string;
  decision: "ALLOW" | "STEP_UP" | "DENY";
  purpose: string;
  timestamp: string;
}

const INITIAL_ROWS: LedgerEventRow[] = [
  {
    eventId: "evt_9b7e12f0a1d401e",
    agentId: "procurement-agent-01",
    recipientId: "cloud-services-inc",
    amountMinor: 24900,
    currency: "USD",
    decision: "ALLOW",
    purpose: "Compute cluster renewal (sandbox)",
    timestamp: "2026-10-22T12:00:00Z",
  },
  {
    eventId: "evt_3c88df5502a11b8",
    agentId: "marketing-ai-07",
    recipientId: "ad-network-sandbox",
    amountMinor: 150000,
    currency: "USD",
    decision: "STEP_UP",
    purpose: "Q4 ad spend spike - pending human supervisor review",
    timestamp: "2026-10-22T12:05:14Z",
  },
  {
    eventId: "evt_f41a09d3b7e90cc",
    agentId: "unverified-agent-99",
    recipientId: "external-unknown-wallet",
    amountMinor: 9500000,
    currency: "USD",
    decision: "DENY",
    purpose: "Unauthorized bulk withdrawal attempt",
    timestamp: "2026-10-22T12:12:30Z",
  },
];

export const App: React.FC = () => {
  const [rowData] = useState<LedgerEventRow[]>(INITIAL_ROWS);

  const columnDefs: ColDef<LedgerEventRow>[] = [
    { field: "eventId", headerName: "Event ID", width: 180 },
    { field: "timestamp", headerName: "Timestamp (UTC)", width: 200 },
    { field: "agentId", headerName: "Agent ID", width: 180 },
    { field: "recipientId", headerName: "Recipient ID", width: 180 },
    {
      field: "amountMinor",
      headerName: "Amount",
      width: 140,
      valueFormatter: (params) => {
        if (params.value == null) return "";
        const formatted = (params.value / 100).toFixed(2);
        return `$${formatted} ${params.data?.currency ?? "USD"}`;
      },
    },
    {
      field: "decision",
      headerName: "Decision",
      width: 130,
      cellRenderer: (params: { value: string }) => {
        const val = params.value;
        const cls =
          val === "ALLOW"
            ? "badge-allow"
            : val === "STEP_UP"
              ? "badge-step-up"
              : "badge-deny";
        return <span className={cls}>{val}</span>;
      },
    },
    { field: "purpose", headerName: "Purpose / Evidence", flex: 1 },
  ];

  return (
    <div className="app-container">
      <header className="header">
        <div className="brand">
          <span className="brand-shield">PHALANX</span>
          <span className="tagline">Authorization & Evidence Shield for Autonomous Agents</span>
        </div>
        <div className="status-badge" role="status" aria-label="System status operational">
          <span className="pulse-dot"></span>
          <span>SANDBOX GUARD ACTIVE</span>
        </div>
      </header>

      <main className="main-content">
        <section className="stats-grid" aria-label="Key Performance Indicators">
          <div className="stat-card">
            <div className="stat-title">Autonomous Authorizations</div>
            <div className="stat-value">1,428</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Step-Up Reviews Pending</div>
            <div className="stat-value" style={{ color: "var(--accent-amber)" }}>3</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Hard Denials Blocked</div>
            <div className="stat-value" style={{ color: "var(--accent-rose)" }}>17</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Ledger Integrity</div>
            <div className="stat-value" style={{ color: "var(--accent-emerald)" }}>100% Immutable</div>
          </div>
        </section>

        <section className="grid-section">
          <div className="section-header">
            <h2 className="section-title">Audit Ledger Events</h2>
          </div>
          <div style={{ height: 350, width: "100%" }}>
            <AgGridReact<LedgerEventRow>
              rowData={rowData}
              columnDefs={columnDefs}
              defaultColDef={{
                sortable: true,
                filter: true,
                resizable: true,
              }}
              theme="legacy"
            />
          </div>
        </section>
      </main>
    </div>
  );
};

export default App;
