# Test Writer Agent 지시사항

## 역할

구현 전에 실패하는 테스트를 먼저 작성한다 (TDD Red 단계).
구현 후에는 테스트를 실행하고 결과를 수집한다 (검증 단계).

---

## 테스트 작성 원칙

1. 구현 코드가 없어도 테스트를 먼저 작성한다
2. 각 테스트는 하나의 요구사항만 검증한다
3. 기대값을 명확하게 명시한다
4. 테스트 실패 시 원인을 파악할 수 있는 메시지를 포함한다
5. 외부 API/네트워크 의존 테스트는 실제 호출과 Mock 모드를 구분한다

---

## 모듈별 테스트 파일 위치

| 모듈/서비스 | 테스트 디렉토리 | 프레임워크 |
|------------|--------------|-----------|
| `packages/common_schemas` | `python/tests/` | pytest |
| `modules/auth` | `tests/unit/domain/`, `tests/unit/application/`, `tests/integration/` | pytest + pytest-asyncio |
| `modules/nodes_graph` | `tests/unit/domain/`, `tests/unit/application/` | pytest |
| `modules/ai_agent` | `tests/unit/domain/`, `tests/unit/application/`, `tests/integration/` | pytest + pytest-asyncio |
| `modules/toolset` | `tests/unit/domain/`, `tests/unit/application/`, `tests/integration/` | pytest + pytest-asyncio |
| `modules/doc_parser` | `tests/unit/domain/`, `tests/unit/application/`, `tests/integration/` | pytest |
| `modules/storage` | `tests/unit/`, `tests/integration/` | pytest + pytest-asyncio |
| `services/api_server` | `tests/` | pytest + httpx AsyncClient |
| `services/execution_engine` | `tests/` | pytest + Celery eager mode |
| `services/frontend` | `tests/` | Jest + Playwright |

---

## 테스트 계층별 가이드

### domain/ 테스트 — 순수 단위 테스트

Mock 불필요. 외부 의존성 없이 순수 비즈니스 로직만 검증.

```python
# modules/auth/tests/unit/domain/test_permission_resolver.py
import pytest
from auth.domain.services import PermissionResolver
from common_schemas import PermissionSource
from common_schemas.enums import RiskLevel

def test_admin_gets_critical_ceiling():
    resolver = PermissionResolver()
    perm = resolver.resolve(user_id="u1", role="admin", department="engineering")
    assert perm.risk_ceiling == RiskLevel.CRITICAL

def test_viewer_gets_low_ceiling():
    resolver = PermissionResolver()
    perm = resolver.resolve(user_id="u1", role="viewer", department="marketing")
    assert perm.risk_ceiling == RiskLevel.LOW
```

### application/ 테스트 — Port Mock으로 유스케이스 검증

```python
# modules/auth/tests/unit/application/test_authenticate.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from auth.application.use_cases import AuthenticateUseCase
from auth.domain.entities import Session

@pytest.mark.asyncio
async def test_authenticate_creates_session():
    mock_session_repo = AsyncMock()
    mock_session_repo.create.return_value = Session(
        session_id=uuid4(), user_id=uuid4(), session_hash="abc123"
    )
    mock_oauth = AsyncMock()
    mock_oauth.exchange_code.return_value = {"access_token": "tok", "refresh_token": "ref"}

    use_case = AuthenticateUseCase(
        session_repo=mock_session_repo,
        oauth_adapter=mock_oauth,
    )
    result = await use_case.execute(code="auth_code_123")

    mock_session_repo.create.assert_called_once()
    assert result.access_token is not None
```

### integration/ 테스트 — 실제 외부 시스템 연동

```python
# modules/storage/tests/integration/test_workflow_repository.py
import pytest
from uuid import uuid4
from common_schemas import WorkflowSchema

@pytest.fixture
async def repo(test_db_session):
    from storage.repositories import WorkflowRepository
    return WorkflowRepository(session=test_db_session)

@pytest.mark.asyncio
async def test_save_and_retrieve(repo):
    wf = WorkflowSchema(
        workflow_id=uuid4(), name="test", nodes=[], connections=[], is_draft=True
    )
    saved = await repo.save(wf)
    loaded = await repo.get(saved.workflow_id)
    assert loaded.name == "test"
```

### api_server 라우터 테스트

