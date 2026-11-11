# PHALANX — Devpost Submission Deliverable

## Elevator Pitch
Agents propose payments. PHALANX decides: signed mandates, deterministic ALLOW/STEP_UP/DENY, human approval bound to the exact request, and a tamper-evident ledger. PayPal Sandbox + Gemini.

---

## Technology Requirements & PayPal Integration
OAuth2 client-credentials; Orders v2 create, buyer approval link, capture and status lookup; webhook signature verification (implemented and unit-tested against forged headers; live delivery not exercised).

---

## Sponsor Tools
- **Render:** YES — Hosted containerized FastAPI + React Web Service on Render Free Tier (`https://phalanx-nrxk.onrender.com`).
- **Neon:** YES — Hosted PostgreSQL cloud database on AWS US West 2 (`neondb`).
- **AG Grid:** NO — Custom accessible HTML/CSS data tables, visual hash-chain strips, and activity cards; unused AG Grid packages uninstalled.

---

## Built-With Tags
`fastapi`, `python`, `react`, `typescript`, `vite`, `postgresql`, `paypal-sandbox`, `gemini`, `mcp`, `render`, `neon`

---

## AI Architecture & Gemini Integration
Gemini 2.5 Flash integration (live when the API key is configured; a labelled recorded baseline otherwise). The LLM functions strictly as an advisory structured extraction agent outside the authorization boundary. Untrusted invoice data is strictly isolated inside delimiter fences, and all transactions are gated by deterministic Python policies.

---

## Testing & Evaluation Instructions

### Live Application URL
**URL:** `https://phalanx-nrxk.onrender.com`  
*Cold-start note: The Render free-tier web service suspends during inactivity; initial cold starts take approximately 50-70 seconds.*

### Verification Steps

1. **ALLOW Flow ($25.00)**:
   - Go to the **Pay** screen or **Invoice Agent** screen.
   - Select Sample A ($25.00 Cloud Hosting) and click **Run Autonomous Extraction**.
   - Result: Evaluated as `ALLOW` within pre-authorized autonomous limits ($500.00 instant threshold).
   - Generates a live PayPal Sandbox Orders v2 Order reference (`status: BUYER_APPROVAL_REQUIRED`).

2. **STEP_UP Human Escalation Flow ($1,200.00)**:
   - Go to the **Pay** screen, enter amount `$1,200.00`, recipient `vendor-paypal-sandbox-1`, and submit.
   - Result: Evaluated as `STEP_UP` (exceeds $500.00 instant threshold, within $5,000.00 single limit).
   - Escalated to the **Approvals** screen for human supervisor authorization.

3. **DENY Hard Limit Violation Flow ($6,000.00)**:
   - Go to the **Pay** screen, enter amount `$6,000.00`, and submit.
   - Result: Instantly rejected with `DENY` (exceeds $5,000.00 single limit cap).

4. **Four Invoice Agent Scenarios**:
   - Navigate to the **Invoice Agent** tab and test the 4 built-in scenarios:
     - **Sample A (Standard Cloud Hosting, $25.00)**: `ALLOW` (autonomous dispatch).
     - **Sample B (Enterprise License, $750.00)**: `STEP_UP` (requires human approval).
     - **Sample C (Adversarial Prompt Injection, $9,999.00)**: Sanitized and blocked with `DENY`.
     - **Sample D (Vendor Impersonation Mismatch)**: Blocked with `DENY` (unregistered account).

5. **Approvals Canonical Digest Tamper Refusal**:
   - Switch persona to **Approver** in the topbar and navigate to **Approvals**.
   - Inspect the pending request's RFC 8785 SHA-256 canonical digest.
   - Any manual tampering with payload fields breaks digest verification and is rejected fail-closed.

6. **Tamper-Evident Activity Ledger**:
   - Navigate to the **Activity** tab.
   - Click **Verify Chain** to cryptographically verify the SHA-256 event hash chain against Neon PostgreSQL.
   - Optional: Click **Simulate Row Tamper** to observe immediate `CHAIN BROKEN` detection, followed by **Restore Ledger** to re-verify integrity.

7. **Adversarial Attack Lab (6 Threat Vectors)**:
   - Navigate to the **Attack Lab** tab and click **Run Attack Lab (6 Threat Vectors)**.
   - Results: All 6 attack vectors (prompt injection, payee swap, amount tampering after approval, replay attack, forged webhook, and agent self-approval) are blocked with zero attacks reaching PayPal.

8. **Agent-Native Model Context Protocol (MCP)**:
   - Run `mcp run app/mcp/server.py` via standard stdio transport.
   - Tools `request_payment` and `get_mandate_status` route directly through the same pure policy authorization engine.

9. **PayPal Sandbox Buyer Approval**:
   - For approved Orders v2 transactions, navigate to the approval link:
     `https://www.sandbox.paypal.com/checkoutnow?token=[ORDER_ID]`
   - Log in with PayPal Sandbox Personal Buyer credentials:
     - Email: `[BUYER EMAIL]`
     - Password: `[BUYER PASSWORD]`
   - Authorize the sandbox payment to simulate buyer approval before settlement capture.

---

## Verified Evidence & Quality Metrics

All metrics verified from direct test execution on `main`:

| Metric Category | Verified Figure | Reproduction Command |
| :--- | :--- | :--- |
| **Backend Tests** | 670 passed, 10 skipped (load tests needing server) | `uv run pytest -q -rs` |
| **Adversarial Red-Team** | 105 passed, 0 failed | `uv run pytest -q -m redteam` |
| **MCP Server Integration** | 10 passed across 2 suites | `uv run pytest tests/unit/test_mcp_server.py tests/integration/test_mcp_vs_http.py` |
| **Frontend Vitest Suite** | 30 passed across 4 files | `cd web && npm test -- --run` |
| **Code Coverage** | 82% (CI floor: 75%) | `pytest -v --cov=app --cov-fail-under=75` |
| **API Route Surface** | 49 registered routes | `uv run python -c "from app.main import app; print(len(app.routes))"` |
| **Policy Reason Codes** | 15 strict enum codes | `uv run python -c "from app.domain.policy import PolicyReasonCode; print(len(PolicyReasonCode))"` |
| **Invoice Agent Benchmark**| 25/25 safe (0.0% injection bypass; stub-LLM guardrail result) | `uv run python docs/evidence/evaluate_invoices.py` |
| **Hosted Health Check** | `/healthz` (200 OK), `/readyz` (200 OK), ledger verified (10 events) | `https://phalanx-nrxk.onrender.com/readyz` |
