# Sprint 3 — 외부 서비스 노드 표준 + Plugin Discovery 설계 노트

**브랜치**: `feature/req-003-catalog-*` (5/12~5/15)
**담당**: 박아름
**작성일**: 2026-05-11
**참조 spec**: `docs/specs/REQ-003-nodes-graph.md`, `docs/specs/REQ-004-ai-agent.md`, `docs/specs/plan/sprint-3.md` §4.2

---

## 0. 배경

Sprint 3 1주차(A2) 박아름 작업:

| 일자 | 카테고리 | 종수 | 브랜치 |
|------|---------|----|-------|
| 5/12 | Communication (Slack/Gmail/Outlook/Teams) | 4 | `feature/req-003-catalog-communication` |
| 5/13 | Document (Drive/Sheets/Docs/OneDrive) | 4 | `feature/req-003-catalog-document` |
| 5/14 | Data + AI/ML + Productivity | 9 | `feature/req-003-plugin-discovery` |
| 5/15 | 잔여 (Webhook/Schedule/Filter/Transform 등) | n | `feature/req-003-catalog-misc` |

현재 카탈로그 **30종 (data 14 + control 8 + trigger 6 + external 2)** → 신규 17~21종 추가 + Plugin discovery 진입점 추가.

본 노트는 4개 PR 진행 시 **반복적으로 참조할 공통 패턴**과 **결정 사항**을 정리한다.

---

## 1. 외부 서비스 노드 — 파일 표준

### 1.1 파일 구조 (기존 `adapters/catalog/external/http_request.py` 패턴 그대로)

```
adapters/catalog/external/{node_type}.py
  ├── @dataclass {NodeType}Input
  ├── @dataclass {NodeType}Output
  ├── class {NodeType}Node(BaseNode[Input, Output])
  │     ├── metadata: NodeMetadata
  │     ├── input_schema / output_schema (dataclass 참조)
  │     └── async def process(self, input) -> Output
  └── def get_node_definition() -> NodeDefinition
```

- `_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)` — `domain/catalog/_catalog_ns.py`의 namespace UUID 사용 (deterministic)
- 등록은 `application/catalog_registry.py`의 `get_all_node_definitions()`에 import + 호출 추가

### 1.2 외부 서비스 노드 필드 규칙

REQ-003 spec H-4 합의에 따라 `NodeDefinition`의 아래 3개 필드를 REQ-002 `CredentialInjectionService`가 필드 접근으로 사용:

| 필드 | 규칙 | 예시 |
|------|------|------|
| `service_type: Optional[str]` | 외부 서비스 식별자. snake_case 통일 | `"slack"`, `"google_workspace"`, `"microsoft_365"`, `"notion"`, `"openai"`, `"anthropic"`, `"linear"` |
| `required_connections: list[str]` | OAuth/API key 연결 요구 목록. service_type과 일관 | `["slack"]`, `["google"]`, `["microsoft"]`, `["notion"]` |
| `risk_level: RiskLevel` | 외부 시스템 쓰기=HIGH, 읽기=MEDIUM, 내부 처리=LOW | post/send/write → HIGH, read/list/get → MEDIUM |

**service_type ↔ required_connections 매핑** (Sprint 3 v1 표준):

| service_type | required_connections | 비고 |
|-------------|---------------------|------|
| `slack` | `["slack"]` | Slack OAuth |
| `google_workspace` | `["google"]` | Drive/Sheets/Docs/Gmail/Calendar 공통 |
| `microsoft_365` | `["microsoft"]` | Outlook/Teams/OneDrive 공통 |
| `notion` | `["notion"]` | Notion API key |
| `openai` | `["openai"]` | API key |
| `anthropic` | `["anthropic"]` | API key |
| `linear` | `["linear"]` | API key |
| `postgresql` / `mysql` / `bigquery` | `["database"]` 또는 서비스별 | 5/14에 확정 |

### 1.3 카테고리 매핑 (REQ-003 spec §노드 카탈로그 요약 기준)

| 신규 노드 | category 값 |
|----------|------------|
| Slack/Gmail/Outlook/Teams 송수신 | `"커뮤니케이션"` |
| Google Drive/OneDrive read/write | `"데이터 소스"` (read) / `"문서 생성"` (write) |
| Google Sheets/Docs read/write | `"데이터 소스"` (read) / `"문서 생성"` (write) |
| PostgreSQL/MySQL/BigQuery query | `"데이터 소스"` |
| OpenAI/Anthropic chat | `"AI / LLM"` |
| Notion page/db | `"외부 API 연동"` |
| Google Calendar/Linear issue | `"외부 API 연동"` |

> 카테고리 문자열은 spec의 한글 표기 그대로 사용 (예: `"조건 / 제어"` 공백 포함).

### 1.4 `node_type` 명명 규칙

```
{service}_{action}[_{object}]
```

