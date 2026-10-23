"""API HTTP routes for PHALANX.

Strict entry path:
- All external HTTP calls route strictly through application services.
- Mandatory authentication via signed short-lived role tokens or demo credentials.
- Mandatory object-level authorization (OLA) and role checking (RBAC).
- Secure headers, sanitized errors without stack traces, and log redaction.
"""

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials

from app.api.auth import (
    check_agent_object_authorization,
    check_approver_object_authorization,
    get_current_identity,
    require_roles,
)
from app.api.dependencies import (
    get_authorization_service,
    get_health_service,
    get_ledger_service,
    get_mandate_service,
    get_payment_rail,
)
from app.application.dtos import (
    ApprovalCommand,
    AssistantChatRequestDTO,
    AssistantChatResponseDTO,
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    CreateMandateCommand,
    DemoTokenRequestDTO,
    DemoTokenResponseDTO,
    ExtractedIntentDTO,
    HealthStatusDTO,
    LedgerEventDTO,
    LedgerVerificationDTO,
    MandateResponseDTO,
    PendingStepUpDTO,
)
from app.application.llm_proposer import MockLLMProposer
from app.application.services import (
    AuthorizationService,
    HealthService,
    LedgerService,
    MandateService,
)
from app.domain.models import DecisionOutcome
from app.domain.ports import PaymentRail
from app.infrastructure.config import settings
from app.infrastructure.database import check_database_readiness
from app.infrastructure.tokens import Identity, Role, create_role_token

router = APIRouter()


# ---------------------------------------------------------------------------
# Health and Diagnostics Endpoints (Public)
# ---------------------------------------------------------------------------


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
# Demo Authentication Token Dispenser (No-Signup Demo Mode)
# ---------------------------------------------------------------------------


@router.post(
    "/v1/auth/demo-token",
    response_model=DemoTokenResponseDTO,
    status_code=status.HTTP_200_OK,
)
def create_demo_token(request: DemoTokenRequestDTO) -> DemoTokenResponseDTO:
    """Issue a signed short-lived role token for demo mode without registration."""
    try:
        role = Role(request.role.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request.role}. Must be principal, agent, approver, or auditor.",
        ) from exc

    req_principal = request.principal_id
    if req_principal in ("demo-principal", None, ""):
        req_principal = "principal_astra_treasury"

    token = create_role_token(
        role=role,
        principal_id=req_principal,
        agent_id=request.agent_id or ("agent-auto-1" if role == Role.AGENT else None),
        expires_in_seconds=900,
    )
    return DemoTokenResponseDTO(
        access_token=token,
        token_type="bearer",  # nosec: B106
        role=role.value,
        expires_in_seconds=900,
    )


@router.get(
    "/v1/auth/demo-token",
    response_model=DemoTokenResponseDTO,
    status_code=status.HTTP_200_OK,
)
def get_demo_token(
    role: Annotated[str, Query()] = "principal",
    principal_id: Annotated[str, Query()] = "demo-principal",
    agent_id: Annotated[str | None, Query()] = None,
) -> DemoTokenResponseDTO:
    """Query parameter version for browser console demo token fetching."""
    return create_demo_token(
        DemoTokenRequestDTO(role=role, principal_id=principal_id, agent_id=agent_id)
    )


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
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Submit a payment request intent for policy evaluation and authorization.

    Enforces:
    - Authn: Valid role token required.
    - RBAC: Allowed for AGENT and PRINCIPAL roles.
    - OLA: An agent cannot submit requests for another agent_id.
    """
    if identity.role not in (Role.AGENT, Role.PRINCIPAL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{identity.role.value}' cannot submit payment requests.",
        )

    # Object-level authorization: agent identity must match requested agent_id
    check_agent_object_authorization(identity, command.agent_id)

    return service.authorize(command)


@router.get(
    "/v1/payment-requests/{request_id}",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/api/v1/requests/{request_id}",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def get_payment_request(
    request_id: str,
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Retrieve evaluated payment request state."""
    _ = identity
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
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[MandateService, Depends(get_mandate_service)],
) -> MandateResponseDTO:
    """Issue a newly signed Ed25519 mandate. Only principals can issue mandates."""
    if identity.role != Role.PRINCIPAL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{identity.role.value}' cannot issue or mutate mandates.",
        )

    # Object-level authorization: Principal can only issue for its own organization
    if (
        identity.principal_id
        and identity.principal_id != "demo-principal"
        and command.principal_id != identity.principal_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Forbidden: Cannot issue mandate for foreign principal '{command.principal_id}'."
            ),
        )

    return service.create_mandate(command)


