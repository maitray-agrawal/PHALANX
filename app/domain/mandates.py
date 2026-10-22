"""Pure domain mandate models and life-cycle invariants."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.domain.canonical_json import canonical_json_bytes


class MandateStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class Mandate:
    """Immutable financial authority mandate issued by a human principal to an agent."""

    mandate_id: str
    version: int
    principal_id: str
    agent_id: str
    single_limit_minor: int
    instant_threshold_minor: int
    lifetime_budget_minor: int
    currency: str
    allowed_payees: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    valid_from_utc: datetime
    valid_until_utc: datetime
    status: MandateStatus
    key_id: str
    signature: str

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError(f"Mandate version must be >= 1, got {self.version}")
        if self.single_limit_minor <= 0:
            raise ValueError("single_limit_minor must be positive")
        if self.instant_threshold_minor < 0:
            raise ValueError("instant_threshold_minor cannot be negative")
        if self.instant_threshold_minor > self.single_limit_minor:
            raise ValueError("instant_threshold_minor cannot exceed single_limit_minor")
        if self.lifetime_budget_minor < self.single_limit_minor:
            raise ValueError("lifetime_budget_minor cannot be less than single_limit_minor")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be 3-letter uppercase ISO code")
        if self.valid_from_utc.tzinfo is None or self.valid_until_utc.tzinfo is None:
            raise ValueError("valid_from_utc and valid_until_utc must be timezone-aware UTC")
        if self.valid_until_utc <= self.valid_from_utc:
            raise ValueError("valid_until_utc must be strictly after valid_from_utc")

    def to_signable_dict(self) -> dict[str, object]:
        """Convert mandate fields (excluding signature) into canonical dictionary for signing."""
        return {
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

    def signable_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_signable_dict())
