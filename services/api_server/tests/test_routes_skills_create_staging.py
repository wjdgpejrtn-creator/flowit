"""POST /skills/personal — 추출 staging carry 테스트 (모델 A: self-publish 시 실 NodeDefinition I/O).

bare-app + dependency_overrides 패턴(extract/review 테스트와 동일) — 실 JWT 우회.
검증축: node_spec_staging 전달 시 그대로 use case에 전달 / 미전달 시 placeholder 폴백.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_document_repository
from app.dependencies.use_cases import (
    get_create_draft_skill_use_case,
    get_get_personal_skill_use_case,
    get_update_personal_skill_use_case,
)
from app.routers.skills import router as skills_router
from common_schemas import PermissionSource
from common_schemas.enums import RiskLevel
from fastapi import FastAPI
from fastapi.testclient import TestClient
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects.skill_state import SkillState

_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_SKILL_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


def _permission() -> PermissionSource:
    return PermissionSource(
        user_id=_USER_ID,
        role="User",  # type: ignore[arg-type]
        department_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


def _created_skill() -> MarketplacePersonalSkill:
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=_SKILL_ID,
        owner_user_id=_USER_ID,
        name="n",
        description="d",
        lifecycle_state=SkillState.DRAFT,
        created_at=now,
        updated_at=now,
    )


def _app(create: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(skills_router)
    app.dependency_overrides[get_permission_source] = _permission
    app.dependency_overrides[get_create_draft_skill_use_case] = lambda: create
    get_personal = AsyncMock()
    get_personal.execute.return_value = _created_skill()
    app.dependency_overrides[get_get_personal_skill_use_case] = lambda: get_personal
    app.dependency_overrides[get_update_personal_skill_use_case] = lambda: AsyncMock()
    app.dependency_overrides[get_document_repository] = lambda: AsyncMock()
    return app


def test_create_carries_node_spec_staging():
    create = AsyncMock()
    create.execute.return_value = _SKILL_ID
    body = {
        "name": "주문 알림",
        "description": "주문 상태 변경 시 슬랙 알림",
        "node_spec_staging": {
            "category": "integration",
            "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"ts": {"type": "string"}}},
            "risk_level": "Medium",
            "required_connections": ["slack"],
            "service_type": "slack",
        },
    }
    with TestClient(_app(create)) as tc:
        res = tc.post("/api/v1/skills/personal", json=body)
    assert res.status_code == 201
    staging = create.execute.call_args.kwargs["node_spec_staging"]
    # 추출 staging이 placeholder가 아니라 그대로 전달됐는지
    assert staging.category == "integration"
    assert staging.risk_level == RiskLevel.MEDIUM
    assert staging.input_schema["properties"]["order_id"]["type"] == "string"
    assert staging.required_connections == ["slack"]
    assert staging.service_type == "slack"


def test_create_without_staging_uses_placeholder():
    create = AsyncMock()
    create.execute.return_value = _SKILL_ID
    with TestClient(_app(create)) as tc:
        res = tc.post("/api/v1/skills/personal", json={"name": "수동", "description": "수동 폼"})
    assert res.status_code == 201
    staging = create.execute.call_args.kwargs["node_spec_staging"]
    # 미전달 시 기존 placeholder(action/빈 스키마/LOW) 유지(하위호환)
    assert staging.category == "action"
    assert staging.input_schema == {}
    assert staging.risk_level == RiskLevel.LOW
