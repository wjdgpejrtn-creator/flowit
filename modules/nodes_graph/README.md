# nodes_graph

> REQ-003: 53종 노드 정의 카탈로그, 그래프 검증 (위상 정렬), 직렬화
>
> 구현 명세 → [`docs/specs/REQ-003-nodes_graph.md`](../../docs/specs/REQ-003-nodes_graph.md)

## 설치

```bash
pip install -e modules/nodes_graph
pip install -e "modules/nodes_graph[dev]"
```

## Quick Start

```python
from nodes_graph.domain.entities import NodeDefinition, NodeMetadata, BaseNode
from nodes_graph.domain.services import GraphValidator, GraphSerializer
from nodes_graph.domain.ports import NodeDefinitionRepository, EmbedderPort
from nodes_graph.application.use_cases import (
    ValidateGraphUseCase,
    SearchNodesUseCase,
    RegisterNodesUseCase,
)
```

## Public API

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `NodeDefinition` | `node_id: UUID`, `node_type: str`, `name: str`, `category: str`, `version: str`, `input_schema: dict`, `output_schema: dict`, `parameter_schema: dict`, `risk_level: RiskLevel`, `required_connections: list[str]`, `description: str`, `is_mvp: bool`, `service_type: Optional[str]`, `embedding: Optional[list[float]]`, `owner_user_id: Optional[UUID]`, `team_id: Optional[UUID]` | NodeConfig(REQ-012) 확장. REQ-002가 `risk_level`, `required_connections`, `service_type`을 필드 접근으로 사용 (H-4 합의). `owner_user_id`/`team_id`는 ADR-0020 (i) scope 격리(None=company 전역, 기존 53종 비침습) |
| `NodeMetadata` | `node_id: UUID`, `name: str`, `category: str`, `risk_level: RiskLevel`, `is_mvp: bool` | BaseNode의 메타데이터 (frozen) |
| `BaseNode` | `metadata: NodeMetadata`, `input_schema: type[TInput]`, `output_schema: type[TOutput]` | 모든 노드의 ABC. `Generic[TInput, TOutput]`. `async process(input: TInput, context: NodeContext) → TOutput` 구현 필요 (`context` = ADR-0018 실행 컨텍스트, common_schemas) |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `GraphValidator` | `async validate(workflow: WorkflowSchema) → ValidationErrorResponse` | 사이클 감지, 고립 노드, 타입 불일치, 중복 ID, 필수 연결 누락 검증. 생성자에 `NodeDefinitionRepository` 주입 필요 |
| `GraphSerializer` | `serialize(workflow: WorkflowSchema) → dict`, `deserialize(data: dict) → WorkflowSchema` | Pydantic model_dump/model_validate 래핑 |

