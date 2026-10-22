"""Unit tests for Ed25519-signed mandates, RFC 8785 canonicalization, and tamper evidence."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.canonical_json import canonical_json_bytes
from app.domain.mandates import Mandate, MandateStatus
from app.infrastructure.crypto import (
    generate_ed25519_keypair,
    get_key_id,
    sign_bytes,
    sign_payload,
    verify_mandate_seal,
    verify_signature,
)


@pytest.fixture
def test_keypair() -> tuple[bytes, bytes, str]:
    priv, pub = generate_ed25519_keypair()
    key_id = get_key_id(pub)
    return priv, pub, key_id


def test_mandate_ed25519_sign_and_verify_roundtrip(test_keypair: tuple[bytes, bytes, str]) -> None:
    """Item 1 & 3: Round-trip signing and verification of a strict Pydantic mandate."""
    priv, pub, key_id = test_keypair
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    payload: dict[str, Any] = {
        "mandate_id": "mandate_test_01",
        "version": 1,
        "principal_id": "principal_corp",
        "agent_id": "agent_worker_1",
        "single_limit_minor": 100_000,
        "instant_threshold_minor": 10_000,
        "lifetime_budget_minor": 1_000_000,
        "currency": "USD",
        "allowed_payees": ["vendor_a"],
        "allowed_purposes": ["subscription"],
        "valid_from_utc": now.isoformat(),
        "valid_until_utc": (now + timedelta(days=30)).isoformat(),
        "status": MandateStatus.ACTIVE.value,
        "key_id": key_id,
    }
    sig = sign_bytes(priv, canonical_json_bytes(payload))
    mandate = Mandate(
        mandate_id="mandate_test_01",
        version=1,
        principal_id="principal_corp",
        agent_id="agent_worker_1",
        single_limit_minor=100_000,
        instant_threshold_minor=10_000,
        lifetime_budget_minor=1_000_000,
        currency="USD",
        allowed_payees=("vendor_a",),
        allowed_purposes=("subscription",),
        valid_from_utc=now,
        valid_until_utc=now + timedelta(days=30),
        status=MandateStatus.ACTIVE,
        key_id=key_id,
        signature=sig,
    )

    signable_bytes = mandate.signable_bytes()
    assert verify_signature(pub, signable_bytes, mandate.signature) is True
    assert verify_mandate_seal(pub, signable_bytes, mandate.signature, mandate.key_id) is True


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("mandate_id", "forged_id_x"),
        ("version", 2),
        ("principal_id", "principal_hacker"),
        ("agent_id", "rogue_agent_99"),
        ("single_limit_minor", 99_999_999),
        ("instant_threshold_minor", 99_999_999),
        ("lifetime_budget_minor", 999_999_999),
        ("currency", "EUR"),
        ("allowed_payees", ["hacker_wallet"]),
        ("allowed_purposes", ["unrestricted"]),
        ("valid_from_utc", "2026-01-01T00:00:00+00:00"),
        ("valid_until_utc", "2099-12-31T23:59:59+00:00"),
        ("status", MandateStatus.REVOKED.value),
        ("key_id", "key_forged001"),
    ],
)
def test_mandate_any_one_field_tamper_fails(
    test_keypair: tuple[bytes, bytes, str],
    field: str,
    tampered_value: Any,
) -> None:
    """Item 5: Mutating any single field in the signed payload breaks cryptographic integrity."""
    priv, pub, key_id = test_keypair
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    base_payload: dict[str, Any] = {
        "mandate_id": "mandate_base_01",
        "version": 1,
        "principal_id": "principal_corp",
        "agent_id": "agent_worker_1",
        "single_limit_minor": 100_000,
        "instant_threshold_minor": 10_000,
        "lifetime_budget_minor": 1_000_000,
        "currency": "USD",
        "allowed_payees": ["vendor_a"],
        "allowed_purposes": ["subscription"],
        "valid_from_utc": now.isoformat(),
        "valid_until_utc": (now + timedelta(days=30)).isoformat(),
        "status": MandateStatus.ACTIVE.value,
        "key_id": key_id,
    }
    original_sig = sign_bytes(priv, canonical_json_bytes(base_payload))

    tampered_payload = dict(base_payload)
    tampered_payload[field] = tampered_value
    tampered_bytes = canonical_json_bytes(tampered_payload)

    # Verification MUST fail for each mutated field
    assert verify_signature(pub, tampered_bytes, original_sig) is False


def test_mandate_wrong_algorithm_and_malformed_sig_fails(
    test_keypair: tuple[bytes, bytes, str],
) -> None:
    """Item 5: Wrong algorithm, malformed hex, or length mismatch returns False cleanly."""
    _priv, pub, key_id = test_keypair
    msg = b'{"test":"data"}'

    # Malformed non-hex string
    assert verify_signature(pub, msg, "not_a_hex_string") is False
    assert verify_mandate_seal(pub, msg, "not_a_hex_string", key_id) is False

    # Truncated signature (32 bytes = 64 hex chars instead of 64 bytes = 128 hex chars)
    truncated_hex = "a" * 64
    assert verify_signature(pub, msg, truncated_hex) is False

    # Oversized signature (65 bytes = 130 hex chars)
    oversized_hex = "a" * 130
    assert verify_signature(pub, msg, oversized_hex) is False


def test_mandate_wrong_key_id_fails(test_keypair: tuple[bytes, bytes, str]) -> None:
    """Item 5: Valid signature verified against wrong key_id returns False."""
    priv, pub, key_id = test_keypair
    msg = b'{"mandate_id":"m1"}'
    sig_hex, _actual_key_id = sign_payload(priv, msg, key_id)

    # Correct key_id verifies
    assert verify_mandate_seal(pub, msg, sig_hex, key_id) is True

    # Altered key_id MUST fail
    assert verify_mandate_seal(pub, msg, sig_hex, "key_wrong12345") is False


def test_mandate_stripped_signature_fails(test_keypair: tuple[bytes, bytes, str]) -> None:
    """Item 5: Missing or stripped signature string fails verification."""
    _priv, pub, key_id = test_keypair
    msg = b'{"mandate_id":"m1"}'

    assert verify_mandate_seal(pub, msg, "", key_id) is False
    assert verify_signature(pub, msg, "") is False


@given(
    st.dictionaries(
        keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
        values=st.integers(min_value=-1000, max_value=1000) | st.text(max_size=20) | st.booleans(),
        min_size=2,
        max_size=12,
    )
)
def test_canonicalization_stable_across_key_order_hypothesis(d: dict[str, Any]) -> None:
    """Item 5: Hypothesis property test verifying RFC 8785 invariance across key insertion order."""
    keys = list(d.keys())
    # Generate different insertion-order dictionary representations of identical semantic object
    reversed_d = {k: d[k] for k in reversed(keys)}
    sorted_d = {k: d[k] for k in sorted(keys)}

    out_original = canonical_json_bytes(d)
    out_reversed = canonical_json_bytes(reversed_d)
    out_sorted = canonical_json_bytes(sorted_d)

    assert out_original == out_reversed == out_sorted


def test_mandate_temporal_windows_validity(test_keypair: tuple[bytes, bytes, str]) -> None:
    """Item 5: Inactive or outside temporal validity windows evaluated correctly."""
    _priv, _pub, key_id = test_keypair
    t0 = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=30)

    mandate = Mandate(
        mandate_id="mandate_time_01",
        version=1,
        principal_id="principal_corp",
        agent_id="agent_worker_1",
        single_limit_minor=100_000,
        instant_threshold_minor=10_000,
        lifetime_budget_minor=1_000_000,
        currency="USD",
        allowed_payees=(),
        allowed_purposes=(),
        valid_from_utc=t0,
        valid_until_utc=t1,
        status=MandateStatus.ACTIVE,
        key_id=key_id,
        signature="fake_sig",
    )

    # Within valid window
    assert mandate.is_active_at(t0) is True
    assert mandate.is_active_at(t0 + timedelta(days=15)) is True

    # Premature (before valid_from_utc)
    assert mandate.is_active_at(t0 - timedelta(seconds=1)) is False

    # Expired (at or after valid_until_utc)
    assert mandate.is_active_at(t1) is False
    assert mandate.is_active_at(t1 + timedelta(days=1)) is False

    # Inactive status overrides valid window
    revoked = mandate.revoke()
    assert revoked.is_active_at(t0 + timedelta(days=15)) is False


def test_mandate_versioning_supersede_and_revoke(test_keypair: tuple[bytes, bytes, str]) -> None:
    """Item 4 & 5: Versioning produces new immutable versions; old versions superseded."""
    priv, pub, key_id = test_keypair
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    v1_mandate = Mandate(
        mandate_id="mandate_v_01",
        version=1,
        principal_id="principal_corp",
        agent_id="agent_worker_1",
        single_limit_minor=50_000,
        instant_threshold_minor=10_000,
        lifetime_budget_minor=500_000,
        currency="USD",
        allowed_payees=(),
        allowed_purposes=(),
        valid_from_utc=now,
        valid_until_utc=now + timedelta(days=30),
        status=MandateStatus.ACTIVE,
        key_id=key_id,
        signature="sig_v1",
    )

    # Supersede with increased limit for version 2
    superseded_old, active_v2 = v1_mandate.supersede(
        new_version=2,
        key_id=key_id,
        signature="sig_v2",
        single_limit_minor=100_000,
        instant_threshold_minor=20_000,
    )

    assert superseded_old.status == MandateStatus.SUPERSEDED
    assert superseded_old.version == 1
    assert superseded_old.single_limit_minor == 50_000

    assert active_v2.status == MandateStatus.ACTIVE
    assert active_v2.version == 2
    assert active_v2.single_limit_minor == 100_000
    assert active_v2.instant_threshold_minor == 20_000
    assert active_v2.signature == "sig_v2"

    # Attempting to supersede with non-increasing version raises ValueError
    with pytest.raises(ValueError, match="strictly greater"):
        active_v2.supersede(new_version=2, key_id=key_id, signature="bad_sig")

    with pytest.raises(ValueError, match="strictly greater"):
        active_v2.supersede(new_version=1, key_id=key_id, signature="bad_sig")

    # Revocation returns new revoked instance
    revoked_v2 = active_v2.revoke()
    assert revoked_v2.status == MandateStatus.REVOKED
    assert revoked_v2.version == 2
