"""Data Transfer Objects for Application Layer.

Invariants:
- Strict validation with extra='forbid'.
- Explicit bounds and size limits.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.mandates import MandateStatus
from app.domain.models import DecisionOutcome
from app.domain.policy import PolicyReasonCode
from app.domain.state_machine import RequestState


class AuthorizeTransactionCommand(BaseModel):
    """Command requesting financial transaction authorization."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1, max_length=128)
    recipient_id: str = Field(..., min_length=1, max_length=128)
    amount_minor: int = Field(..., ge=0, description="Amount in integer minor units (e.g. cents)")
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    purpose: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    invoice_reference: str | None = Field(
        default=None,
        max_length=256,
        description="Optional invoice or billing document reference.",
    )
    anomaly_signal: DecisionOutcome | None = Field(
        default=None,
        description="Optional heuristic or model risk assessment. Can only escalate decision.",
    )


class AuthorizationResponseDTO(BaseModel):
    """Response returned upon transaction evaluation."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    decision: DecisionOutcome
    reasons: list[str]
    reason_codes: list[PolicyReasonCode]
    escalated: bool
    event_id: str
    intent_digest: str
    evaluated_at_utc: datetime
    payout_id: str | None = None
    request_state: RequestState | None = None


class CreateMandateCommand(BaseModel):
    """Command to issue an Ed25519-signed authority mandate."""

    model_config = ConfigDict(extra="forbid")

    mandate_id: str = Field(..., min_length=1, max_length=64)
    principal_id: str = Field(..., min_length=1, max_length=128)
    agent_id: str = Field(..., min_length=1, max_length=128)
    single_limit_minor: int = Field(..., gt=0)
    instant_threshold_minor: int = Field(..., ge=0)
    lifetime_budget_minor: int = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    allowed_payees: list[str] = Field(default_factory=list)
    allowed_purposes: list[str] = Field(default_factory=list)
    valid_days: int = Field(default=90, ge=1, le=365)
    allow_unregistered_payees: bool = Field(default=False)


class MandateResponseDTO(BaseModel):
    """Public mandate data structure."""

    model_config = ConfigDict(extra="forbid")

    mandate_id: str
    version: int
    principal_id: str
    agent_id: str
    single_limit_minor: int
    instant_threshold_minor: int
    lifetime_budget_minor: int
    currency: str
    allowed_payees: list[str]
    allowed_purposes: list[str]
    valid_from_utc: datetime
    valid_until_utc: datetime
    status: MandateStatus
    key_id: str
    signature: str
    allow_unregistered_payees: bool = Field(default=False)
    spent_budget_minor: int = Field(default=0)
    remaining_budget_minor: int = Field(default=0)


class PendingStepUpDTO(BaseModel):
    """Pending human review item in step-up queue."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    agent_id: str
    recipient_id: str
    amount_minor: int
    currency: str
    purpose: str
    intent_digest: str
    created_at_utc: datetime
    status: str = Field(default="PENDING")


class ExtractedIntentDTO(BaseModel):
    """Extracted structured transaction intent draft."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    recipient_id: str
    amount_minor: int
    currency: str
    purpose: str
    idempotency_key: str
    anomaly_signal: str | None = None


class AssistantChatRequestDTO(BaseModel):
    """Natural language agent message to be processed."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=2000)
    agent_id: str = Field(default="agent-auto-1")
    session_id: str = Field(default="session-demo-01")


class AssistantChatResponseDTO(BaseModel):
    """Assistant response with optional extracted intent draft."""

    model_config = ConfigDict(extra="forbid")

    reply: str
    intent: ExtractedIntentDTO | None = None
    heuristic_flagged: bool = False
    heuristic_reason: str | None = None


class ApprovalCommand(BaseModel):
    """Human supervisor step-up authorization command."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., min_length=1)
    expected_digest: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 digest of the canonical intent. Must match to prevent tampering.",
    )
    decision: DecisionOutcome = Field(..., description="ALLOW or DENY")
    reason: str = Field(..., min_length=1, max_length=500)


class LedgerEventDTO(BaseModel):
    """Public audit log event view."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    prev_hash: str
    event_hash: str
    payload: dict[str, object]


class LedgerVerificationDTO(BaseModel):
    """Integrity status of the cryptographic hash chain."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    message: str
    broken_index: int | None
    total_events: int


class HealthStatusDTO(BaseModel):
    """Health check response."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    version: str = Field(default="0.1.0")
    timestamp_utc: datetime


class DemoTokenRequestDTO(BaseModel):
    """Request to generate a signed role token in demo mode."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(default="principal", description="principal, agent, approver, or auditor")
    principal_id: str = Field(default="demo-principal", min_length=1, max_length=128)
    agent_id: str | None = Field(default=None, max_length=128)


class DemoTokenResponseDTO(BaseModel):
    """Signed role token response."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in_seconds: int