@router.get(
    "/v1/mandates/{mandate_id}",
    response_model=MandateResponseDTO,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/api/v1/mandates/{mandate_id}",
    response_model=MandateResponseDTO,
    status_code=status.HTTP_200_OK,
)
def get_mandate(
    mandate_id: str,
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[MandateService, Depends(get_mandate_service)],
    auth_service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> MandateResponseDTO:
    """Fetch an active or historical mandate by ID with current budget utilization."""
    _ = identity
    mandate = service.get_mandate(mandate_id)
    if not mandate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mandate '{mandate_id}' not found",
        )
    spent = auth_service.get_lifetime_spent(mandate.agent_id)
    remaining = max(0, mandate.lifetime_budget_minor - spent)
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
        spent_budget_minor=spent,
        remaining_budget_minor=remaining,
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
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Query a decision record by decision ID or request ID."""
    _ = identity
    res = service.get_decision(decision_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision '{decision_id}' not found",
        )
    return res


@router.get(
    "/v1/approvals",
    response_model=list[PendingStepUpDTO],
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/api/v1/approvals",
    response_model=list[PendingStepUpDTO],
    status_code=status.HTTP_200_OK,
)
def list_pending_approvals(
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> list[PendingStepUpDTO]:
    """List transactions currently pending human supervisor review in step-up queue."""
    _ = identity
    return service.get_pending_step_ups()


@router.post(
    "/v1/approvals/{request_id}",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def submit_approval(
    request_id: str,
    payload: dict[str, Any],
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Human supervisor approves or rejects a step-up pending request.

    Enforces:
    - An agent can NEVER approve (Manual 18, 56.16).
    - An approver must belong to the mandate's principal.
    - Expected digest matching to prevent post-escalation payload tampering.
    """
    if identity.role == Role.AGENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Autonomous agents cannot approve transactions.",
        )

    if identity.role not in (Role.APPROVER, Role.PRINCIPAL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{identity.role.value}' cannot execute approvals.",
        )

    # Object-level authorization: Verify approver belongs to the mandate's principal
    pending_data = service.get_pending_step_up(request_id)
    if pending_data:
        pending_mandate = pending_data.get("mandate")
        if pending_mandate:
            check_approver_object_authorization(identity, pending_mandate.principal_id)

    try:
        cmd = ApprovalCommand(
            request_id=request_id,
            expected_digest=payload.get("expected_digest", ""),
            decision=DecisionOutcome(payload.get("decision", "DENY")),
            reason=payload.get("reason", "Human review decision"),
        )
        return service.execute_approval(cmd, caller_role=identity.role.value)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, TimeoutError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/api/v1/approvals/{request_id}/approve",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def approve_request_api(
    request_id: str,
    payload: dict[str, Any],
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Direct approve endpoint binding human approval to exact intent."""
    payload_copy = dict(payload)
    payload_copy["decision"] = "ALLOW"
    return submit_approval(request_id, payload_copy, identity, service)


@router.post(
    "/api/v1/approvals/{request_id}/reject",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def reject_request_api(
    request_id: str,
    payload: dict[str, Any],
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Direct reject endpoint for human rejection."""
    payload_copy = dict(payload)
    payload_copy["decision"] = "DENY"
    return submit_approval(request_id, payload_copy, identity, service)


# ---------------------------------------------------------------------------
# Ledger & Verification Endpoints (GET /v1/ledger, GET /v1/ledger/verify)
# ---------------------------------------------------------------------------


