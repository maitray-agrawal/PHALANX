"""API HTTP routes for PHALANX."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_authorization_service, get_health_service
from app.application.dtos import (
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    HealthStatusDTO,
)
from app.application.services import AuthorizationService, HealthService
from app.infrastructure.database import check_database_readiness

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


@router.post(
    "/api/v1/authorize",
    response_model=AuthorizationResponseDTO,
    status_code=status.HTTP_200_OK,
)
def authorize_transaction(
    command: AuthorizeTransactionCommand,
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> AuthorizationResponseDTO:
    """Evaluate an autonomous agent transaction authorization request."""
    return service.authorize(command)
