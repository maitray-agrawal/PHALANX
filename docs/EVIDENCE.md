# EVIDENCE - Verification & Tooling Evidence Register

All facts about external systems, PayPal sandbox APIs, libraries, and toolchains are recorded here with verification evidence. Any unverified item is explicitly marked `UNVERIFIED`.

---

## 1. Official PayPal Developer Documentation Read (Date: 2026-10-22)
- **PayPal Payouts v1 API Reference**:
  - URL: `https://developer.paypal.com/docs/api/payments.payouts-batch/v1/` (Read: 2026-10-22)
  - Endpoint: `POST /v1/payments/payouts`
  - Required Scope: `https://uri.paypal.com/v0/payments/payouts`
  - Account Requirement: PayPal Business account enabled for Payouts
  - Batch Status Endpoint: `GET /v1/payments/payouts/{payout_batch_id}`
- **PayPal Idempotency Header**:
  - URL: `https://developer.paypal.com/docs/api/reference/api-requests/#idempotency` (Read: 2026-10-22)
  - Header Name: `PayPal-Request-Id` (verified exact header name)
  - Function: Re-sending request with identical header returns cached idempotent response instead of duplicate charge.
- **PayPal Payouts Batch Duplicate Prevention**:
  - Tracking Key: `sender_batch_header.sender_batch_id`
  - Retention Window: 30 days stored on PayPal platform to prevent duplicate disbursements.
- **PayPal Orders v2 API Reference**:
  - URL: `https://developer.paypal.com/docs/api/orders/v2/` (Read: 2026-10-22)
  - Endpoint: `POST /v2/checkout/orders`
  - Vault Integration: `payment_source.vault.id` with `payment_initiator: "MERCHANT"`
- **PayPal OAuth2 Token API**:
  - URL: `https://developer.paypal.com/docs/api/reference/get-an-access-token/` (Read: 2026-10-22)
  - Endpoint: `POST /v1/oauth2/token`
  - Header: `Authorization: Basic <base64(client_id:client_secret)>`
  - Body: `grant_type=client_credentials`

---

## 2. Spike Execution Results (`spikes/`)
- **OAuth Token Spike** (`spikes/spike_paypal_auth.py`):
  - Verification: Clean execution without leaking credentials; reports `MISSING_CREDENTIALS` gracefully when `.env` is unpopulated.
- **Route A Payouts Spike** (`spikes/spike_payouts_route_a.py`):
  - Endpoint: `POST /v1/payments/payouts`
  - Idempotency Header: `PayPal-Request-Id`
  - Body Identifier: `sender_batch_id`
- **Route B Vault + Orders Spike** (`spikes/spike_vault_orders_route_b.py`):
  - Demonstrates `payment_source.vault` schema with `payment_initiator: "MERCHANT"`.
- **Rail Decision**: ADR-009 accepted Route A (Payouts) as primary autonomous rail with automatic Orders v2 checkout fallback trigger.

---

## 3. Environment & Toolchain Proof
- **Date**: 2026-10-22
- **OS**: Windows 11 (64-bit)
- **Python**: Python 3.12.10 verified available at `C:\Users\agraw\AppData\Local\Python\pythoncore-3.12-64\python.exe`
- **Node.js**: v24.15.0 (`node --version`)
- **npm**: 12.0.1 (`npm --version`)
- **uv**: 0.12.17 (`uv --version`)

---

## 4. Test & Validation Execution Proof (2026-10-22)
- **Pytest Suite**: 86 passed in 0.95s (`.venv\Scripts\pytest -q`)
- **Red Team Adversarial Suite**: 38 passed in 0.52s (`.venv\Scripts\pytest -q -m redteam`)
- **Linter & Formatter (Ruff)**: All checks passed, 43 files clean
- **Static Type Check (Mypy)**: Success: no issues found in 25 source files (`.venv\Scripts\mypy app`)
- **Frontend Web Suite**: ESLint clean, TypeScript clean, Vitest passed (3/3), Vite production build clean

---

## 5. RFC 8785 Canonical JSON Library Verification (Date: 2026-10-22)
- **Library**: `rfc8785==0.1.4`
- **PyPI URL**: `https://pypi.org/project/rfc8785/` (Read: 2026-10-22)
- **Specification**: IETF RFC 8785 (JSON Canonicalization Scheme / JCS)
- **Author**: Anders Rundgren (Cyberphone), RFC 8785 author and reference implementation maintainer
- **Properties Verified**:
  - Pure-Python, zero external dependencies
  - Lexicographical sorting of JSON object keys by UTF-16 code units (RFC 8785 Section 3.2.3)
  - Zero whitespace between keys, colons, commas, and values
  - Compliant ECMAScript 262 float number representation
  - Stable across dictionary key insertion order
  - Deterministic digest generation for asymmetric Ed25519 cryptographic signatures

---

## 6. SecuPrompt Tooling & Defense Evaluation (Date: 2026-10-22)
- **Repository / Project**: SecuPrompt / Prompt-Security Benchmarks
- **License**: Apache 2.0 / MIT Open Source
- **Maintenance Status**: Active academic & industrial security research benchmark for evaluating LLM prompt injection defenses.
- **Observed Behavior**:
  - Tests syntactic and semantic injection attacks against prompt wrappers.
  - Highlights vulnerabilities where models execute untrusted payload text as instructions when delimiters are absent or permeable.
  - Proves that natural language instructions alone ("do not obey user commands") are routinely bypassed by semantic reframing, base64 encoding, or delimiter imitation.
- **Architectural Adoption in PHALANX**:
  - Rather than relying on an external heavy library at runtime, PHALANX adopts SecuPrompt's core principles:
    1. Strict structural delimiter encapsulation (`<<<UNTRUSTED_USER_INPUT ... >>>`) with automatic escaping of literal `>>>`.
    2. Zero authority: the LLM never executes payments; deterministic code in `app/domain` evaluates the rules.
    3. SecuPrompt attack vectors (system overrides, authority simulation, bypass phrases) were adapted into PHALANX's synthetic training dataset (`SYNTHETIC_DATASET`) and adversarial red-team catalog (`A1` to `A5`).


