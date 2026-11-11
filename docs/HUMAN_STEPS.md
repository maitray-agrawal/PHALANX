# HUMAN_STEPS.md - Phalanx Manual Operation Guide

Manual steps required by human operators / hackathon judges. Non-destructive, documented procedures.

---

## 1. PayPal Sandbox Live Order Verification (E1 Check)

To verify the live Orders v2 checkout, buyer approval, and capture flow against PayPal sandbox:

1. Ensure `.env` or environment contains valid sandbox credentials:
   ```bash
   PAYPAL_CLIENT_ID=your_sandbox_client_id
   PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
   ```
2. Run the automated interactive verification script:
   ```bash
   python scripts/e1_sandbox_check.py
   ```
3. The script will output a buyer approval link:
   ```text
   Approval URL: https://www.sandbox.paypal.com/checkoutnow?token=...
   ```
4. Open the approval URL in your browser:
   - Log in using your PayPal Sandbox Personal (Buyer) account.
   - Click "Continue" / "Approve" to authorize the $25.00 USD transaction.
5. Return to the terminal and press `[ENTER]`.
6. The script captures the order and verifies final `COMPLETED` status via provider lookup.

---

## 2. Gemini API Live Invoice Agent (Optional)

To enable live Gemini 2.5 Flash model calls instead of recorded baseline runs:

1. Export your Google Gemini API key:
   ```bash
   export GEMINI_API_KEY="AIzaSy..."
   ```
2. (Optional) Select a model:
   ```bash
   export GEMINI_MODEL="gemini-2.5-flash"
   ```
3. Restart backend service. The Invoice Agent will automatically query Gemini in live mode with temperature 0.0, strict JSON schema output, and daily quota tracking.

---

## 3. Neon PostgreSQL Setup (Hosted Cloud)

1. Sign up at [Neon Console](https://console.neon.tech).
2. Create project `phalanx-db`.
3. In SQL Editor, run the initialization statements from `docs/evidence/neon-manual-setup.md`.
4. Copy the Direct Connection URI (with `sslmode=require`).
5. Set `DATABASE_URL` in your deployment environment.
