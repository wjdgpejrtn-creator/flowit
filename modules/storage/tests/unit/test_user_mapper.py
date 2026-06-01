"""UserMapper 단위 테스트 — department(표시용 라벨) 매핑 round-trip.

AppBar 부서 배지가 user_id 대신 표시용 부서 라벨(users.department 문자열)을 보여주도록 매퍼에
department 매핑을 추가했다(이전엔 ORM 컬럼은 있으나 매퍼가 누락). JWT/라우트 비의존 — 순수
엔티티↔ORM 변환만 검증하므로 어떤 환경에서도 실행된다(api_server /me 라우트 테스트는 JWT 인프라
의존이라 별개).
"""
from datetime import UTC, datetime
from uuid import uuid4

from auth.domain.entities.user import User
from storage.mappers.user_mapper import UserMapper


def _user(*, department, department_id):
    now = datetime.now(UTC)
    return User(
        user_id=uuid4(),
        email="tester@example.com",
        name="Tester",
        role="Admin",
        department_id=department_id,
        department=department,
        created_at=now,
        updated_at=now,
    )


def test_department_label_round_trips():
    # 표시용 부서 라벨이 to_orm→to_domain 왕복에서 보존되어야 /auth/me가 배지에 노출 가능.
    dept_id = uuid4()
    user = _user(department="FlowIt-001", department_id=dept_id)
    back = UserMapper.to_domain(UserMapper.to_orm(user))
    assert back.department == "FlowIt-001"
    # authz용 department_id(UUID)도 표시 라벨과 독립적으로 보존(관심사 분리).
    assert back.department_id == dept_id


def test_department_none_round_trips():
    # 미설정(NULL) graceful — 프론트가 '—' 표시.
    user = _user(department=None, department_id=None)
    back = UserMapper.to_domain(UserMapper.to_orm(user))
    assert back.department is None
    assert back.department_id is None