- `slack_post_message`, `gmail_send`, `outlook_send`, `teams_post_message`
- `google_drive_read`, `google_sheets_read`, `google_docs_write`, `onedrive_read`
- `postgresql_query`, `bigquery_query`, `mysql_query`
- `openai_chat`, `anthropic_chat`
- `notion_create_page`, `google_calendar_create_event`, `linear_create_issue`

> `_NODE_TYPE` 문자열은 spec의 예시(`gmail_send`, `slack_post`)와 같은 snake_case 유지.

---

## 2. `process()` 구현 정책 (Sprint 3 1주차)

### 2.1 결정: **NotImplementedError stub**

Sprint 3 1주차 박아름 작업 scope는 **NodeDefinition 메타데이터 + BaseNode 상속 + dataclass Input/Output 정의**까지. 실제 API 호출은 **toolset(REQ-005) connector 또는 `ToolToNodeWrapper` 경유**로 향후 처리.

```python
class SlackPostMessageNode(BaseNode[SlackPostMessageInput, SlackPostMessageOutput]):
    metadata = NodeMetadata(...)
    input_schema = SlackPostMessageInput
    output_schema = SlackPostMessageOutput

    async def process(self, input: SlackPostMessageInput) -> SlackPostMessageOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "ToolToNodeWrapper로 BaseTool을 래핑하거나, execution_engine "
            "디스패처에서 service_type 기반 라우팅."
        )
```

### 2.2 사유

- **OAuth credential 주입**은 REQ-002 `CredentialInjectionService` 책임 — `process()` 시그니처에 credential 인자가 없음
- **toolset(REQ-005)이 같은 외부 서비스 connector를 따로 구현** (햄햄 5/12~5/17) — 중복 구현 회피
- Sprint 3 1주차 목표는 **카탈로그 등록**(검색·추천 가능 상태)이지 실행 동작이 아님

### 2.3 예외

`http_request` 같이 credential 불필요한 generic 노드는 기존처럼 `process()` 본체 구현 (참조: `http_request.py` line 48-66).

---

## 3. Plugin Discovery 패턴

### 3.1 현재 구조 (PR #30 머지본)

```
application/catalog_registry.py
  get_all_node_definitions() → list[NodeDefinition] (30종)
    = get_domain_node_definitions() (28종)
    + http_request() + pdf_generate() (2종)
```

- `domain/catalog/__init__.py`의 `get_domain_node_definitions()`이 data/control/trigger 28종 일괄 반환
- external 2종은 catalog_registry에서 명시 import 후 호출

### 3.2 신규 구조 (5/14 작업, `feature/req-003-plugin-discovery`)

**옵션 A — 단순 확장 (권장)**

`application/catalog_registry.py`에 신규 17종을 명시 import + append:

```python
# adapters/catalog/external/ 신규 17종을 import
from ..adapters.catalog.external.slack_post_message import get_node_definition as _slack_post_message
# ... (17 개)

def get_all_node_definitions() -> list[NodeDefinition]:
    return [
        *get_domain_node_definitions(),
        _http_request(), _pdf_generate(),
        _slack_post_message(), _gmail_send(), _outlook_send(), _teams_post_message(),  # 5/12
        _google_drive_read(), _google_sheets_read(), _google_docs_write(), _onedrive_read(),  # 5/13
        _postgresql_query(), _bigquery_query(), _mysql_query(),  # 5/14 Data
        _openai_chat(), _anthropic_chat(),  # 5/14 AI
        _notion_create_page(), _google_calendar_create_event(), _linear_create_issue(),  # 5/14 Productivity
    ]
```

**옵션 B — 자동 발견 (확장 가능하나 복잡)**

`adapters/catalog/registry.py` 신설 + `pkgutil.walk_packages`로 `external/` 하위 모듈 자동 import → `get_node_definition()` 함수 자동 수집.

```python
# adapters/catalog/registry.py
import importlib, pkgutil
from .. import external as _external_pkg

def discover_external_nodes() -> list[NodeDefinition]:
    nodes = []
    for _, name, _ in pkgutil.iter_modules(_external_pkg.__path__):
        mod = importlib.import_module(f"...adapters.catalog.external.{name}")
        if hasattr(mod, "get_node_definition"):
            nodes.append(mod.get_node_definition())
    return nodes
```

### 3.3 결정 (5/14에 확정)

**현재 1차 권장: 옵션 A (명시 import).** 이유:
- 노드 17종은 추적·테스트 용이성이 자동 발견보다 가치 높음
- ImportError 발생 시 디버깅 명확
- pkgutil 자동 발견은 PR #30 리뷰에서 reject된 패턴(역 import) 위험과 닿음

옵션 B는 Sprint 4 이후 노드 수 50종 초과 시 재검토.

---

## 4. UPSERT 흐름 (`RegisterNodesUseCase`)

