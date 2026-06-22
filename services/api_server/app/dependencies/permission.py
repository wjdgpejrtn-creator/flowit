from __future__ import annotations

from auth.domain.entities.user import User
from auth.domain.ports.session_repository import SessionRepository
from auth.domain.ports.user_repository import UserRepository
from auth.domain.services.permission_resolver import PermissionResolver
from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError, NotFoundError
from fastapi import Depends, Request

from app.dependencies.auth import (
    get_permission_resolver,
    get_session_repository,
    get_user_repository,
)


async def get_current_user(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    """AuthMiddleware가 채운 `request.state.user_id`로 현재 User를 조회.

    User 조회의 **단일 소스** — `get_permission_source`도 본 의존성을 경유한다. FastAPI가
    한 요청 내에서 동일 의존성을 캐싱하므로, `/auth/me`처럼 user(프로필)와 permission(인가)을
    함께 쓰는 라우트에서도 User DB 조회는 1회로 합쳐진다 (PR #163 리뷰 — 이중 조회 제거).
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise AuthorizationError("Authentication required", code="E-AUTH-003")
    user = await user_repo.find_by_id(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    if not user.is_active:
        raise AuthorizationError("User is inactive", code="E-AUTH-004")
    return user


async def get_permission_source(
    request: Request,
    user: User = Depends(get_current_user),
    session_repo: SessionRepository = Depends(get_session_repository),
    resolver: PermissionResolver = Depends(get_permission_resolver),
) -> PermissionSource:
    """JWT 검증 후 AuthMiddleware가 채운 `session_hash`로 Session을 조회해 PermissionSource를 구성.

    User는 `get_current_user`에서 공유받는다 (FastAPI 의존성 캐싱 — 동일 요청 내 User 조회 1회).

    department_id가 NULL인 사용자는 `user_id`로 fallback (single-tenant 운영 patch —
    onboarding flow에서 정식 할당하는 후속 PR 예정).
    """
    session_hash = getattr(request.state, "session_hash", None)
    if not session_hash:
        raise AuthorizationError("Authentication required", code="E-AUTH-003")

    session = await session_repo.find_by_hash(session_hash)
    if session is None or session.is_revoked or session.is_expired():
        raise AuthorizationError("Session expired or revoked", code="E-AUTH-006")

    # TODO(req-002 onboarding): department_id가 NULL인 사용자는 user_id로 fallback.
    # PR #88(JIT user provisioning) 직후 모든 신규 user가 department_id=None으로 생성되므로
    # 본 분기가 default 경로. multi-tenant 도입 시 onboarding flow에서 정식 할당하는 별도 PR
    # 필요 — single-tenant mode 가정이 깨지면 모든 user가 자기 자신 department 안에 격리되어
    # team scope workflow 공유가 작동하지 않음.
    department_id = user.department_id or user.user_id  # fallback: single-tenant patch
    return resolver.resolve(
        user_id=user.user_id,
        role=user.role,
        department_id=department_id,
        session_id=session.session_id,
    )