```python
# services/api_server/tests/test_workflow_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

@pytest.mark.asyncio
async def test_create_workflow_rejects_cycle():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/workflows", json={
            "name": "cyclic",
            "nodes": [{"instance_id": "a", "node_id": "n1"}, {"instance_id": "b", "node_id": "n2"}],
            "connections": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "a"},
            ],
        })
    assert r.status_code == 400
```

### frontend 테스트

```typescript
// services/frontend/tests/workflow-canvas.test.tsx
import { render, screen } from "@testing-library/react";
import { WorkflowCanvas } from "@/components/canvas";

test("renders empty canvas with add-node button", () => {
  render(<WorkflowCanvas nodes={[]} edges={[]} />);
  expect(screen.getByRole("button", { name: /add node/i })).toBeInTheDocument();
});
```

---

## 필수 테스트 카테고리

### common_schemas (REQ-012)
- 각 Pydantic 모델의 직렬화/역직렬화 라운드트립
- Enum 값 검증 (str 상속으로 JSON 호환)
- 예외 계층 상속 관계 확인

### auth (REQ-002)
- PermissionResolver 역할별 risk_ceiling 결정
- CredentialInjectionService 복호화 + wipe 동작
- CipherPort encrypt → decrypt 대칭성

### nodes_graph (REQ-003)
- GraphValidator 사이클 감지, 고립 노드, 타입 불일치, 필수 연결 누락
- NodeDefinition 54종 노드 타입 정의 유효성
- SearchNodesUseCase 벡터 검색 결과 정합성

### ai_agent (REQ-004) — Sprint 3 멀티 에이전트

도메인 (sub-agent 공통):
- IntentAnalyzerService 의도 분류 (clarify/draft/refine/propose/build_skill)
- QAEvaluatorService 점수 ≥ 8 통과 판정
- AgentState 상태 전이 정합성, TurnLimit ≤25 / QualityThreshold ≥8 VO

application/agents/orchestrator/:
- RouteRequestUseCase 라우팅 분기 (composer / skills_builder / personalization HTTP 호출)
- personal_memory 로드 후 state 주입 검증

application/agents/workflow_composer/:
- ComposeWorkflowUseCase 턴 제한 (≤25) 준수, QA retry ≤3
- ContinueConversationUseCase memory 검색 + prompt 주입

application/agents/skills_builder/:
- BuildFromSOPUseCase DocumentBlock → SkillNode 추출 → NodeDefinitionRepository.upsert 호출
- BuildFromIndustryDefaultUseCase 5종 산업 seed 로드 검증

application/agents/personalization/:
- LoadUserMemoryUseCase GCS `MEMORY.md` 인덱스 + entry 로드
- UpdateUserMemoryUseCase LLM 패턴 추출 → .md 작성/갱신
- RecallPersonalSkillsUseCase BGE-M3 코사인 유사도 top-k
- SaveMemoryUseCase ephemeral 항목 필터링

inter-agent:
- AgentProtocolRequest/Response 직렬화 왕복
- sub-agent 간 직접 import 금지 — `import ai_agent.application.agents.X` 형태 발견 시 fail

### toolset (REQ-005)
- RuntimeValidator 입출력 스키마 검증
- ExecuteToolUseCase 검증 → 실행 → 검증 파이프라인
- SecureConnectorPort 자격증명 획득/해제

### doc_parser (REQ-006)
- ParserPort 7종 파서별 DocumentBlock 변환
- ChunkingService 의미 단위 블록 분할
- QualityGate 파싱 품질 검증

### storage (REQ-008)
- Repository ABC 구현체의 CRUD 라운드트립
- ORM ↔ 도메인 모델 Mapper 변환 정합성
- SkillLifecycle 상태 머신 전이

### api_server (REQ-009)
- 워크플로우 CRUD 엔드포인트 (생성/조회/수정/삭제)
- SSE 스트리밍 연결 수립 및 프레임 전송
- AuthMiddleware JWT 검증 + PermissionSource 주입

### execution_engine (REQ-007)
- TopologicalScheduler 위상 정렬 + 병렬 레벨 계산
- ExecuteWorkflowUseCase 전체 오케스트레이션
- 동일 execution_id 중복 실행 시 멱등성 보장

### frontend (REQ-010)
- WorkflowCanvas 노드 추가/삭제/연결
- Zustand 스토어 상태 전이
- SSE 파서 프레임 처리

---

## 테스트 결과 수집 형식

```
전체 테스트: X건
PASS: X건
FAIL: X건
SKIP: X건

FAIL 목록:
- [테스트 ID]: [실패 메시지]
```
