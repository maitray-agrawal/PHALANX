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
    """Verify that when MANDATE_SIGNING_KEY_HEX is unset,
    keypair derives deterministically from SECRET_KEY.
    """
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


# ---------------------------------------------------------------------------
# Task 3: Regression Tests for Ed25519 Signing Key Loading & Validation
# ---------------------------------------------------------------------------

VALID_64_HEX_KEY = "4" * 64


def test_valid_64_character_hex_key_loads_correctly():
    """1. A valid 64-character hexadecimal key loads correctly."""
    priv, pub, key_id = load_or_generate_keypair(key_hex=VALID_64_HEX_KEY)
    assert len(priv) == 32
    assert len(pub) == 32
    assert priv == bytes.fromhex(VALID_64_HEX_KEY)
    assert key_id.startswith("key_")


def test_invalid_hex_character_rejected():
    """2. An invalid hexadecimal character is rejected."""
    # Contains 'g' which is non-hex
    invalid_hex = "4" * 63 + "g"
    with pytest.raises(
        ValueError, match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."
    ):
        load_or_generate_keypair(key_hex=invalid_hex)


def test_odd_length_key_rejected():
    """3. An odd-length key is rejected."""
    odd_key_65 = "a" * 65
    with pytest.raises(
        ValueError, match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."
    ):
        load_or_generate_keypair(key_hex=odd_key_65)

    odd_key_63 = "b" * 63
    with pytest.raises(
        ValueError, match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."
    ):
        load_or_generate_keypair(key_hex=odd_key_63)


def test_wrong_length_keys_rejected():
    """4. A key with the wrong length is rejected (quotes, whitespace, prefix, or wrong size)."""
    # 0x prefix + 64 hex = 66 chars
    with pytest.raises(
        ValueError, match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."
    ):
        load_or_generate_keypair(key_hex="0x" + "c" * 64)

    # Quoted string
    with pytest.raises(
        ValueError, match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."
    ):
        load_or_generate_keypair(key_hex=f'"{VALID_64_HEX_KEY}"')

    # Trailing whitespace or newline
    with pytest.raises(
        ValueError, match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."
    ):
        load_or_generate_keypair(key_hex=VALID_64_HEX_KEY + "\n")

    # 32 characters (16 bytes, half length)
    with pytest.raises(
        ValueError, match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."
    ):
        load_or_generate_keypair(key_hex="d" * 32)


def test_empty_or_missing_production_config_fails_safely():
    """5. Empty or missing production configuration fails safely."""
    empty_settings = Settings(secret_key="", mandate_signing_key_hex="", environment="production")
    with (
        patch("app.infrastructure.crypto.settings", empty_settings),
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        pytest.raises(ValueError, match="ephemeral key fallback is prohibited"),
    ):
        load_or_generate_keypair(key_hex="", key_file_path="")


def test_error_messages_do_not_reveal_secret_values():
    """6. Error messages do not reveal secret values."""
    canary_secret = "secret_canary_super_confidential_token_12345678901234567890"
    with pytest.raises(ValueError) as exc_info:
        load_or_generate_keypair(key_hex=canary_secret)

    err_text = str(exc_info.value)
    assert canary_secret not in err_text
    assert "secret_canary" not in err_text
    assert err_text == "MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters."


def test_existing_key_identity_remains_stable_across_repeated_boots():
    """7. Existing key identity remains stable across repeated boot executions."""
    # Hex keypair loading stability
    priv_a, pub_a, kid_a = load_or_generate_keypair(key_hex=VALID_64_HEX_KEY)
    priv_b, pub_b, kid_b = load_or_generate_keypair(key_hex=VALID_64_HEX_KEY)
    assert priv_a == priv_b
    assert pub_a == pub_b
    assert kid_a == kid_b

    # HKDF derived keypair stability
    test_settings = Settings(
        secret_key="production-stable-master-secret-key-32b",
        mandate_signing_key_hex="",
        environment="production",
    )
    with (
        patch("app.infrastructure.crypto.settings", test_settings),
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
    ):
        priv_1, pub_1, kid_1 = load_or_generate_keypair()
        priv_2, pub_2, kid_2 = load_or_generate_keypair()
        assert priv_1 == priv_2
        assert pub_1 == pub_2
        assert kid_1 == kid_2


def test_invalid_production_key_never_generates_replacement_key():
    """8. Invalid production key configuration never silently generates a replacement key."""
    # Even if SECRET_KEY is valid, an invalid MANDATE_SIGNING_KEY_HEX must fail closed,
    # never silently falling back to SECRET_KEY derivation or ephemeral generation.
    test_settings = Settings(
        secret_key="production-stable-master-secret-key-32b",
        mandate_signing_key_hex="invalid_hex_string_position_65" + "0" * 35,
        environment="production",
    )
    with (
        patch("app.infrastructure.crypto.settings", test_settings),
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        pytest.raises(
            ValueError,
            match="MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters.",
        ),
    ):
        load_or_generate_keypair(key_hex=test_settings.mandate_signing_key_hex)