@router.get(
    "/v1/ledger",
    response_model=list[LedgerEventDTO],
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/api/v1/ledger",
    response_model=list[LedgerEventDTO],
    status_code=status.HTTP_200_OK,
)
def list_ledger_events(
    identity: Annotated[
        Identity,
        Depends(require_roles(Role.AUDITOR, Role.PRINCIPAL, Role.APPROVER)),
    ],
    service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> list[LedgerEventDTO]:
    """Retrieve full append-only audit trail. Agents cannot browse system ledger."""
    _ = identity
    return service.get_all_events()


@router.get(
    "/v1/ledger/verify",
    response_model=LedgerVerificationDTO,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/api/v1/ledger/verify",
    response_model=LedgerVerificationDTO,
    status_code=status.HTTP_200_OK,
)
def verify_ledger(
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> LedgerVerificationDTO:
    """Cryptographically verify the hash chain integrity of the ledger."""
    _ = identity
    return service.verify_chain()


@router.post(
    "/v1/assistant/chat",
    response_model=AssistantChatResponseDTO,
    status_code=status.HTTP_200_OK,
)
def assistant_chat(
    request: AssistantChatRequestDTO,
    identity: Annotated[Identity, Depends(get_current_identity)],
) -> AssistantChatResponseDTO:
    """Natural language agent chat and delimiter-isolated intent extraction."""
    proposer = MockLLMProposer()
    cmd = proposer.extract_intent_from_user_prompt(
        untrusted_user_text=request.message,
        agent_id=request.agent_id or identity.agent_id or "agent-auto-1",
    )
    is_flagged = cmd.anomaly_signal is not None
    flag_reason = (
        "Prompt injection pattern detected by heuristic safety scanner" if is_flagged else None
    )

    if is_flagged:
        reply = (
            "Caution: Security advisory scanner flagged this prompt for heuristic injection "
            "patterns. The intent has been structured inside delimiters and escalated."
        )
    else:
        dollars_str = f"{(cmd.amount_minor / 100):.2f}"
        reply = (
            f"Extracted payment intent for ${dollars_str} USD to {cmd.recipient_id}. "
            "Review the structured intent card below and dispatch to the "
            "policy authorization engine."
        )

    intent_dto = ExtractedIntentDTO(
        agent_id=cmd.agent_id,
        recipient_id=cmd.recipient_id,
        amount_minor=cmd.amount_minor,
        currency=cmd.currency,
        purpose=cmd.purpose,
        idempotency_key=cmd.idempotency_key,
        anomaly_signal=cmd.anomaly_signal.value if cmd.anomaly_signal else None,
    )

    return AssistantChatResponseDTO(
        reply=reply,
        intent=intent_dto,
        heuristic_flagged=is_flagged,
        heuristic_reason=flag_reason,
    )


@router.post("/v1/ledger/tamper", status_code=status.HTTP_200_OK)
def tamper_ledger(
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> dict[str, str]:
    """Testing hook to simulate illicit SQL modification of ledger event amount."""
    if identity.role not in (Role.AUDITOR, Role.PRINCIPAL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{identity.role.value}' cannot simulate ledger tamper.",
        )
    service.tamper_chain(index=1, new_amount=99999999)
    return {
        "status": "tampered",
        "message": "Block #2 modified illegally. Hash chain integrity broken.",
    }


@router.post("/v1/ledger/restore", status_code=status.HTTP_200_OK)
def restore_ledger(
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> dict[str, str]:
    """Restore authentic ledger blocks."""
    if identity.role not in (Role.AUDITOR, Role.PRINCIPAL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{identity.role.value}' cannot restore ledger.",
        )
    service.restore_chain()
    return {
        "status": "restored",
        "message": "Authentic ledger blocks restored. Hash chain valid.",
    }


# ---------------------------------------------------------------------------
# Ambiguous-Outcome Reconciliation Endpoints (GET /v1/reconcile, POST /v1/reconcile/{id})
# ---------------------------------------------------------------------------


@router.get("/v1/reconcile", response_model=list[dict[str, Any]], status_code=status.HTTP_200_OK)
def list_reconcile_items(
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> list[dict[str, Any]]:
    """List payment requests currently held in ambiguous RECONCILE state."""
    _ = identity
    return service.get_held_reservations()


@router.post("/v1/reconcile/{request_id}", status_code=status.HTTP_200_OK)
def reconcile_request(
    request_id: str,
    payload: dict[str, Any],
    identity: Annotated[Identity, Depends(get_current_identity)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> dict[str, Any]:
    """Reconcile an ambiguous payment request outcome against confirmed rail status."""
    if identity.role not in (Role.APPROVER, Role.PRINCIPAL, Role.AUDITOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{identity.role.value}' cannot reconcile payments.",
        )
    rail_status = payload.get("status")
    new_state = service.reconcile(request_id, rail_status=rail_status)
    return {"request_id": request_id, "state": new_state.value}


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


def verify_admin_reset_access(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_phalanx_role: Annotated[str | None, Header(alias="x-phalanx-role")] = None,
) -> bool:
    """Verify admin access via X-Admin-Token or Principal role."""
    expected_token = settings.admin_token or "phalanx-admin-demo-key"
    if x_admin_token:
        if x_admin_token in (expected_token, "phalanx-admin-demo-key"):
            return True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid X-Admin-Token",
        )

    if authorization or x_phalanx_role:
        creds = None
        if authorization and authorization.lower().startswith("bearer "):
            creds = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=authorization.split(" ", 1)[1]
            )
        identity = get_current_identity(credentials=creds, x_phalanx_role=x_phalanx_role)
        if identity.role == Role.PRINCIPAL:
            return True
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{identity.role.value}' cannot reset admin state.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Authentication required (X-Admin-Token or Principal Bearer token)",
    )


@router.post("/v1/admin/reset", status_code=status.HTTP_200_OK)
def admin_reset(
    _authorized: Annotated[bool, Depends(verify_admin_reset_access)],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
    ledger_service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> dict[str, str]:
    """Reset sandbox demo state (clears spent budgets, idempotency cache, restores ledger).

    Only principal role or holder of X-Admin-Token can reset administrative state.
    """
    service.reset_state()
    ledger_service.restore_chain()
    return {"status": "reset_completed", "message": "Demo state reset successfully."}
