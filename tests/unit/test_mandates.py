"""Unit tests for Ed25519-signed mandates and tamper evidence."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.canonical_json import canonical_json_bytes
from app.domain.mandates import Mandate, MandateStatus
from app.infrastructure.crypto import (
    generate_ed25519_keypair,
    get_key_id,
    sign_bytes,
    verify_signature,
)


@pytest.fixture
def test_keypair() -> tuple[bytes, bytes, str]:
    priv, pub = generate_ed25519_keypair()
    key_id = get_key_id(pub)
    return priv, pub, key_id


def test_mandate_ed25519_sign_and_verify_roundtrip(test_keypair: tuple[bytes, bytes, str]) -> None:
    priv, pub, key_id = test_keypair
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    payload = {
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

    signable_bytes = canonical_json_bytes(mandate.to_signable_dict())
    assert verify_signature(pub, signable_bytes, mandate.signature) is True


def test_mandate_tampered_payload_fails_verification(
    test_keypair: tuple[bytes, bytes, str],
) -> None:
    priv, pub, key_id = test_keypair
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    payload = {
        "mandate_id": "mandate_test_02",
        "version": 1,
        "principal_id": "principal_corp",
        "agent_id": "agent_worker_1",
        "single_limit_minor": 100_000,
        "instant_threshold_minor": 10_000,
        "lifetime_budget_minor": 1_000_000,
        "currency": "USD",
        "allowed_payees": [],
        "allowed_purposes": [],
        "valid_from_utc": now.isoformat(),
        "valid_until_utc": (now + timedelta(days=30)).isoformat(),
        "status": MandateStatus.ACTIVE.value,
        "key_id": key_id,
    }
    sig = sign_bytes(priv, canonical_json_bytes(payload))

    # An attacker maliciously raises single limit to 10,000,000 minor units
    tampered_dict = dict(payload)
    tampered_dict["single_limit_minor"] = 10_000_000

    # Verification of tampered bytes against original signature MUST fail
    tampered_bytes = canonical_json_bytes(tampered_dict)
    assert verify_signature(pub, tampered_bytes, sig) is False


def test_mandate_wrong_key_fails_verification(test_keypair: tuple[bytes, bytes, str]) -> None:
    priv, _pub, key_id = test_keypair
    _other_priv, other_pub = generate_ed25519_keypair()
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    payload = {
        "mandate_id": "mandate_test_03",
        "version": 1,
        "principal_id": "principal_corp",
        "agent_id": "agent_worker_1",
        "single_limit_minor": 50_000,
        "instant_threshold_minor": 10_000,
        "lifetime_budget_minor": 500_000,
        "currency": "USD",
        "allowed_payees": [],
        "allowed_purposes": [],
        "valid_from_utc": now.isoformat(),
        "valid_until_utc": (now + timedelta(days=30)).isoformat(),
        "status": MandateStatus.ACTIVE.value,
        "key_id": key_id,
    }
    sig = sign_bytes(priv, canonical_json_bytes(payload))
    signable_bytes = canonical_json_bytes(payload)

    # Verification with a different public key MUST fail
    assert verify_signature(other_pub, signable_bytes, sig) is False
