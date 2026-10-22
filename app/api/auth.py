"""Authentication and object-level authorization dependencies for FastAPI."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infrastructure.tokens import (
    Identity,
    Role,
    TokenError,
    TokenExpiredError,
    verify_role_token,
)

security = HTTPBearer(auto_error=False)


def get_current_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    x_phalanx_role: Annotated[str | None, Header()] = None,
) -> Identity:
    """Extract and verify caller identity from Bearer token or demo header.

    Raises:
        HTTPException(401): If token is missing, malformed, or expired.
    """
    token_str: str | None = None

    if credentials and credentials.scheme.lower() == "bearer":
        token_str = credentials.credentials
    elif x_phalanx_role:
        # Support demo header convenience in demo environment
        token_str = f"demo-{x_phalanx_role}"

    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Authentication token required (Bearer <token>)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verify_role_token(token_str)
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unauthorized: Token expired ({exc})",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unauthorized: Invalid token ({exc})",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_roles(*allowed_roles: Role) -> Callable[[Identity], Identity]:
    """Enforce role-based access control."""

    def role_checker(
        identity: Annotated[Identity, Depends(get_current_identity)],
    ) -> Identity:
        if identity.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Forbidden: Role '{identity.role.value}' lacks permission for this action. "
                    f"Required: {[r.value for r in allowed_roles]}"
                ),
            )
        return identity

    return role_checker


def check_agent_object_authorization(identity: Identity, request_agent_id: str) -> None:
    """Object-level authorization: An agent identity can only request for itself."""
    if identity.role == Role.AGENT and identity.agent_id and identity.agent_id != request_agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Forbidden: Agent '{identity.agent_id}' cannot initiate "
                f"transactions on behalf of '{request_agent_id}'"
            ),
        )


def check_approver_object_authorization(identity: Identity, mandate_principal_id: str) -> None:
    """Object-level authorization: An approver must belong to the mandate's principal."""
    if (
        identity.role in (Role.APPROVER, Role.PRINCIPAL)
        and identity.principal_id
        and mandate_principal_id
        and identity.principal_id != mandate_principal_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Forbidden: Approver principal '{identity.principal_id}' does not match "
                f"mandate principal '{mandate_principal_id}'"
            ),
        )
