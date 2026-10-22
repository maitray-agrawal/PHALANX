"""Ed25519 cryptographic sealing and signature verification.

Uses cryptography.hazmat primitives (RFC 8032 Ed25519).
Signatures are hex-encoded.
"""

import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Generate a raw 32-byte private seed and 32-byte public key."""
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes_raw()
    public_raw = private_key.public_key().public_bytes_raw()
    return private_raw, public_raw


def get_key_id(public_bytes: bytes) -> str:
    """Generate deterministic key ID prefix from public key hash."""
    return f"key_{hashlib.sha256(public_bytes).hexdigest()[:12]}"


def sign_bytes(private_bytes: bytes, message: bytes) -> str:
    """Sign payload with Ed25519 private key and return hex signature."""
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    sig = private_key.sign(message)
    return sig.hex()


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
