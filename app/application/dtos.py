"""Data Transfer Objects for Application Layer.

Invariants:
- Strict validation with extra='forbid'.
- Explicit bounds and size limits.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import DecisionOutcome


class AuthorizeTransactionCommand(BaseModel):
    """Command requesting financial transaction authorization."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1, max_length=128)
    recipient_id: str = Field(..., min_length=1, max_length=128)
    amount_minor: int = Field(..., ge=0, description="Amount in integer minor units (e.g. cents)")
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    purpose: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    anomaly_signal: DecisionOutcome | None = Field(
        default=None,
        description="Optional heuristic or model risk assessment. Can only escalate decision.",
    )


class AuthorizationResponseDTO(BaseModel):
    """Response returned upon transaction evaluation."""

    model_config = ConfigDict(extra="forbid")

    decision: DecisionOutcome
    reasons: list[str]
    escalated: bool
    event_id: str
    evaluated_at_utc: datetime


class HealthStatusDTO(BaseModel):
    """Health check response."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    version: str = Field(default="0.1.0")
    timestamp_utc: datetime
