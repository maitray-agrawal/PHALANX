"""Unit tests for HKDF key derivation, mandate seals, and restart determinism."""

import os
from unittest.mock import patch

import pytest

from app.infrastructure.config import Settings
from app.infrastructure.crypto import (
    derive_key,
    load_or_generate_keypair,
    sign_payload,
    verify_mandate_seal,
)


def test_derived_keys_differ():
    """Verify that HKDF derivation with distinct labels yields distinct keys."""
    secret = "super-secret-master-key-phalanx-secure-seed-12345"
    token_key = derive_key(secret, "phalanx-token-hmac", 32)
    mandate_key = derive_key(secret, "phalanx-mandate-ed25519", 32)

    assert len(token_key) == 32
    assert len(mandate_key) == 32
    assert token_key != mandate_key, "Token HMAC key and Mandate Ed25519 seed must differ"


def test_key_verification_survives_restart():
    """Verify that restart (reloading keypair with same secret_key) verifies previous signatures."""
    secret = "consistent-across-container-restarts-phalanx-2026"
    test_settings = Settings(secret_key=secret, environment="production")

    # Instance 1: Generate keypair and sign payload
    with patch("app.infrastructure.crypto.settings", test_settings):
        priv_1, pub_1, key_id_1 = load_or_generate_keypair()
        message = b'{"mandate_id":"test-1","single_limit_minor":5000}'
        sig, signed_key_id = sign_payload(priv_1, message)
        assert signed_key_id == key_id_1

    # Instance 2: Simulate restart with same SECRET_KEY
    with patch("app.infrastructure.crypto.settings", test_settings):
        priv_2, pub_2, key_id_2 = load_or_generate_keypair()
        assert priv_1 == priv_2
        assert pub_1 == pub_2
        assert key_id_1 == key_id_2

        # Verification succeeds with reloaded public key
        assert verify_mandate_seal(pub_2, message, sig, key_id_2) is True


def test_ephemeral_fallback_prohibited_outside_test():
    """Verify that outside test, missing secret raises ValueError."""
    empty_settings = Settings(secret_key="", mandate_signing_key_hex="", environment="production")
    with (
        patch("app.infrastructure.crypto.settings", empty_settings),
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        pytest.raises(ValueError, match="ephemeral key fallback is prohibited"),
    ):
        load_or_generate_keypair()


def test_mandate_signing_key_optional_with_secret_key():
    """Verify that when MANDATE_SIGNING_KEY_HEX is unset, keypair derives deterministically from SECRET_KEY."""
    test_settings = Settings(
        secret_key="master-secret-key-at-least-32-chars-long!",
        mandate_signing_key_hex="",
        environment="production",
    )
    with (
        patch("app.infrastructure.crypto.settings", test_settings),
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
    ):
        priv, pub, key_id = load_or_generate_keypair()
        assert len(priv) == 32
        assert len(pub) == 32
        assert key_id.startswith("key_")
