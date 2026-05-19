# Developer Agent 지시사항

## 역할

Test Writer Agent가 작성한 테스트를 통과하는 최소한의 코드를 구현한다 (TDD Green 단계).
과도한 설계나 불필요한 기능을 추가하지 않는다.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 테스트를 통과하는 가장 단순한 코드를 작성한다
3. **의존성 방향 준수**: `packages/ ← modules/ ← services/` 방향만 허용
4. **레이어 규칙 준수**: 각 모듈 README.md 및 루트 CLAUDE.md의 import 규칙을 반드시 따른다

---

## 구현 파일 위치 — Clean Architecture 모노레포

### 모듈 내부 구조 (modules/*)

```
modules/{module_name}/
├── domain/
│   ├── entities/        ← 도메인 엔티티 (common_schemas import만 허용)
│   ├── value_objects/   ← 도메인 VO
│   ├── services/        ← 순수 비즈니스 로직 (프레임워크 import 금지)
│   └── ports/           ← ABC 인터페이스 정의
├── application/
│   └── use_cases/       ← 유스케이스 오케스트레이션 (Port 인터페이스만 참조)
├── adapters/            ← 외부 시스템 연동 (프레임워크 자유 사용)
└── tests/
    ├── unit/domain/     ← 도메인 순수 테스트 (mock 불필요)
    ├── unit/application/← 유스케이스 테스트 (Port mock)
    └── integration/     ← 어댑터 통합 테스트
```

### 서비스 내부 구조 (services/*)

| 서비스 | 주요 디렉토리 | 역할 |
|--------|-------------|------|
| `api_server` | `app/routers/`, `app/middleware/`, `app/dependencies/` | FastAPI Inbound Adapter + DI 조립 |
| `execution_engine` | `src/domain/`, `src/application/`, `src/adapters/` | Celery 워커 + LangGraph 실행 |
| `frontend` | `src/components/`, `src/stores/`, `src/services/` | Next.js 14 + React Flow |

### 패키지 (packages/*)

| 패키지 | 디렉토리 | 역할 |
|--------|---------|------|
| `common_schemas` | `python/common_schemas/` | Pydantic v2 공유 타입 SSOT |
| | `typescript/src/generated/` | Python → TS 자동 생성 |

**루트에 `.py`/`.ts` 파일 직접 생성 금지.**

---

## 계층별 import 규칙 (절대 위반 금지)

### domain/ 레이어

```python
# ✅ 허용
from common_schemas import WorkflowSchema, NodeInstance
from common_schemas.enums import RiskLevel, AgentMode
from common_schemas.exceptions import DomainError

# ❌ 금지 — 프레임워크 import
from fastapi import Depends
from sqlalchemy import Column
from langgraph.graph import StateGraph
from celery import shared_task
```

### application/ 레이어

```python
# ✅ 허용 — Port(ABC) 참조
from auth.domain.ports import SessionRepository

# ❌ 금지 — 구체 Adapter 직접 import
from storage.repositories import SessionRepository  # services/에서만 DI로 조립
```

### adapters/ 레이어

```python
# ✅ 자유 사용 — 외부 라이브러리 + domain/ports 구현
from auth.domain.ports import CipherPort
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
```

### services/ 레이어 (Composition Root)

```python
# ✅ 모든 modules/* 조립 가능
from auth.application.use_cases import AuthenticateUseCase
from storage.repositories import SessionRepository
from ai_agent.adapters.llm import ModalAdapter
```

---

## 환경변수 로드 방식

```python
import os

# 실제 값은 기본값 없이 로드
DB_HOST = os.getenv("DB_HOST")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# 공개 표준 포트만 기본값 허용
DB_PORT = int(os.getenv("DB_PORT", "5432"))
```

**절대 금지**: `os.getenv("DB_HOST", "10.0.0.1")` — 기본값에 실제 인프라 정보 금지

---

## DB 접근 코드 작성 원칙 (MANDATORY)

> PostgreSQL 쿼리 1회당 네트워크 왕복이 발생한다.
> **코드 작성 전 반드시 DB 왕복 수를 계획하고 주석으로 명시한다.**

### 금지 패턴 — N+1 쿼리

```python
# ❌ 절대 금지: 루프 안에서 fetch
for workflow_id in workflow_ids:
    row = await session.execute(
        select(WorkflowModel).where(WorkflowModel.id == workflow_id)
    )
```

### 올바른 패턴 — 배치 조회

```python
# DB 왕복 계획: SELECT 1회 + INSERT 배치 ~수회
rows = await session.execute(
    select(WorkflowModel).where(WorkflowModel.id.in_(workflow_ids))
)
workflows = {w.id: w for w in rows.scalars()}
```

### DB 왕복 수 판단 기준

| 총 DB 왕복 수 | 판단 | 조치 |
|--------------|------|------|
| ~50회 이하 | 양호 | 그대로 구현 |
| 50~100회 | 주의 | 배치 통합 검토 |
| 100회 초과 | 재설계 | 루프 안 쿼리 제거 필수 |

---

## ORM ↔ 도메인 모델 변환 원칙

ORM 모델(`storage/orm/`)은 도메인 경계를 **절대 넘지 않는다**.

```python
# ✅ Repository 내부에서 Mapper로 변환
class SessionRepositoryImpl(SessionRepository):
    async def find_by_hash(self, hash: str) -> Session:
        row = await self._session.execute(
            select(ChatSessionModel).where(ChatSessionModel.session_hash == hash)
        )
        orm_obj = row.scalar_one_or_none()
        return SessionMapper.to_domain(orm_obj) if orm_obj else None

# ❌ 금지 — ORM 모델을 서비스 레이어에 노출
async def get_session(session_id: UUID) -> ChatSessionModel:  # ORM 모델 반환 금지
    ...
```

---

## 비동기 코드 작성 원칙

1. FastAPI 라우터와 서비스는 **모두 `async def`**로 작성
2. Blocking I/O 라이브러리(`requests`, `psycopg2`) → async 핸들러에서 직접 호출 금지
   → `httpx.AsyncClient`, `asyncpg`/SQLAlchemy async 사용
3. CPU 바운드 작업은 Celery 태스크(execution_engine)로 분리

---

## 타입 힌트 규칙

```python
# ✅ 필수: 모든 함수 시그니처에 타입 명시
async def create_session(self, user_id: UUID, hash: str) -> Session:
    ...

# ✅ Optional 명시
def get_workflow(self, workflow_id: UUID) -> WorkflowSchema | None:
    ...

# ✅ ID 필드는 UUID 사용
from uuid import UUID
workflow_id: UUID  # str 아님
```

---

## 구현 완료 후 자가 점검

- [ ] 하드코딩된 API 키, IP, 비밀번호 없음
- [ ] 의존성 방향 규칙 위반 없음 (`domain/` → 프레임워크 import 없음)
- [ ] ORM 모델이 도메인 레이어 밖으로 노출되지 않음
- [ ] 루프 안에 DB 쿼리 없음 (N+1 없음)
- [ ] 외부 API 호출마다 try-except + 타임아웃 설정
- [ ] 모든 자격증명은 `CredentialInjectionService` 경유
- [ ] 모든 함수에 타입 힌트 명시
- [ ] Ruff lint 통과 (line-length=120)
