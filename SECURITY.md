# Security Policy — PHALANX

PHALANX is an authorization and governance layer designed to enforce security boundaries around autonomous financial agents. We take security vulnerabilities seriously and appreciate responsible disclosure.

---

## 1. Supported Versions

| Version | Supported | Security Maintenance |
|---|---|---|
| `1.0.x` (current `main`) | :white_check_mark: | Active security updates |
| `< 1.0.0` | :x: | Unsupported |

---

## 2. Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a vulnerability or security boundary flaw in PHALANX:

1. **GitHub Private Vulnerability Reporting (Preferred):**  
   Navigate to the repository's **Security** tab, click **Report a vulnerability**, and submit your report privately.

2. **Email Disclosure:**  
   Send an encrypted or detailed report to `maitray.agrawal@gmail.com` with the subject line `[SECURITY] PHALANX Vulnerability Report`.

### What to Include
- Detailed description of the vulnerability, including attack vector and potential impact.
- Reproducible steps, proof-of-concept script, or test case.
- Component(s) affected (`app/domain`, `app/application`, `app/infrastructure`, API endpoints, or database triggers).
- Proposed remediation or patch, if available.

### Response SLA
- **Initial Acknowledgement:** Within 48 hours of receipt.
- **Triage & Severity Assessment:** Within 5 business days.
- **Remediation Release:** Target within 14 business days, coordinated with responsible public disclosure.

---

## 3. Threat Model & Security Controls

PHALANX maintains documented security architectures and threat models:
- [Security Architecture & Threat Model](docs/security.md) — Comprehensive STRIDE analysis and red-team test coverage.
- [Security Baseline & Advisories](docs/SECURITY_BASELINE.md) — Dependency scanning results, known audit items, and baseline protections.

### Core Security Invariants
1. **Pure Domain Boundary:** `app/domain` contains zero I/O, no system clock, and no network dependencies.
2. **AI Non-Authority:** Large Language Models (Gemini 2.5 Flash) extract structured data inside strict delimiter boundaries but have zero payment authorization authority.
3. **Cryptographic Mandates:** Ed25519 asymmetric signatures over RFC 8785 canonical JSON seal all spending boundaries.
4. **Append-Only Ledger:** The PostgreSQL audit journal is immutable; the database trigger `trg_deny_ledger_mutation` denies all `UPDATE` and `DELETE` queries.
5. **Human-in-the-Loop:** Transactions exceeding instant thresholds require cryptographic intent digest approvals.

---

## 4. Sandbox Disclosure

PHALANX is an entry for the PayPal AI Hackathon 2026. The application operates exclusively against the **PayPal Developer Sandbox** (`https://api-m.sandbox.paypal.com`). No real money is transferred, and live financial credentials must never be configured in any environment.

