import React from "react";
import { Terminal } from "lucide-react";

export const DeveloperConsole: React.FC = () => {
  return (
    <section
      id="panel-developer"
      role="tabpanel"
      aria-labelledby="tab-developer"
      className="card"
    >
      <div className="card-header">
        <div className="card-title-row">
          <Terminal className="card-icon" />
          <h2 className="card-title">Model Context Protocol (MCP) & Developer Integration</h2>
        </div>
        <span className="phalanx-system-badge">FASTAPI + MCP SERVER</span>
      </div>
      <p className="card-subtitle">
        Integrate autonomous agents directly via standardized MCP tools or RESTful API endpoints.
        All operations require signed role tokens and adhere to object-level authorization (OLA).
      </p>

      <div className="mcp-tool-card">
        <div className="mcp-tool-title">tool: phalanx_authorize_transaction</div>
        <p className="subtext" style={{ marginBottom: "0.5rem" }}>
          Autonomous agent tool to evaluate and submit financial transaction intent under active
          Ed25519 mandate.
        </p>
        <pre className="code-block">
{`# Python MCP Client Integration Example
import requests

response = requests.post(
    "http://localhost:8000/v1/payment-requests",
    headers={"Authorization": f"Bearer {token}", "X-Phalanx-Role": "agent"},
    json={
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-paypal-sandbox-1",
        "amount_minor": 2500,
        "currency": "USD",
        "purpose": "Monthly server renewal",
        "idempotency_key": "unique_agent_uuid_001"
    }
)
decision = response.json()
print("Authorization Outcome:", decision["decision"]) # ALLOW | STEP_UP | DENY`}
        </pre>
      </div>

      <div className="mcp-tool-card">
        <div className="mcp-tool-title">tool: phalanx_get_mandate</div>
        <p className="subtext" style={{ marginBottom: "0.5rem" }}>
          Inspect current Ed25519 mandate limits, remaining budget balances, and allowlisted payees.
        </p>
        <pre className="code-block">
{`curl -X GET "http://localhost:8000/v1/mandates/mandate_default_sandbox" \\
  -H "Authorization: Bearer <principal_token>" \\
  -H "X-Phalanx-Role: principal"`}
        </pre>
      </div>
    </section>
  );
};
