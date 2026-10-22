# ADR-009: Payment Rail Selection & Fallback Architecture

- **Status**: Accepted
- **Date**: 2026-10-22
- **Author**: Staff Integration Engineer
- **Context**: PayPal AI Hackathon 2026 entry, AstraX product (sandbox money only).

---

## 1. Context & Problem Statement
Autonomous financial agents need an external payment rail to disburse funds. Direct human interactive checkout (redirecting the payer to log in on each transaction) breaks agent autonomy. We evaluated three integration routes against the official PayPal Sandbox APIs:

1. **Route A: PayPal Payouts v1 API (`POST /v1/payments/payouts`)**
   - Business account disbursement to recipient emails or PayPal IDs.
   - Payer (merchant/principal) does not need to be present during execution.
   - Idempotency supported via `PayPal-Request-Id` header and `sender_batch_id`.
   - Requires `https://uri.paypal.com/v0/payments/payouts` permission scope.

2. **Route B: PayPal Vault + Orders v2 (`POST /v2/checkout/orders` with `payment_source.vault`)**
   - Requires an initial Customer-Initiated Transaction (CIT) to obtain a customer `vault_id`.
   - Subsequent transactions use Merchant-Initiated Transaction (MIT) rules (`payment_initiator: "MERCHANT"`).
   - Requires Advanced Credit and Debit Card processing or PayPal Account Vaulting enabled on the sandbox account.

3. **Fallback Route: Orders v2 Checkout (`POST /v2/checkout/orders` with `intent: "CAPTURE"`)**
   - Generates an order ID and returns an approval link (`rel: "approve"`).
   - Works on all standard personal and business sandbox accounts without special approval scopes.

---

## 2. Decision
1. **Primary Route: Route A (Payouts v1 API)**
   - Payouts is the native paradigm for autonomous agent disbursements: the agent acts under a pre-funded treasury mandate to disburse funds to approved third-party vendors without requiring interactive human login at runtime.
   - Network idempotency is guaranteed via the `PayPal-Request-Id` header.
   - Application batch tracking is guaranteed via `sender_batch_id` (stored for 30 days by PayPal).

2. **Automatic Fallback Trigger**:
   - If the sandbox account returns `403 Forbidden` (lacking mass payment / Payouts feature activation) or if Payouts fails, the adapter automatically falls back to **Orders v2 Checkout**.
   - In test and local development environments without configured credentials, the system uses `FakePaymentRail` to guarantee 100% deterministic, hermetic test execution.

3. **Domain Protocol**:
   - `PaymentRail` Protocol lives in `app/domain/ports.py` with methods:
     - `pay(intent: TransactionIntent) -> PaymentResult`
     - `lookup(transaction_id: str) -> PaymentResult`
     - `normalize_error(raw_error: Any) -> str`
   - Zero I/O or network dependencies in `app/domain`.

---

## 3. Consequences & Evidence
- **Positive**: Complete autonomy for payments within authorized policy bounds; robust fallback when Payouts scope is not active on judge accounts.
- **Negative**: Payouts sandbox accounts require business tier verification for live execution.
- **Evidence**: Verified API endpoints, idempotency header (`PayPal-Request-Id`), and parameter schemas recorded in [docs/EVIDENCE.md](file:///d:/PHALANX/docs/EVIDENCE.md).
