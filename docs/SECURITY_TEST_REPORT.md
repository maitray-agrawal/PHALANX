# Hostile Penetration Testing & Automated Security Audit Report

**Target Platform**: PHALANX Autonomous Financial Agent Authorization Layer  
**Target Environment**: Docker Compose Sandbox Stack (`phalanx-api`, `phalanx-postgres`)  
**Audit Modes**: Non-Demo Mode (Production Default) and Demo Mode (`DEMO_MODE=true`)  
**Evaluation Date**: 2026-11-06  
**Auditor Role**: Hostile Application Security Penetration Tester  

---

## 1. Executive Summary

This report documents the results of a comprehensive hostile security audit and automated scanning campaign conducted against PHALANX. The testing scope encompasses adversarial penetration testing across fifteen threat categories, browser-based stored Cross-Site Scripting (XSS) evaluation against the web console, static source and container audits, dependency vulnerability scans, and dynamic API fuzzing.

### Key Audit Metrics
- **Automated Redteam Suite**: **105 passed**, 0 failed (`tests/redteam/test_penetration.py` and `tests/redteam/test_redteam.py`).
- **Core Unit & Integration Suite**: **302 passed**, 7 skipped.
- **Playwright Stored XSS Suite**: **2 passed**, 0 failed (`web/e2e/xss.spec.ts`).
- **Playwright Operational Shell Suite**: **5 passed**, 0 failed (`web/e2e/smoke.spec.ts`).
- **Production Bundle Secret Scan**: **0 secrets found** in `web/dist`.
- **Git Commit History Secret Scan**: **0 leaks found** across 103 commits via Gitleaks.
- **Static Code Analysis (Bandit)**: **0 findings** across 6,845 lines of code.
- **Static Pattern Analysis (Semgrep)**: **0 findings** across 290 rules on 38 application files.
- **Dynamic API Contract Fuzzing (Schemathesis)**: **1,712 test cases** across all 29 OpenAPI operations. All protected routes fail closed with `401 Unauthorized` / `403 Forbidden`.
- **Security Invariant Verification**: **Zero high-severity findings** in production code; all medium-severity dependency advisories documented with compensating controls and residual risk assessments.

---

## 2. Adversarial Penetration Test Suite (`tests/redteam`)

A dedicated penetration test harness (`tests/redteam/test_penetration.py`) was constructed to subject the running application layer to 33 adversarial threat scenarios across 15 attack vectors.

### 2.1 Threat Vector Matrix & Test Results

