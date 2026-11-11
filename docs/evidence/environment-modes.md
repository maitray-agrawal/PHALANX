# Environment Model and Modes in PHALANX

**Date:** 2026-11-10  
**Status:** VERIFIED via codebase inspection and unit/integration tests

---

## Accepted `ENVIRONMENT` Values

PHALANX evaluates `ENVIRONMENT` (or `settings.environment`) in several critical security boundaries:

| Environment | Classification | Behavior & Invariants |
|---|---|---|
| `production`, `prod` | Production | Strict fail-closed.<br>• `is_test_environment()` = `False`.<br>• Real `SECRET_KEY` (>= 32 bytes) mandatory.<br>• Real `MANDATE_SIGNING_KEY_HEX` or `SECRET_KEY` required (no ephemeral fallback).<br>• Database session factory mandatory.<br>• **`POST /v1/admin/reset` is strictly forbidden (HTTP 403).** |
| `staging` | Pre-production | Identical security posture to `production`.<br>• `is_test_environment()` = `False`.<br>• Admin reset allowed only if not blocked, but all cryptographic & database guards remain fail-closed. |
| `demo` | Hosted Demo / Evaluation | **Secure demonstration mode for Render & cloud evaluations.**<br>• `is_test_environment()` = `False` (no test mocks, no ephemeral keys, real cryptographic validation active).<br>• Real `SECRET_KEY` (>= 32 bytes) mandatory.<br>• Real `MANDATE_SIGNING_KEY_HEX` or `SECRET_KEY` required.<br>• Database session factory mandatory.<br>• **`POST /v1/admin/reset` is allowed with valid `X-Admin-Token` or Principal role for periodic/daily cleanup.**<br>• `DEMO_SEED=true` seeds sample scenarios safely at boot. |
| `development` | Local Development | Default mode.<br>• Same fail-closed cryptographic checks as demo unless test markers are present. |
| `test`, `testing` | Automated Tests | Test harness execution only.<br>• `is_test_environment()` = `True`.<br>• Ephemeral Ed25519 key generation allowed.<br>• Database session factory optional for isolated unit mocks. |

---

## Fail-Closed Boundaries Summary

1. **Secret Key Validation (`validate_secret_key`):**
   In `production`, `staging`, and `demo`, `SECRET_KEY` must be set and contain at least 32 UTF-8 bytes.
2. **Mandate Cryptographic Keys (`load_or_generate_keypair`):**
   In `production`, `staging`, and `demo`, an explicit signing key or secret key must be provided; ephemeral fallback generates an immediate `ValueError`.
3. **Database Immutability & Persistence:**
   In `production`, `staging`, and `demo`, services demand a live SQLAlchemy session factory.
4. **Admin Reset Endpoint (`POST /v1/admin/reset`):**
   Requires authentication via `X-Admin-Token` (min 24 chars) or authenticated Principal bearer token in all environments. In `production`/`prod`, it is disabled completely with `403 Forbidden`. In `demo`, it permits resets to restore clean evaluation state.