### domain/ports (인터페이스 — 구현체는 `modules/storage`)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `NodeDefinitionRepository` | `async upsert(definition: NodeDefinition) → NodeDefinition` | `storage/repositories/` |
| | `async list_all(mvp_only: bool = False) → list[NodeDefinition]` | |
| | `async get_by_id(node_id: UUID) → Optional[NodeDefinition]` | |
| | `async search_by_embedding(query_embedding: list[float], limit: int = 10, viewer_user_id: Optional[UUID] = None, viewer_team_ids: Optional[list[UUID]] = None) → list[NodeDefinition]` | viewer scope 격리(ADR-0020 (i)): None=전역만, 지정 시 전역+본인 personal+소속 team |
| `EmbedderPort` | `async embed(text: str) → list[float]` | 외부 구현 (BGE-M3, 768차원) |
| | `async embed_batch(texts: list[str]) → list[list[float]]` | |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ValidateGraphUseCase` | `WorkflowSchema → ValidationErrorResponse` | 그래프 무결성 검증 |
| `SearchNodesUseCase` | `query: str, limit: int → list[NodeDefinition]` | 벡터 임베딩 기반 노드 검색 |
| `RegisterNodesUseCase` | `nodes: list[NodeDefinition] → int` | Plugin discovery 노드 일괄 등록. 임베딩 자동 생성 후 upsert |

### adapters

| 어댑터 | 설명 |
|--------|------|
| `catalog/external/*` | 25종 NodeDefinition + BaseNode 파일. ADR-0018 Phase 3d 완료로 25종 전부 `process()` 실구현 (transform/api·messaging·LLM/Linear·DB·Google·file·http_request·pdf_generate). `NotImplementedError` 스텁 없음 |
| `catalog/registry.py` | Plugin discovery 진입점 (`discover_and_register`) |

> **`ToolToNodeWrapper` 제거 — 2026-05-19 박아름 toolset 정리 PR**: 5/15 햄햄·박아름 합의 + 5/19 조장 안. toolset 14종 중 중복 3종(`http_request_tool`/`conditional`/`loop`)은 양쪽 제거, 나머지 11종은 `external/`에 개별 파일로 직접 등록.

## 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common_schemas (REQ-012)
  │     └── WorkflowSchema, NodeInstance, NodeConfig, Edge, Position
  │     └── RiskLevel, ErrorCode, ValidationErrorItem, ValidationErrorResponse
  └── toolset (REQ-005) — 직접 import 없음.
        external 노드 실행은 execution_engine.CatalogNodeExecutor가 node_type으로
        BaseNode.process()를 직접 호출 (ADR-0018 — ToolsetExecutor 경로 폐기).

Downstream (이 모듈에 의존):
  ├── auth (REQ-002)            → NodeDefinitionRepository ABC import (CredentialInjectionService)
  ├── ai_agent (REQ-004)        → GraphValidator 호출, NodeRegistry 퍼사드로 래핑
  ├── execution_engine (REQ-007) → 실행 시 위상 정렬
  ├── api_server (REQ-009)      → 노드 목록 조회, 그래프 검증 엔드포인트
  └── storage (REQ-008)         → NodeDefinitionRepository 구현체 제공
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| 없음 | — | 순수 도메인 로직. 임베딩 설정은 EmbedderPort 구현체가 관리 |

## 노드 카탈로그 요약 (53종 MVP)

> 상세 분류는 `docs/specs/REQ-003-nodes-graph.md` §"노드 카탈로그 요약" 참조. 28 domain + 25 external (기존 14 + REQ-005 toolset 연동 11).

| 카테고리 | MVP | 예시 node_type |
|---------|:---:|------|
| 데이터 소스 | 5종 | `google_drive_read`, `google_sheets_read` |
| 트리거 | 8종 | `schedule_trigger`, `webhook_trigger`, `gmail_trigger` |
| AI / LLM | 10종 | `llm_generate`, `llm_summarize`, `embedding_create` |
| 데이터 처리 | 14종 | `json_transform`, `text_split`, `merge_data` |
| 조건 / 제어 | 8종 | `if_condition`, `switch_case`, `loop_for_each` |
| 문서 생성 | 4종 | `google_docs_write`, `pdf_generate` |
| 커뮤니케이션 | 2종 | `gmail_send`, `slack_post` |
| 외부 API 연동 | 3종 | `http_request`, `google_calendar_create` |

## 에러 코드

| 코드 | 의미 | HTTP |
|------|------|------|
| E-NODE-001 | 존재하지 않는 노드 타입 | 404 |
| E-NODE-002 | 노드 파라미터 스키마 불일치 | 422 |
| E-NODE-003 | 권한 없는 노드 사용 시도 | 403 |
| E-NODE-004 | 외부 서비스 연결 누락 (credential_id) | 422 |
| E-NODE-005 | 추후 노드 사용 시도 (MVP 단계 차단) | 403 |
| E-WF-001 | 워크플로우 찾을 수 없음 | 404 |
| E-WF-002 | 소유자 아님 (Ownership 위반) | 403 |
| E-WF-003 | 워크플로우 스키마 검증 실패 | 422 |
| E-WF-004 | 그래프 무결성 위반 | 422 |

## 테스트

```bash
pytest modules/nodes_graph/tests/
```