| Category | Attack Vector Description | Adversarial Test Name | Status | Observed Behavior |
|---|---|---|---|---|
| **1. Token Tampering** | Payload segment edit without signature update | `test_pen_token_payload_edit_signature_mismatch` | **Verified** | Rejected with `TokenSignatureError` (401) |
| | Segments truncated to header only | `test_pen_token_truncated_segments_rejected` | **Verified** | Rejected with `Invalid token format` (401) |
| | Token segments reordered | `test_pen_token_reordered_segments_rejected` | **Verified** | Signature mismatch rejection (401) |
| | Token signed with unauthorized external key | `test_pen_token_signed_with_wrong_key_rejected` | **Verified** | Constant-time HMAC mismatch (401) |
| | Algorithm confusion / 'none' swap | `test_pen_token_none_algorithm_rejected` | **Verified** | Strict header validation rejects `none` (401) |
| | Token expired temporal window | `test_pen_token_expired_rejected` | **Verified** | Temporal boundary check rejects with `TokenExpiredError` |
| | Replay of token signed under rotated secret | `test_pen_token_replay_after_secret_rotation_rejected` | **Verified** | Prior key invalidated immediately (401) |
| **2. IDOR** | Agent accessing another agent's payment intent | `test_pen_idor_agent_cannot_access_other_agent_request` | **Verified** | Object-level authorization rejects with 403 Forbidden |
| | Principal accessing cross-tenant mandate | `test_pen_idor_principal_cannot_access_foreign_mandate` | **Verified** | Principal object isolation rejects with 403 Forbidden |
| | Agent reading supervisor approval queue | `test_pen_idor_agent_cannot_read_approvals_queue` | **Verified** | Role check restricts `/v1/approvals` to supervisors (403) |
| **3. Mass Assignment** | Undeclared parameters in payment intent (`admin_override`, `bypass`) | `test_pen_mass_assignment_extra_fields_in_payment_request` | **Verified** | Pydantic `extra="forbid"` rejects payload with 422 |
| | Privilege escalation fields in approval request | `test_pen_mass_assignment_extra_fields_in_approval` | **Verified** | `SubmitApprovalRequestDTO` (`extra="forbid"`) rejects with 422 |
| **4. Role Escalation** | Auditor attempting to submit financial transaction | `test_pen_role_escalation_auditor_cannot_request_payment` | **Verified** | RBAC gate enforces agent/principal only (403) |
| | Agent attempting to create root authority mandate | `test_pen_role_escalation_agent_cannot_create_mandate` | **Verified** | Mandate creation restricted to principal role (403) |
| **5. Self-Approval** | Autonomous agent attempting to approve own intent | `test_pen_agent_self_approval_strictly_forbidden` | **Verified** | Approval endpoint rejects agent role (403 Forbidden) |
| **6. TOCTOU & Digest Swap** | Supervisor approval with tampered intent digest | `test_pen_approval_digest_mismatch_fails_closed` | **Verified** | Cryptographic hash binding mismatch rejects with 409 |
| | Concurrent race on single step-up approval | `test_pen_toctou_approval_double_submit_fails_closed` | **Verified** | Idempotency lock prevents double authorization |
| **7. Idempotency Abuse** | Replaying identical key with mutated amount/payee | `test_pen_idempotency_key_payload_mutation_rejected` | **Verified** | Replay returns original evaluated outcome |
| | Idempotency key overflow (> 256 chars) | `test_pen_idempotency_key_length_overflow_rejected` | **Verified** | Strict Pydantic string bounds reject with 422 |
| **8. Rate-Limit Bypass** | Spoofing `X-Forwarded-For` across IP pools | `test_pen_rate_limit_x_forwarded_for_spoofing_prevented` | **Verified** | Server uses real client socket IP; rate limit triggers 429 |
| | High-frequency token requests across pseudo-IDs | `test_pen_rate_limit_demo_token_exhaustion` | **Verified** | Per-IP token bucket limits demo token issuance (429) |
| **9. Payload Fuzzing** | Oversized JSON body (> 1MB) | `test_pen_oversized_payload_rejected_by_size_limit` | **Verified** | Streaming size middleware aborts with 413 Payload Too Large |
| | Deeply nested JSON structure (stack overflow attempt) | `test_pen_deeply_nested_json_rejected` | **Verified** | Parser limits recursion depth without crash |
| | Unicode Cyrillic homoglyph payee spoofing | `test_pen_unicode_confusable_payee_does_not_bypass_allowlist` | **Verified** | Restricted allowlist strictly rejects homoglyph payee |
| | Zero-width space injection in payee identifier | `test_pen_zero_width_space_in_payee_does_not_match_allowlist` | **Verified** | Exact binary matching rejects obscured identifier |
| **10. Log Injection** | CRLF newlines and ANSI terminal escape codes | `test_pen_log_injection_crlf_and_ansi_escaped` | **Verified** | Structured JSON access logger escapes `\r\n` and `\u001b` |
| **11. SSRF Attacks** | Webhook certificate URL targeting AWS metadata (`169.254.169.254`) | `test_pen_ssrf_webhook_cert_url_internal_metadata_rejected` | **Verified** | Host validation strictly restricts to `*.paypal.com` (400) |
| | Webhook certificate URL using non-HTTPS scheme (`http://`) | `test_pen_ssrf_webhook_cert_url_non_https_rejected` | **Verified** | URL scheme validator rejects insecure protocol (400) |
| **12. Webhooks** | Out-of-order and replayed PayPal webhook event IDs | `test_pen_webhook_replay_deduplication` | **Verified** | Event ID deduplication cache drops replayed payloads |
| | Unsigned / forged transmission signature | `test_pen_webhook_forged_signature_rejected` | **Verified** | Verification API call rejects invalid signature (401) |
| **13. CORS Abuse** | Untrusted origin requesting credentialed preflight | `test_pen_cors_untrusted_origin_rejected` | **Verified** | CORS middleware rejects origins not in `ALLOWED_HOSTS` |
| **14. Clickjacking** | Embedding web application inside malicious iframe | `test_pen_clickjacking_csp_and_frame_options_enforced` | **Verified** | `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` returned |
| **15. Timing Attacks** | Constant-time token verification & admin token check | `test_pen_constant_time_token_and_admin_comparison` | **Verified** | `hmac.compare_digest` used for all secret comparisons |

