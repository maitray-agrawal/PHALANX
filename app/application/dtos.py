"""Data Transfer Objects for Application Layer.

Invariants:
- Strict validation with extra='forbid'.
- Explicit bounds and size limits.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.mandates import MandateStatus
from app.domain.models import DecisionOutcome
from app.domain.policy import PolicyReasonCode
from app.domain.state_machine import RequestState


class AuthorizeTransactionCommand(BaseModel):
    """Command requesting financial transaction authorization."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1, max_length=128)
    recipient_id: str = Field(..., min_length=1, max_length=128)
    amount_minor: int = Field(
        ...,
        ge=0,
        strict=True,
        description="Amount in integer minor units (e.g. cents)",
    )
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    purpose: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    invoice_reference: str | None = Field(
        default=None,
        max_length=256,
        description="Optional invoice or billing document reference.",
    )
    payee: str | None = Field(
        default=None,
        max_length=256,
        description="Optional supplier or vendor name from invoice for binding check.",
    )
    anomaly_signal: DecisionOutcome | None = Field(
        default=None,
        description="Optional heuristic or model risk assessment. Can only escalate decision.",
    )

    @field_validator("invoice_reference", mode="before")
    @classmethod
    def validate_invoice_ref(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else None
        return str(v)


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
    require_invoice_reference: bool = Field(default=False)
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


class SubmitApprovalRequestDTO(BaseModel):
    """Payload for human supervisor step-up authorization endpoint."""

    model_config = ConfigDict(extra="forbid")

    expected_digest: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 digest of the canonical intent. Must match to prevent tampering.",
    )
    decision: DecisionOutcome = Field(..., description="ALLOW or DENY")
    reason: str = Field(default="Human supervisor review", max_length=500)


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


class OverviewResponseDTO(BaseModel):
    """Cockpit high-level operational overview metrics (three values only)."""

    model_config = ConfigDict(extra="forbid")

    remaining_authority: int = Field(
        ...,
        description="Remaining lifetime authorization budget in minor units (e.g. cents).",
    )
    pending_approval_count: int = Field(
        ...,
        description="Count of transactions currently pending human supervisor step-up review.",
    )
    last_activity: str | None = Field(
        default=None,
        description="ISO-8601 UTC timestamp of the most recent ledger activity, or None.",
    )


class ActivityItemDTO(BaseModel):
    """Single transaction item in the paginated activity feed."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    decision: str
    amount: int = Field(..., description="Transaction amount in integer minor units.")
    payee: str = Field(..., description="Recipient identifier.")
    reason_code: str = Field(..., description="Primary policy reason code.")
    provider_state: str = Field(..., description="Real payment provider execution state.")
    timestamp_utc: str | None = Field(default=None, description="ISO-8601 timestamp.")


class PaginatedActivityResponseDTO(BaseModel):
    """Paginated ledger activity feed response."""

    model_config = ConfigDict(extra="forbid")

    items: list[ActivityItemDTO]
    next_cursor: str | None = None
    has_more: bool = False


class HashChainProofDTO(BaseModel):
    """Cryptographic linkage proof for a specific ledger sequence block."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_seq: int
    prev_hash: str
    event_hash: str
    canonical_payload_hash: str
    is_valid: bool


class ReceiptResponseDTO(BaseModel):
    """Detailed transaction receipt containing cryptographic governance proofs."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    intent_digest: str
    mandate_id: str
    mandate_version: int
    decision: str
    reason_codes: list[str]
    ledger_sequence: int
    hash_chain_proof: HashChainProofDTO
    amount_minor: int
    currency: str
    payee: str
    created_at_utc: str


class ReceiptVerificationResponseDTO(BaseModel):
    """Public verification outcome for a transaction receipt."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="PASS or FAIL")
    is_valid: bool
    receipt_id: str
    decision: str
    ledger_sequence: int
    event_hash: str
    broken_block: int | None = None
    message: str


class AttackLabItemDTO(BaseModel):
    """Outcome of an individual canned adversarial attack."""

    model_config = ConfigDict(extra="forbid")

    attack_name: str
    target: str
    blocked: bool
    decision: str
    reason_code: str
    description: str
    reached_paypal: bool = False


class AttackLabResponseDTO(BaseModel):
    """Summary response of all executed canned attack vectors."""

    model_config = ConfigDict(extra="forbid")

    attacks_run: int
    all_defended: bool
    results: list[AttackLabItemDTO]
