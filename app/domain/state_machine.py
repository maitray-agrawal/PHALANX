"""Pure domain request lifecycle state machine (Production Gate 56.17).

Defines explicit states from RECEIVED to CLOSED and rigorously validates allowable transitions.
Zero I/O, no clock, no randomness.
"""

from enum import Enum


class RequestState(str, Enum):
    """Explicit lifecycle states for financial payment requests."""

    RECEIVED = "RECEIVED"
    EVALUATING = "EVALUATING"
    AUTHORIZED = "AUTHORIZED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DENIED = "DENIED"
    EXECUTING = "EXECUTING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    VOIDED = "VOIDED"
    CLOSED = "CLOSED"

    @property
    def is_terminal(self) -> bool:
        """CLOSED is the terminal state with no outgoing transitions."""
        return self == RequestState.CLOSED


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""

    def __init__(
        self,
        current_state: RequestState,
        target_state: RequestState,
        reason: str = "",
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason
        msg = f"Invalid request lifecycle transition: {current_state.value} -> {target_state.value}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


# Explicit allowable state transitions graph
_ALLOWABLE_TRANSITIONS: dict[RequestState, frozenset[RequestState]] = {
    RequestState.RECEIVED: frozenset(
        {
            RequestState.EVALUATING,
            RequestState.CLOSED,  # Boundary rejection
        }
    ),
    RequestState.EVALUATING: frozenset(
        {
            RequestState.AUTHORIZED,  # Pre-authorized ALLOW
            RequestState.PENDING_APPROVAL,  # Requires STEP_UP
            RequestState.DENIED,  # Hard DENY
        }
    ),
    RequestState.PENDING_APPROVAL: frozenset(
        {
            RequestState.APPROVED,  # Human supervisor approved
            RequestState.REJECTED,  # Human supervisor rejected
            RequestState.VOIDED,  # Approval window expired / cancelled
        }
    ),
    RequestState.APPROVED: frozenset(
        {
            RequestState.AUTHORIZED,  # Ready for payment rail dispatch
        }
    ),
    RequestState.AUTHORIZED: frozenset(
        {
            RequestState.EXECUTING,  # Dispatched to payment rail
            RequestState.VOIDED,  # Pre-execution revocation
        }
    ),
    RequestState.EXECUTING: frozenset(
        {
            RequestState.SETTLED,  # Payment captured/completed
            RequestState.FAILED,  # Payment rail rejected/failed
        }
    ),
    RequestState.SETTLED: frozenset(
        {
            RequestState.CLOSED,
        }
    ),
    RequestState.REJECTED: frozenset(
        {
            RequestState.CLOSED,
        }
    ),
    RequestState.DENIED: frozenset(
        {
            RequestState.CLOSED,
        }
    ),
    RequestState.FAILED: frozenset(
        {
            RequestState.CLOSED,
        }
    ),
    RequestState.VOIDED: frozenset(
        {
            RequestState.CLOSED,
        }
    ),
    RequestState.CLOSED: frozenset(),  # Terminal: zero transitions permitted
}


def can_transition(current: RequestState, target: RequestState) -> bool:
    """Return True if transitioning from current to target state is legally permitted."""
    allowed = _ALLOWABLE_TRANSITIONS.get(current, frozenset())
    return target in allowed


def transition_request_state(
    current: RequestState,
    target: RequestState,
    *,
    reason: str = "",
) -> RequestState:
    """Transition between request states, strictly rejecting invalid paths.

    Raises InvalidStateTransitionError if transition is disallowed.
    """
    if not can_transition(current, target):
        raise InvalidStateTransitionError(current, target, reason)
    return target