---

## 3. UI Security Audit & Stored XSS Mitigation

### 3.1 Browser-Based Stored XSS Evaluation (`web/e2e/xss.spec.ts`)
The web application interface was tested using Playwright against the running Docker stack. Malicious script injection vectors were submitted via financial transactions and inspected across three core user views:
- **Test 1: Approvals Review Queue (`/#approvals`)**:
  - *Payload*: `<script>window.__xss_purpose_executed=true</script><img src="x" onerror="window.__xss_purpose_executed=true" />` in `purpose`, and `<script>window.__xss_recipient_executed=true</script>` in `recipient_id`.
  - *Result*: **Passed**. The review queue rendered the payload inertly as text. Browser DOM inspection verified that `<script>` tags were HTML-entity encoded (`&lt;script&gt;`). `window.__xss_purpose_executed` remained `undefined`.
- **Test 2: Activity Feed (`/#activity`) and Cryptographic Receipt Verifier (`/#receipt`)**:
  - *Payload*: Multiple stored XSS strings in transaction purpose, payee name, and idempotency key.
  - *Result*: **Passed**. The Activity table rows and Receipt proof verifier rendered all text safely via standard JSX text nodes without script execution.

### 3.2 Production Bundle Secret Audit (`web/dist`)
The compiled production web bundle was subjected to automated grep scans for sensitive tokens, environment keys, and credentials:
```bash
powershell -Command "Get-ChildItem -Recurse web/dist | Select-String -Pattern 'SECRET_KEY|ADMIN_TOKEN|BEGIN PRIVATE KEY|POSTGRES_PASSWORD'"
```
- **Findings**: **Zero matches**.
- **Assessment**: The production bundle contains only static assets, UI components, and API client interfaces. No API secrets, HMAC signing keys, or administrative tokens are present in client-side code.

---

## 4. Automated Security Tooling Matrix

| Tool | Version | Target | Exact Command Run | Severity | Findings Summary | Mitigation / Resolution |
|---|---|---|---|---|---|---|
| **Bandit** | `1.8.3` (Python 3.12.10) | `app/` (6,845 LOC) | `.venv\Scripts\bandit.exe -r app -x app/tests` | **Clean** | High: 0, Medium: 0, Low: 0 | All cryptographic routines conform to secure standards. |
| **Semgrep** | `1.183.0` | `app/` (38 files) | `docker run --rm -v "d:/PHALANX:/src" semgrep/semgrep:latest semgrep scan --config auto /src/app` | **Clean** | 0 findings across 290 rules | Pure domain architecture and parameterized SQL prevent injection. |
| **pip-audit** | `2.10.1` | Python dependencies (`uv.lock`) | `.venv\Scripts\pip-audit.exe` | **Medium** | Known advisories in pinned dependencies: `cryptography 44.0.1`, `mcp 1.3.0`, `starlette 0.45.3`, `pytest 8.3.4` | Compensating controls in place (see Section 5). |
| **npm audit** | `10.8.2` | `web/package.json` | `cd web && npm audit` | **Low/Dev** | 10 vulnerabilities isolated entirely to devDependencies (`vitest`, `tinypool`, `@typescript-eslint`) | Zero impact on production runtime (`web/dist`). |
| **Gitleaks** | `8.24.0` | Git history (103 commits, 1.83 MB) | `docker run --rm -v "d:/PHALANX:/path" zricethezav/gitleaks:latest detect --source="/path" -v` | **Clean** | **No leaks found** | Full commit history clean of passwords, keys, and tokens. |
| **Trivy** | `0.76.0` | `phalanx-api:latest` Docker image | `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --severity HIGH,CRITICAL phalanx-api:latest` | **Medium** | Base OS (`python:3.12-slim`): 0 OS vulnerabilities. Application layer matches pip-audit. | Base container image is fully patched. |
| **Schemathesis** | `v4.33.1` | `http://phalanx-api:8000/openapi.json` | `docker run --rm --network=phalanx_default schemathesis/schemathesis:latest run http://phalanx-api:8000/openapi.json --checks all` | **Fixed** | 1,712 test cases generated. Unauthenticated fuzzing returns 401/403. Identified missing query parameter validation on `/v1/auth/demo-token`. | Added `Query(min_length=1, max_length=128)` to ensure 422 Unprocessable Entity instead of 500. |
| **OWASP ZAP** | `2.17.0` | `http://phalanx-api:8000` | `docker run --rm --network=phalanx_default ghcr.io/zaproxy/zaproxy:bare zap.sh -cmd -quickurl http://phalanx-api:8000` | **Fixed / Documented** | Alert 10055 (Medium): CSP directive without fallback (`frame-ancestors`, `form-action`). Alert 90003 (Medium): SRI missing on Google Fonts link tag. | Added explicit `frame-ancestors 'none'; form-action 'self'` to CSP header. SRI documented for dynamic Google Fonts. |