이미 구현되어 있음 (`application/use_cases/register_nodes_use_case.py`):

```python
RegisterNodesUseCase(node_def_repo, embedder).execute(nodes)
  → embedder.embed_batch([n.description for n in nodes if n.embedding is None])
  → for each: node_def_repo.upsert(node)
  → 등록 건수 반환
```

### 4.1 호출 시점

| 시점 | 담당 |
|------|-----|
| api_server startup lifespan | 황대원 5/12-13 (api_server skeleton 작업과 같이) |
| Skills Builder 산업 default 등록 | 박아름 5/16 (`BuildFromIndustryDefaultUseCase` 본체) |
| Skills Builder SOP 추출 등록 | 박아름 5/16 (`BuildFromSOPUseCase` 본체) |

### 4.2 의존성

- `NodeDefinitionRepository` 구현체: `storage/repositories/PgNodeDefinitionRepository` (황대원 5/15)
- `EmbedderPort` 구현체: `ai_agent/adapters/llm/modal_embedding_adapter.py` (신정혜 5/13, **`llm-base` Modal 배포 5/12 저녁 의존**)
- 슬립 시 stub embedder (zeros 768d 또는 random) 사용 가능

---

## 5. 일자별 PR scope (재확인)

| 일자 | 브랜치 | scope | 산출물 |
|------|--------|-------|--------|
| 5/12 | `feature/req-003-catalog-communication` | Communication 4종 NodeDefinition + BaseNode (process stub) | 4 file in `external/` + catalog_registry append + unit test |
| 5/13 | `feature/req-003-catalog-document` | Document 4종 | 동일 |
| 5/14 | `feature/req-003-plugin-discovery` | Data 3 + AI 2 + Productivity 3 + (옵션 A 채택 시) catalog_registry 정리 + (선택) `adapters/catalog/registry.py` skeleton | 9 file + registry 정리 |
| 5/15 | `feature/req-003-catalog-misc` | 잔여 카테고리 (Webhook/Schedule/Filter/Transform 추가) + 산업 default seed 5종 (`modules/ai_agent/seeds/industry_defaults/*.json`) | n file + 5 JSON seed |

각 PR마다:
- ✅ NodeDefinition 등록 (`catalog_registry.py` import 추가)
- ✅ 기존 72/72 PASS 회귀 확인 (`pytest modules/nodes_graph/tests/`)
- ✅ 신규 노드별 unit test (메타데이터 + 직렬화)
- ✅ `process()` stub은 `pytest.raises(NotImplementedError)`로 회귀 방지 명시

---

## 6. Open Questions (5/12 sync에서 확정)

| 항목 | 누구와 | 시간 |
|------|--------|-----|
| doc_parser `DocumentBlock` 필드 (Skills Builder가 소비할 필드) | 김진형 | 5/12 09:00 (30분) |
| Inter-agent 통신 계약 (`agent_protocol.py`) | 신정혜, 햄햄 | 5/12 오후 (1h) |
| Database 노드(PostgreSQL/MySQL/BigQuery) `required_connections` 값 — 통합 `["database"]` vs 분리 | 황대원 (REQ-008 영향) | 5/14 작업 전 |
| Modal app 진입점 위치 (TASKS.md `adapters/modal/` vs spec 보류) | 황대원 | 조장이 sprint plan/REQ-011 손볼 예정 (5/11 카톡 합의) |

---

## 7. 임계 의존성

```
5/12 저녁 — 신정혜 llm-base Modal 배포
  ↓ (BGE-M3 endpoint 제공)
5/13 — 신정혜 ModalEmbeddingAdapter 구현 (EmbedderPort)
  ↓ (RegisterNodesUseCase의 embedder 의존)
5/14 — 박아름 plugin discovery + UPSERT 동작 검증
```

신정혜 슬립 시 박아름 5/14 작업은:
- catalog_registry 정리 + 노드 9종 추가는 진행 가능
- UPSERT 실행 검증은 stub embedder (zeros 768d)로 우회

---

## 8. spec 우선 원칙 (2026-05-11 확정)

- `docs/specs/`가 진본 (spec)
- `docs/specs/plan/sprint-3.md` plan은 일자별 분배
- `modules/*/TASKS.md`(조장 5/11 보존본)와 spec 충돌 시 spec 우선 — 5/11 조장 확인 완료
  - Repository 메서드: `.upsert()` (spec) — TASKS.md 수정 완료 (커밋 `b3936c2`)
  - Seed 위치: `modules/ai_agent/seeds/industry_defaults/` (spec) — TASKS.md 수정 완료
  - Modal app 위치: 조장이 sprint plan/REQ-011에서 처리 예정

---

## 9. 변경 이력

| 일자 | 변경 |
|------|------|
| 2026-05-11 | 초안 작성 (Plugin discovery 패턴 + 외부 노드 표준 + process stub 정책 + 5/12~5/15 PR scope) |
