#!/usr/bin/env python3
"""Generate cryptographically secure deployment secrets for PHALANX.

Outputs:
- SECRET_KEY: Single source of truth master key (HMAC role tokens + Ed25519 mandate seals)
- ADMIN_TOKEN: High-entropy secret for administrative endpoints
  (GET /v1/admin/client-ip, POST /v1/admin/reset)
- RECONCILE_SECRET: Secret for external cron reconciliation
  (POST /v1/admin/reconcile-scheduled, POST /v1/admin/daily-reset)

Security Rules:
- This script strictly prints to stdout; it NEVER writes secrets to disk or any file.
- Store these values immediately in your password manager (e.g. 1Password, Bitwarden).
- Paste these values directly into the Render Dashboard -> Environment tab.
- NEVER change SECRET_KEY once deployed: changing it invalidates existing mandate
  cryptographic seals and active role tokens.
"""

import secrets
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_ed25519_keypair(secret_key_hex: str) -> tuple[str, str]:
    """Derive deterministic Ed25519 public key and key ID from secret_key."""
    ikm = secret_key_hex.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"phalanx-mandate-ed25519",
    )
    seed = hkdf.derive(ikm)
    priv_key = Ed25519PrivateKey.from_private_bytes(seed)
    pub_bytes = priv_key.public_key().public_bytes_raw()
    pub_hex = pub_bytes.hex()
    digest = hashes.Hash(hashes.SHA256())
    digest.update(pub_bytes)
    key_id = f"key_{digest.finalize().hex()[:12]}"
    return pub_hex, key_id


def main() -> None:
    # 1. 256 bits (32 bytes) of cryptographically secure random entropy
    secret_key = secrets.token_hex(32)

    # 2. 32 bytes (256 bits) of URL-safe random string for admin token (>= 24 chars)
    admin_token = f"phx_adm_{secrets.token_urlsafe(32)}"

    # 3. 32 bytes of URL-safe random string for reconcile cron secret (>= 24 chars)
    reconcile_secret = f"phx_rec_{secrets.token_urlsafe(32)}"

    pub_hex, key_id = derive_ed25519_keypair(secret_key)

    output = f"""
================================================================================
PHALANX HOSTED DEPLOYMENT SECRETS (Render & Neon)
================================================================================
IMPORTANT OPERATIONAL INSTRUCTIONS:
1. Copy and paste the environment variables below into the Render Dashboard:
   Render Web Service -> Environment -> Environment Variables.
2. Store these secrets in your password manager (e.g. 1Password, Bitwarden).
3. NEVER write these secrets to any file, repository, or commit.
4. NEVER change SECRET_KEY after initial deployment:
   SECRET_KEY is the single source of truth for HMAC tokens and Ed25519 mandate
   signing. Changing it will cause all existing mandate signatures in Neon
   to fail verification (fail closed).
================================================================================

# --- PASTE INTO RENDER DASHBOARD ENVIRONMENT TAB ---

SECRET_KEY={secret_key}
ADMIN_TOKEN={admin_token}
RECONCILE_SECRET={reconcile_secret}

# --- DERIVED CRYPTOGRAPHIC METADATA (AUDIT / VERIFICATION) ---
# Ed25519 Key ID:    {key_id}
# Ed25519 Public Key: {pub_hex}
# Note: MANDATE_SIGNING_KEY_HEX is derived deterministically from SECRET_KEY
# via HKDF-SHA256. Do NOT set MANDATE_SIGNING_KEY_HEX in Render unless you are
# explicitly using an external KMS or hardware security module keypair.
================================================================================
"""
    sys.stdout.write(output.strip() + "\n")


if __name__ == "__main__":
    main()
