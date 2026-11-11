"""Ed25519 cryptographic sealing and signature verification.

Uses standard cryptography.hazmat primitives (RFC 8032 Ed25519).
Private key material is never logged or exposed.
Signatures are hex-encoded.

CRITICAL SECURITY STATEMENT:
The Ed25519 signature is an automated cryptographic integrity seal asserting that
a mandate's limits, payees, and validity windows have not been tampered with in storage
or transit. It does NOT represent human legal non-repudiation.
"""

import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.infrastructure.config import settings


def derive_key(secret_key: str | bytes, label: str, length: int = 32) -> bytes:
    """Derive a cryptographically independent key from SECRET_KEY using HKDF-SHA256."""
    ikm = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=label.encode("utf-8"),
    )
    return hkdf.derive(ikm)


def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Generate a raw 32-byte private seed and 32-byte public key."""
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes_raw()
    public_raw = private_key.public_key().public_bytes_raw()
    return private_raw, public_raw


def get_key_id(public_bytes: bytes) -> str:
    """Generate deterministic key ID prefix from public key SHA-256 hash."""
    return f"key_{hashlib.sha256(public_bytes).hexdigest()[:12]}"


HEX_CHARACTERS = frozenset("0123456789abcdefABCDEF")


def validate_mandate_signing_key_hex(key_hex: str) -> None:
    """Strictly validate Ed25519 private signing key hex string.

    Requirements:
    - Exactly 64 hexadecimal characters (representing a 32-byte raw seed).
    - No 0x prefix.
    - No quotes or delimiters.
    - No whitespace or newline characters.

    Never prints or logs the key material or partial values.
    """
    if (
        not isinstance(key_hex, str)
        or len(key_hex) != 64
        or not all(c in HEX_CHARACTERS for c in key_hex)
    ):
        raise ValueError("MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters.")


def load_or_generate_keypair(
    key_hex: str | None = None,
    key_file_path: str | None = None,
) -> tuple[bytes, bytes, str]:
    """Load Ed25519 signing keypair from hex string or file path, or generate ephemeral.

    Private key material is never printed, logged, or included in error traces.
    Returns (private_raw_bytes, public_raw_bytes, key_id).
    """
    if key_hex is not None and key_hex != "":
        validate_mandate_signing_key_hex(key_hex)
        priv_bytes = bytes.fromhex(key_hex)
        priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
        pub_bytes = priv_key.public_key().public_bytes_raw()
        return priv_bytes, pub_bytes, get_key_id(pub_bytes)

    if key_file_path and key_file_path.strip():
        path = Path(key_file_path.strip())
        if path.is_file():
            try:
                raw_data = path.read_bytes()
                if b"BEGIN" in raw_data:
                    from cryptography.hazmat.primitives import serialization

                    loaded_key = serialization.load_pem_private_key(raw_data, password=None)
                    if not isinstance(loaded_key, Ed25519PrivateKey):
                        raise ValueError("PEM file must contain an Ed25519 private key")
                    priv_key = loaded_key
                    priv_bytes = loaded_key.private_bytes_raw()
                else:
                    content = raw_data.decode("utf-8").strip()
                    priv_bytes = bytes.fromhex(content)
                    if len(priv_bytes) != 32:
                        raise ValueError("Key file content must be 32 bytes hex")
                    priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
                pub_bytes = priv_key.public_key().public_bytes_raw()
                return priv_bytes, pub_bytes, get_key_id(pub_bytes)
            except Exception as e:
                raise ValueError("Failed to load Ed25519 private key from file") from e

    # If no explicit key provided, derive deterministic seed from secret_key to preserve
    # cross-process and cross-restart consistency within the deployment environment
    secret_key = getattr(settings, "secret_key", None)
    if secret_key and secret_key.strip():
        seed = derive_key(secret_key.strip(), "phalanx-mandate-ed25519", 32)
        priv_key = Ed25519PrivateKey.from_private_bytes(seed)
        pub_bytes = priv_key.public_key().public_bytes_raw()
        return seed, pub_bytes, get_key_id(pub_bytes)

    # Outside test, ephemeral fallback is strictly forbidden
    env = getattr(settings, "environment", "")
    if env != "test" and os.getenv("ENVIRONMENT") != "test":
        raise ValueError(
            "MANDATE_SIGNING_KEY_HEX or SECRET_KEY is mandatory outside test environment; "
            "ephemeral key fallback is prohibited"
        )

    # Default to ephemeral keypair for test harness only
    priv_raw, pub_raw = generate_ed25519_keypair()
    return priv_raw, pub_raw, get_key_id(pub_raw)


def sign_bytes(private_bytes: bytes, message: bytes) -> str:
    """Sign payload with Ed25519 private key and return hex signature."""
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    sig = private_key.sign(message)
    return sig.hex()


def sign_payload(
    private_bytes: bytes,
    message: bytes,
    expected_key_id: str | None = None,
) -> tuple[str, str]:
    """Sign message bytes and return (signature_hex, key_id).

    Every signature is cryptographically paired with its verifying key_id.
    """
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    pub_bytes = private_key.public_key().public_bytes_raw()
    key_id = expected_key_id or get_key_id(pub_bytes)
    sig_hex = private_key.sign(message).hex()
    return sig_hex, key_id


def verify_signature(public_bytes: bytes, message: bytes, signature_hex: str) -> bool:
    """Verify Ed25519 signature over message bytes.

    Returns False on invalid signature, malformed hex, or length mismatch.
    """
    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        sig = bytes.fromhex(signature_hex)
        public_key.verify(sig, message)
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_mandate_seal(
    public_bytes: bytes,
    message: bytes,
    signature_hex: str,
    key_id: str,
) -> bool:
    """Verify mandate signature seal and confirm key_id binding."""
    if not signature_hex or not key_id:
        return False
    if get_key_id(public_bytes) != key_id:
        return False
    return verify_signature(public_bytes, message, signature_hex)
