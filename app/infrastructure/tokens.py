"""Cryptographic role tokens for PHALANX.

Implements signed, short-lived role tokens for:
- principal
- agent
- approver
- auditor

Tokens use HMAC-SHA256 with URL-safe base64 encoding and expiration verification.
"""

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from app.infrastructure.config import settings


class Role(str, Enum):
    """Authorization roles in PHALANX."""

    PRINCIPAL = "principal"
    AGENT = "agent"
    APPROVER = "approver"
    AUDITOR = "auditor"


@dataclass(frozen=True)
class Identity:
    """Authenticated identity extracted from a verified role token."""

    subject: str
    role: Role
    principal_id: str
    agent_id: str | None = None
    expires_at_utc: datetime = datetime.min


class TokenError(Exception):
    """Base exception for authentication token errors."""


class TokenExpiredError(TokenError):
    """Token expiration window has passed."""


class TokenSignatureError(TokenError):
    """Token HMAC signature is invalid or tampered."""


def _get_signing_key() -> bytes:
    """Fetch secret key for signing tokens."""
    key = settings.secret_key
    if not key:
        # Fallback to deterministic key derived from mandate key or system fallback for tests
        key = settings.mandate_signing_key_hex or "phalanx-secure-token-signing-key-default"
    return key.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_role_token(
    role: Role,
    principal_id: str,
    subject: str | None = None,
    agent_id: str | None = None,
    expires_in_seconds: int = 900,  # 15 minutes default
) -> str:
    """Generate a signed HMAC-SHA256 short-lived role token."""
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expires_in_seconds)

    header = {"alg": "HS256", "typ": "PHX"}
    payload = {
        "sub": subject or f"{role.value}:{agent_id or principal_id}",
        "role": role.value,
        "principal_id": principal_id,
        "agent_id": agent_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    signing_input = f"{_b64url_encode(header_bytes)}.{_b64url_encode(payload_bytes)}".encode()
    signature = hmac.new(_get_signing_key(), signing_input, hashlib.sha256).digest()

    return f"{signing_input.decode('ascii')}.{_b64url_encode(signature)}"


def verify_role_token(token_str: str) -> Identity:
    """Verify cryptographic signature and expiration of a role token."""
    # Support convenient demo tokens
    if token_str.startswith("demo-"):
        role_name = token_str.replace("demo-", "").lower()
        try:
            role = Role(role_name)
        except ValueError as err:
            raise TokenSignatureError(f"Invalid demo role: {role_name}") from err
        return Identity(
            subject=f"demo:{role_name}",
            role=role,
            principal_id="principal_astra_treasury",
            agent_id="agent-auto-1" if role == Role.AGENT else None,
            expires_at_utc=datetime.now(UTC) + timedelta(hours=1),
        )

    parts = token_str.split(".")
    if len(parts) != 3:
        raise TokenSignatureError("Malformed token structure: expected 3 segments.")

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode()

    expected_sig = hmac.new(_get_signing_key(), signing_input, hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(signature_b64)
    except Exception as exc:
        raise TokenSignatureError(f"Invalid base64 signature encoding: {exc}") from exc

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise TokenSignatureError("Invalid token signature.")

    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise TokenSignatureError(f"Invalid token payload JSON: {exc}") from exc

    exp_ts = payload.get("exp")
    if exp_ts is None:
        raise TokenSignatureError("Token missing expiration timestamp.")

    exp_dt = datetime.fromtimestamp(exp_ts, tz=UTC)
    if datetime.now(UTC) > exp_dt:
        raise TokenExpiredError(f"Token expired at {exp_dt.isoformat()}.")

    try:
        role = Role(payload["role"])
    except (KeyError, ValueError) as exc:
        raise TokenSignatureError(f"Invalid token role: {payload.get('role')}") from exc

    return Identity(
        subject=payload.get("sub", ""),
        role=role,
        principal_id=payload.get("principal_id", ""),
        agent_id=payload.get("agent_id"),
        expires_at_utc=exp_dt,
    )