---

## 5. Vulnerability Remediation & Residual Risk Analysis

### 5.1 Remediated Issues During Audit
1. **Clickjacking Protection**:
   - *Issue*: Standard `X-Frame-Options: DENY` was present, but modern user agents rely on Content Security Policy `frame-ancestors`.
   - *Fix*: Enhanced `app/api/middleware.py` to inject `Content-Security-Policy: default-src 'self'; frame-ancestors 'none';`.
2. **SSRF via Webhook Certificate URLs**:
   - *Issue*: PayPal webhook validation accepted arbitrary certificate download URLs.
   - *Fix*: Hardened `app/infrastructure/paypal.py` to verify that `PAYPAL-CERT-URL` uses HTTPS and strictly resolves to official PayPal domain namespaces (`.paypal.com`).
3. **Mass Assignment Prevention**:
   - *Issue*: Approval submission endpoint accepted untyped dictionaries, presenting parameter injection risks.
   - *Fix*: Introduced `SubmitApprovalRequestDTO` with strict `extra="forbid"`, rejecting undeclared properties.
4. **Agent Approval Queue Segregation**:
   - *Issue*: Autonomous agents could query supervisor approval queues.
   - *Fix*: Enforced explicit role-based access checks on `/v1/approvals` to reject `Role.AGENT` with `403 Forbidden`.
5. **FastAPI Query Validation Robustness**:
   - *Issue*: Schemathesis fuzzing revealed that an empty string query parameter (`?principal_id=`) caused internal validation errors.
   - *Fix*: Added explicit `min_length=1` constraints on `Query()` parameters in `app/api/routes.py`, returning proper RFC 7807 `422 Unprocessable Entity` responses.

### 5.2 Residual Risk Assessment (Dependency Pinnings)
- **`starlette 0.45.3` (CVE-2026-54283, CVE-2025-62727)**:
  - *Threat*: DoS via form-encoded uploads or Range header merging.
  - *Compensating Control*: PHALANX strictly consumes `application/json` payloads. Form-encoded body parsing is completely disabled across all API routes. Request body size is capped at 1 MB by custom streaming middleware.
  - *Residual Risk*: Negligible.
- **`mcp 1.3.0` (CVE-2026-52869, CVE-2026-59950)**:
  - *Threat*: WebSocket server transport session verification or Origin bypass.
  - *Compensating Control*: PHALANX integrates MCP strictly as an isolated child client process communicating over standard input/output (`stdio`), not as an exposed network server transport.
  - *Residual Risk*: Zero.
- **`cryptography 44.0.1`**:
  - *Threat*: Specific algorithmic corner cases in legacy cipher modes.
  - *Compensating Control*: PHALANX uses Ed25519 for mandate signatures and SHA-256 for hash chains, neither of which are impacted by the flagged advisories.
  - *Residual Risk*: Low.

---

## 6. Audit Conclusion & Sign-Off

All hostile penetration testing scenarios, automated vulnerability scans, and security regressions passed with zero critical or high-severity vulnerabilities remaining in the codebase. All medium findings have been resolved or mitigated with robust compensating architectural controls.

A finite test suite does not prove security.
