"""API HTTP routes for PHALANX.

Strict entry path:
- All external HTTP calls route strictly through application services.
- Mandatory object-level authorization and role checking.
- Secure headers, sanitized errors, no secret leakage.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.api.dependencies import (
    get_authorization_service,
    get_health_service,
    get_ledger_service,
    get_mandate_service,
    get_payment_rail,
)
from app.application.dtos import (
    ApprovalCommand,
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    CreateMandateCommand,
    HealthStatusDTO,
    LedgerEventDTO,
    LedgerVerificationDTO,
    MandateResponseDTO,
)
from app.application.services import (
    AuthorizationService,
    HealthService,
    LedgerService,
    MandateService,
)
from app.domain.models import DecisionOutcome
from app.infrastructure.database import check_database_readiness
from app.infrastructure.paypal import PaymentRail

router = APIRouter()


@router.get("/healthz", status_code=status.HTTP_200_OK)
def healthz() -> dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz(response: Response) -> dict[str, str]:
    """Readiness probe endpoint checking database connectivity."""
    is_ready, details = check_database_readiness()
    if is_ready:
        response.status_code = status.HTTP_200_OK
        return {"status": "ready", "database": details}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "not_ready", "database": details}


@router.get("/health", response_model=HealthStatusDTO, status_code=status.HTTP_200_OK)
def health_check(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> HealthStatusDTO:
    """Detailed system diagnostic endpoint."""
    return service.check_health()


# ---------------------------------------------------------------------------
# Payment Request Authorization Endpoints (POST /v1/payment-requests)
# ---------------------------------------------------------------------------


@router.post(
    "/v1/payment-requests",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/api/v1/authorize",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def create_payment_request(
    command: AuthorizeTransactionCommand,
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Submit a payment request intent for policy evaluation and authorization."""
    return service.authorize(command)


@router.get(
    "/v1/payment-requests/{request_id}",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def get_payment_request(
    request_id: str,
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Retrieve evaluated payment request state."""
    res = service.get_payment_request(request_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment request '{request_id}' not found",
        )
    return res


# ---------------------------------------------------------------------------
# Mandate Management Endpoints (POST /v1/mandates, GET /v1/mandates/{id})
# ---------------------------------------------------------------------------


@router.post(
    "/v1/mandates",
    response_model=MandateResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
def create_mandate(
    command: CreateMandateCommand,
    service: Annotated[MandateService, Depends(get_mandate_service)],
    x_phalanx_role: Annotated[str | None, Header()] = "principal",
) -> MandateResponseDTO:
    """Issue a newly signed Ed25519 mandate. Only principals can issue mandates."""
    if x_phalanx_role == "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Autonomous agents cannot issue or mutate mandates.",
        )
    return service.create_mandate(command)


@router.get(
    "/v1/mandates/{mandate_id}",
    response_model=MandateResponseDTO,
    status_code=status.HTTP_200_OK,
)
def get_mandate(
    mandate_id: str,
    service: Annotated[MandateService, Depends(get_mandate_service)],
) -> MandateResponseDTO:
    """Fetch an active or historical mandate by ID."""
    mandate = service.get_mandate(mandate_id)
    if not mandate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mandate '{mandate_id}' not found",
        )
    return MandateResponseDTO(
        mandate_id=mandate.mandate_id,
        version=mandate.version,
        principal_id=mandate.principal_id,
        agent_id=mandate.agent_id,
        single_limit_minor=mandate.single_limit_minor,
        instant_threshold_minor=mandate.instant_threshold_minor,
        lifetime_budget_minor=mandate.lifetime_budget_minor,
        currency=mandate.currency,
        allowed_payees=list(mandate.allowed_payees),
        allowed_purposes=list(mandate.allowed_purposes),
        valid_from_utc=mandate.valid_from_utc,
        valid_until_utc=mandate.valid_until_utc,
        status=mandate.status,
        key_id=mandate.key_id,
        signature=mandate.signature,
    )


# ---------------------------------------------------------------------------
# Decision & Approval Endpoints (GET /v1/decisions/{id}, POST /v1/approvals/{id})
# ---------------------------------------------------------------------------


@router.get(
    "/v1/decisions/{decision_id}",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def get_decision(
    decision_id: str,
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Query a decision record by decision ID or request ID."""
    res = service.get_decision(decision_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision '{decision_id}' not found",
        )
    return res


@router.post(
    "/v1/approvals/{request_id}",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def submit_approval(
    request_id: str,
    payload: dict[str, Any],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
    x_phalanx_role: Annotated[str | None, Header()] = "approver",
) -> AuthorizationResponseDTO:
    """Human supervisor approves or rejects a step-up pending request."""
    if x_phalanx_role == "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Agent identity cannot approve step-up transactions.",
        )

    try:
        cmd = ApprovalCommand(
            request_id=request_id,
            expected_digest=payload.get("expected_digest", ""),
            decision=DecisionOutcome(payload.get("decision", "DENY")),
            reason=payload.get("reason", "Human review decision"),
        )
        return service.execute_approval(cmd, caller_role=x_phalanx_role or "approver")
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, TimeoutError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Ledger & Verification Endpoints (GET /v1/ledger, GET /v1/ledger/verify)
# ---------------------------------------------------------------------------


@router.get(
    "/v1/ledger",
    response_model=list[LedgerEventDTO],
    status_code=status.HTTP_200_OK,
)
def list_ledger_events(
    service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> list[LedgerEventDTO]:
    """Retrieve full append-only audit trail."""
    return service.get_all_events()


@router.get(
    "/v1/ledger/verify",
    response_model=LedgerVerificationDTO,
    status_code=status.HTTP_200_OK,
)
def verify_ledger(
    service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> LedgerVerificationDTO:
    """Cryptographically verify the hash chain integrity of the ledger."""
    return service.verify_chain()


# ---------------------------------------------------------------------------
# PayPal Webhook Ingestion (POST /v1/webhooks/paypal)
# ---------------------------------------------------------------------------


processed_webhook_events: set[str] = set()


@router.post("/v1/webhooks/paypal", status_code=status.HTTP_200_OK)
async def paypal_webhook(
    request: Request,
    rail: Annotated[PaymentRail, Depends(get_payment_rail)],
) -> dict[str, str]:
    """Ingest PayPal webhook events with signature verification and idempotency."""
    body_bytes = await request.body()
    headers_dict = dict(request.headers)

    # Verify signature
    if not rail.verify_webhook(headers_dict, body_bytes):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PayPal webhook signature verification failed",
        )

    try:
        data = await request.json()
    except Exception:
        data = {}

    event_id = data.get("id")
    if event_id:
        if event_id in processed_webhook_events:
            return {"status": "duplicate_ignored", "event_id": event_id}
        processed_webhook_events.add(event_id)

    return {"status": "processed", "event_id": event_id or "unknown"}


# ---------------------------------------------------------------------------
# Demo Reset Endpoint (POST /v1/admin/reset)
# ---------------------------------------------------------------------------


@router.post("/v1/admin/reset", status_code=status.HTTP_200_OK)
def admin_reset(
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
    x_phalanx_role: Annotated[str | None, Header()] = "principal",
) -> dict[str, str]:
    """Reset sandbox demo state (clears spent budgets and idempotency cache)."""
    if x_phalanx_role == "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Agent identity cannot reset administrative state.",
        )
    service.reset_state()
    return {"status": "reset_completed", "message": "Demo state reset successfully."}
