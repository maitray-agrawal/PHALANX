"""Unit tests for GroundedExplanationValidator:
preventing hallucinated amounts, payees, and decisions.
"""

from datetime import UTC, datetime

import pytest

from app.application.dtos import AuthorizationResponseDTO
from app.application.grounding import GroundedExplanationValidator
from app.domain.models import DecisionOutcome
from app.domain.policy import PolicyReasonCode


@pytest.fixture
def allow_record() -> AuthorizationResponseDTO:
    return AuthorizationResponseDTO(
        request_id="req_valid_001",
        decision=DecisionOutcome.ALLOW,
        reasons=["Amount within pre-authorized autonomous limits"],
        reason_codes=[PolicyReasonCode.PRE_AUTHORIZED],
        escalated=False,
        event_id="evt_001",
        intent_digest="digest123",
        evaluated_at_utc=datetime.now(UTC),
        payout_id="sandbox_tx_999",
    )


@pytest.fixture
def deny_record() -> AuthorizationResponseDTO:
    return AuthorizationResponseDTO(
        request_id="req_denied_002",
        decision=DecisionOutcome.DENY,
        reasons=["Amount 60000 exceeds single limit 50000"],
        reason_codes=[PolicyReasonCode.SINGLE_LIMIT_EXCEEDED],
        escalated=False,
        event_id="evt_002",
        intent_digest="digest456",
        evaluated_at_utc=datetime.now(UTC),
        payout_id=None,
    )


def test_grounded_validator_accepts_valid_paraphrase(
    allow_record: AuthorizationResponseDTO,
) -> None:
    validator = GroundedExplanationValidator()
    candidate = (
        "Your request req_valid_001 was evaluated with decision ALLOW. "
        "The $25.00 transfer (2500 minor units) to recipient vendor-paypal-sandbox-1 "
        "is pre-authorized and dispatched."
    )

    valid, text = validator.validate_and_ground(
        candidate,
        allow_record,
        expected_recipient_id="vendor-paypal-sandbox-1",
        expected_amount_minor=2500,
    )

    assert valid is True
    assert text == candidate


def test_grounded_validator_rejects_hallucinated_amount(
    allow_record: AuthorizationResponseDTO,
) -> None:
    """Prompt requirement: model returns a wrong amount and the validator rejects it."""
    validator = GroundedExplanationValidator()
    # Candidate LLM explanation hallucinated an amount of $9999.00 / 999900 cents
    candidate = (
        "Your request req_valid_001 was approved with decision ALLOW. "
        "We sent $9999.00 to vendor-paypal-sandbox-1."
    )

    valid, fallback = validator.validate_and_ground(
        candidate,
        allow_record,
        expected_recipient_id="vendor-paypal-sandbox-1",
        expected_amount_minor=2500,
    )

    assert valid is False
    # Templated deterministic explanation returned
    assert "Decision: ALLOW for request req_valid_001" in fallback
    assert "USD 25.00 to payee 'vendor-paypal-sandbox-1'" in fallback
    assert "PRE_AUTHORIZED" in fallback


def test_grounded_validator_rejects_hallucinated_payee(
    allow_record: AuthorizationResponseDTO,
) -> None:
    validator = GroundedExplanationValidator()
    # Candidate mentions unknown payee
    candidate = (
        "Your request req_valid_001 was approved with decision ALLOW. "
        "The $25.00 transfer was sent to recipient rogue-attacker-wallet."
    )

    valid, fallback = validator.validate_and_ground(
        candidate,
        allow_record,
        expected_recipient_id="vendor-paypal-sandbox-1",
        expected_amount_minor=2500,
    )

    assert valid is False
    assert "payee 'vendor-paypal-sandbox-1'" in fallback


def test_grounded_validator_rejects_contradictory_outcome(
    deny_record: AuthorizationResponseDTO,
) -> None:
    validator = GroundedExplanationValidator()
    # Record is DENY, but LLM hallucinates that decision was ALLOW
    candidate = (
        "Great news! Your request req_denied_002 received decision ALLOW. "
        "Amount 60000 was approved."
    )

    valid, fallback = validator.validate_and_ground(
        candidate, deny_record, expected_recipient_id="vendor-1", expected_amount_minor=60000
    )

    assert valid is False
    assert "Decision: DENY" in fallback
    assert "SINGLE_LIMIT_EXCEEDED" in fallback


def test_grounded_validator_rejects_missing_request_id(
    allow_record: AuthorizationResponseDTO,
) -> None:
    validator = GroundedExplanationValidator()
    candidate = "Payment was evaluated with decision ALLOW for $25.00 to vendor-paypal-sandbox-1."

    valid, fallback = validator.validate_and_ground(
        candidate,
        allow_record,
        expected_recipient_id="vendor-paypal-sandbox-1",
        expected_amount_minor=2500,
    )

    assert valid is False
    assert "req_valid_001" in fallback
