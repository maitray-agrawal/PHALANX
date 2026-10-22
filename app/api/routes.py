"""API HTTP routes for PHALANX."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_authorization_service, get_health_service
from app.application.dtos import (
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    HealthStatusDTO,
)
from app.application.services import AuthorizationService, HealthService

router = APIRouter()


@router.get("/health", response_model=HealthStatusDTO, status_code=status.HTTP_200_OK)
def health_check(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> HealthStatusDTO:
    """System health check endpoint."""
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
