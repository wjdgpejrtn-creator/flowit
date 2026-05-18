from __future__ import annotations

from fastapi import Depends, Request

from auth.domain.ports.session_repository import SessionRepository
from auth.domain.ports.user_repository import UserRepository
from auth.domain.services.permission_resolver import PermissionResolver
from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError, NotFoundError

from app.dependencies.auth import (
    get_permission_resolver,
    get_session_repository,
    get_user_repository,
)


async def get_permission_source(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
    session_repo: SessionRepository = Depends(get_session_repository),
    resolver: PermissionResolver = Depends(get_permission_resolver),
) -> PermissionSource:
    """JWT 검증 후 AuthMiddleware가 채운 `request.state.user_id`/`session_hash`로부터
    User + Session을 조회해 PermissionSource를 구성.

    department_id가 NULL인 사용자는 `user_id`로 fallback (single-tenant 운영 patch —
    onboarding flow에서 정식 할당하는 후속 PR 예정).
    """
    user_id = getattr(request.state, "user_id", None)
    session_hash = getattr(request.state, "session_hash", None)
    if user_id is None or not session_hash:
        raise AuthorizationError("Authentication required", code="E-AUTH-003")

    user = await user_repo.find_by_id(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    if not user.is_active:
        raise AuthorizationError("User is inactive", code="E-AUTH-004")

    session = await session_repo.find_by_hash(session_hash)
    if session is None or session.is_revoked or session.is_expired():
        raise AuthorizationError("Session expired or revoked", code="E-AUTH-006")

    department_id = user.department_id or user.user_id  # fallback: single-tenant
    return resolver.resolve(
        user_id=user.user_id,
        role=user.role,
        department_id=department_id,
        session_id=session.session_id,
    )
