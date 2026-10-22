# PHALANX Demo Script (Under 3 Minutes)

Target Video Runtime: 2 minutes 45 seconds.

---

### Scene 1: Autonomous Pre-Authorized Payment (0:00 - 0:45)
- **Actor Persona**: Autonomous Agent (`agent-auto-1`).
- **Action**: Agent submits a routine operational payment for $25.00 ("Monthly subscription renewal") via the Request Console.
- **Narrative**:
  - "Notice how the agent proposes the transaction intent. The policy engine evaluates deterministic bounds without calling any LLM."
  - "Because $25.00 is below the $500.00 instant threshold and within the active Ed25519 mandate, the policy returns `ALLOW`."
  - "The transaction dispatches instantly through the PayPal Sandbox rail, generating transaction ID `sandbox_tx_1001`, and records an immutable block in the audit ledger."

---

### Scene 2: Anomaly Detection & Human Step-Up Approval (0:45 - 1:45)
- **Actor Persona**: Agent initiates; Human Supervisor (`approver`) reviews.
- **Action**:
  - Agent submits a $1,200.00 equipment invoice.
  - Policy engine returns `STEP_UP`: "Amount exceeds instant threshold ($500.00); human approval required."
  - Switch persona to `agent` and attempt to click Approve -> UI blocks the action with a 403 Forbidden security banner ("Agents cannot approve their own requests").
  - Switch persona to `approver` -> The Approval Queue displays the canonical RFC 8785 SHA-256 digest locking the payee, amount, and purpose.
  - Supervisor approves -> Digest matches, budget is re-evaluated, and PayPal Sandbox payment executes.

---

### Scene 3: Cryptographic Shield-Wall Ledger & Tamper Detection (1:45 - 2:30)
- **Actor Persona**: Compliance Auditor (`auditor`).
- **Action**:
  - Open the Cryptographic Audit Ledger.
  - Show the visual blockchain: each event contains `prev_hash` pointing to the previous block.
  - Click **Verify Chain** -> Verification succeeds ("Cryptographic chain verified 100%").
  - Click **Simulate Database Tamper** (simulates an illicit SQL `UPDATE` modifying amount).
  - The block-chain visual immediately turns red at the broken link and highlights the tampered block index!
  - Click **Restore True Ledger** to restore integrity.

---

### Closing Summary (2:30 - 2:45)
- "PHALANX guarantees bounded financial authority for autonomous AI agents:
  1. Signed Ed25519 mandates.
  2. Pure deterministic policy engine.
  3. Digest-bound human approvals.
  4. Cryptographic hash-chained audit ledger.
  Sandbox only. No real money at risk."
