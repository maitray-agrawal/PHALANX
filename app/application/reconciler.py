"""Application service for asynchronous and scheduled reconciliation of ambiguous payment requests.

Invariants:
- Completed external settlement settles the reservation.
- Confirmed external failure/denial/expiry releases the reservation.
- Still pending external state keeps reservation held.
- Age past RECONCILE_MAX_AGE transitions request to NEEDS_REVIEW, preserving held budget.
- Never auto-release on a timeout.
- Exponential backoff per request: base_backoff * (2 ** attempts) up to max_backoff.
- Idempotent: re-reconciling a settled or released request does not alter balances or error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.application.services import AuthorizationService
from app.domain.ports import ClockPort, PaymentRail
from app.domain.state_machine import RequestState

logger = logging.getLogger("phalanx.reconciler")


@dataclass
class AttemptTracker:
    """Tracks backoff attempts for an in-flight ambiguous transaction."""

    attempts: int = 0
    last_attempt_at: datetime | None = None


class ReconcilerService:
    """Manages reconciliation lifecycle, backoff scheduling, and timeout review transitions."""

    def __init__(
        self,
        auth_service: AuthorizationService,
        payment_rail: PaymentRail,
        clock: ClockPort,
        db_session_factory: sessionmaker[Session] | None = None,
        max_age_seconds: int = 86400,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,
    ) -> None:
        self._auth_service = auth_service
        self._payment_rail = payment_rail
        self._clock = clock
        self._db_session_factory = db_session_factory
        self._max_age_seconds = max_age_seconds
        self._base_backoff_seconds = base_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._trackers: dict[str, AttemptTracker] = {}

    def should_retry(self, request_id: str, now: datetime) -> bool:
        """Return True if backoff window for this request has elapsed."""
        tracker = self._trackers.get(request_id)
        if not tracker or tracker.last_attempt_at is None:
            return True
        backoff = min(
            self._max_backoff_seconds,
            self._base_backoff_seconds * (2**tracker.attempts),
        )
        return bool((now - tracker.last_attempt_at).total_seconds() >= backoff)

    def record_attempt(self, request_id: str, now: datetime) -> None:
        """Record an attempt tick and increment attempt counter."""
        tracker = self._trackers.setdefault(request_id, AttemptTracker())
        tracker.attempts += 1
        tracker.last_attempt_at = now

    def clear_tracker(self, request_id: str) -> None:
        """Clear backoff tracker once terminal outcome is reached."""
        self._trackers.pop(request_id, None)

    def reconcile_single(
        self,
        request_id: str,
        force: bool = False,
        rail_status: str | None = None,
    ) -> RequestState:
        """Reconcile a single ambiguous request with backoff guard and timeout review."""
        now = self._clock.now_utc()
        current_state = self._auth_service.get_request_state(request_id)
        if current_state in (RequestState.SETTLED, RequestState.FAILED, RequestState.CLOSED):
            self.clear_tracker(request_id)
            return current_state

        if not force and not self.should_retry(request_id, now):
            return current_state or RequestState.RECONCILE

        self.record_attempt(request_id, now)

        new_state = self._auth_service.reconcile(
            request_id=request_id,
            rail_status=rail_status,
            max_age_seconds=self._max_age_seconds,
        )

        if new_state in (RequestState.SETTLED, RequestState.FAILED, RequestState.CLOSED):
            self.clear_tracker(request_id)

        return new_state

    def reconcile_all(self, force: bool = False) -> dict[str, Any]:
        """Iterate all held ambiguous requests and reconcile against payment rail."""
        held_items = self._auth_service.get_held_reservations()
        metrics = {
            "total_checked": len(held_items),
            "settled": 0,
            "released": 0,
            "pending": 0,
            "needs_review": 0,
        }

        for item in held_items:
            req_id = item["request_id"]
            state = self.reconcile_single(req_id, force=force)
            if state == RequestState.SETTLED:
                metrics["settled"] += 1
            elif state == RequestState.FAILED:
                metrics["released"] += 1
            elif state == RequestState.NEEDS_REVIEW:
                metrics["needs_review"] += 1
            else:
                metrics["pending"] += 1

        return metrics

    def reconcile_by_transaction_id(
        self,
        transaction_id: str,
        rail_status: str | None = None,
        force: bool = True,
    ) -> RequestState | None:
        """Find held request matching external transaction ID and trigger reconciliation."""
        held_items = self._auth_service.get_held_reservations()
        for item in held_items:
            if item.get("payout_id") == transaction_id:
                return self.reconcile_single(
                    item["request_id"], force=force, rail_status=rail_status
                )

        # Check in-memory held reservations dictionary
        for req_id, data in self._auth_service._held_reservations.items():
            if data.get("payout_id") == transaction_id or transaction_id in str(
                data.get("payout_id", "")
            ):
                return self.reconcile_single(req_id, force=force, rail_status=rail_status)

        return None
