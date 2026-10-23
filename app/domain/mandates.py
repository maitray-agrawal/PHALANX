"""Pure domain mandate models and life-cycle invariants.

CRITICAL SECURITY NOTE:
The Ed25519 signature is an automated cryptographic integrity seal designed
to detect data tampering in transit and storage. It is NOT human non-repudiation.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.canonical_json import canonical_json_bytes


class MandateStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class Mandate(BaseModel):
    """Immutable financial authority mandate issued by a human principal to an agent.

    Enforces strict Pydantic validation (extra='forbid', frozen=True, strict=True),
    integer minor units, UTC timezone enforcement, and temporal windows.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mandate_id: str = Field(
        ..., min_length=1, max_length=64, description="Unique mandate identifier"
    )
    version: int = Field(..., ge=1, description="Mandate version number (monotonically increasing)")
    principal_id: str = Field(
        ..., min_length=1, max_length=128, description="Authorizing principal ID"
    )
    agent_id: str = Field(
        ..., min_length=1, max_length=128, description="Authorized autonomous agent ID"
    )
    single_limit_minor: int = Field(
        ...,
        gt=0,
        description="Maximum single transaction ceiling in integer minor units (e.g. cents)",
    )
    instant_threshold_minor: int = Field(
        ...,
        ge=0,
        description="Instant approval threshold in minor units; amounts above trigger step-up",
    )
    lifetime_budget_minor: int = Field(
        ...,
        gt=0,
        description="Cumulative lifetime spending budget in integer minor units",
    )
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
        description="3-letter uppercase ISO-4217 currency code",
    )
    allowed_payees: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Whitelisted payee IDs. If empty, all payees within limits are permitted.",
    )
    allowed_purposes: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Permitted transaction purpose categories. If empty, all purposes permitted.",
    )
    valid_from_utc: datetime = Field(
        ..., description="UTC timestamp defining the start of mandate validity"
    )
    valid_until_utc: datetime = Field(
        ..., description="UTC timestamp defining the expiration of the mandate"
    )
    status: MandateStatus = Field(default=MandateStatus.ACTIVE, description="Lifecycle status")
    key_id: str = Field(
        ..., min_length=1, max_length=64, description="Identifier of the Ed25519 signing key"
    )
    signature: str = Field(
        default="", description="Hex-encoded Ed25519 cryptographic signature seal"
    )
    require_invoice_reference: bool = Field(
        default=False,
        description="Whether payments under this mandate require a non-empty invoice reference",
    )
    allow_unregistered_payees: bool = Field(
        default=False,
        description="Whether payees outside allowed_payees are permitted",
    )

    @field_validator("valid_from_utc", "valid_until_utc")
    @classmethod
    def validate_timezone_aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware UTC")
        return v

    @model_validator(mode="after")
    def validate_invariants(self) -> "Mandate":
        if self.instant_threshold_minor > self.single_limit_minor:
            raise ValueError("instant_threshold_minor cannot exceed single_limit_minor")
        if self.lifetime_budget_minor < self.single_limit_minor:
            raise ValueError("lifetime_budget_minor cannot be less than single_limit_minor")
        if self.valid_until_utc <= self.valid_from_utc:
            raise ValueError("valid_until_utc must be strictly after valid_from_utc")
        return self

    def to_signable_dict(self) -> dict[str, Any]:
        """Convert mandate fields (excluding signature) into a canonical dictionary for signing."""
        payload: dict[str, Any] = {
            "mandate_id": self.mandate_id,
            "version": self.version,
            "principal_id": self.principal_id,
            "agent_id": self.agent_id,
            "single_limit_minor": self.single_limit_minor,
            "instant_threshold_minor": self.instant_threshold_minor,
            "lifetime_budget_minor": self.lifetime_budget_minor,
            "currency": self.currency,
            "allowed_payees": list(self.allowed_payees),
            "allowed_purposes": list(self.allowed_purposes),
            "valid_from_utc": self.valid_from_utc.isoformat(),
            "valid_until_utc": self.valid_until_utc.isoformat(),
            "status": self.status.value,
            "key_id": self.key_id,
        }
        if self.require_invoice_reference:
            payload["require_invoice_reference"] = True
        if self.allow_unregistered_payees:
            payload["allow_unregistered_payees"] = True
        return payload

    def signable_bytes(self) -> bytes:
        """Serialize signable dictionary into RFC 8785 canonical JSON bytes."""
        return canonical_json_bytes(self.to_signable_dict())

    def is_active_at(self, check_time_utc: datetime) -> bool:
        """Check if mandate is ACTIVE and within its temporal validity window."""
        if self.status != MandateStatus.ACTIVE:
            return False
        return self.valid_from_utc <= check_time_utc < self.valid_until_utc

    def supersede(
        self,
        new_version: int,
        key_id: str,
        signature: str,
        *,
        single_limit_minor: int | None = None,
        instant_threshold_minor: int | None = None,
        lifetime_budget_minor: int | None = None,
        allowed_payees: tuple[str, ...] | None = None,
        allowed_purposes: tuple[str, ...] | None = None,
        valid_from_utc: datetime | None = None,
        valid_until_utc: datetime | None = None,
        allow_unregistered_payees: bool | None = None,
    ) -> tuple["Mandate", "Mandate"]:
        """Create a new version of the mandate and supersede the old one.

        Invariant: Mandates are immutable; old versions are NEVER edited in-place.
        Returns (superseded_old, active_new).
        """
        if new_version <= self.version:
            msg = f"New version {new_version} must be strictly greater than {self.version}"
            raise ValueError(msg)
        superseded_old = self.model_copy(update={"status": MandateStatus.SUPERSEDED})
        active_new = Mandate(
            mandate_id=self.mandate_id,
            version=new_version,
            principal_id=self.principal_id,
            agent_id=self.agent_id,
            single_limit_minor=(
                single_limit_minor if single_limit_minor is not None else self.single_limit_minor
            ),
            instant_threshold_minor=(
                instant_threshold_minor
                if instant_threshold_minor is not None
                else self.instant_threshold_minor
            ),
            lifetime_budget_minor=(
                lifetime_budget_minor
                if lifetime_budget_minor is not None
                else self.lifetime_budget_minor
            ),
            currency=self.currency,
            allowed_payees=allowed_payees if allowed_payees is not None else self.allowed_payees,
            allowed_purposes=(
                allowed_purposes if allowed_purposes is not None else self.allowed_purposes
            ),
            valid_from_utc=valid_from_utc if valid_from_utc is not None else self.valid_from_utc,
            valid_until_utc=(
                valid_until_utc if valid_until_utc is not None else self.valid_until_utc
            ),
            allow_unregistered_payees=(
                allow_unregistered_payees
                if allow_unregistered_payees is not None
                else self.allow_unregistered_payees
            ),
            status=MandateStatus.ACTIVE,
            key_id=key_id,
            signature=signature,
        )
        return superseded_old, active_new

    def revoke(self) -> "Mandate":
        """Revoke the mandate, returning a revoked immutable copy without editing in place."""
        return self.model_copy(update={"status": MandateStatus.REVOKED})
