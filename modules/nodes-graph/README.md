# nodes-graph

> REQ-003: 54종 노드 정의 카탈로그, 그래프 검증 (위상 정렬), 직렬화

## 설치

```bash
pip install -e modules/nodes-graph
pip install -e "modules/nodes-graph[dev]"
```

## Quick Start

```python
from nodes_graph.domain.entities import NodeDefinition
from nodes_graph.domain.services import GraphValidator, GraphSerializer
from nodes_graph.domain.ports import NodeDefinitionRepository
from nodes_graph.application.use_cases import ValidateGraphUseCase, SearchNodesUseCase
```

## Public API

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `NodeDefinition` | node_type, service_type, required_connections, risk_level, input_schema, output_schema | NodeConfig(REQ-012) 확장, 54종 노드 타입 정의 |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `GraphValidator` | `validate(workflow: WorkflowSchema) → ValidationErrorResponse` | 사이클 감지, 고립 노드, 타입 불일치, 필수 연결 누락 검출 |
| `GraphSerializer` | `serialize(workflow) → dict` / `deserialize(data) → WorkflowSchema` | 워크플로우 직렬화/역직렬화 |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `NodeDefinitionRepository` | `get_by_id(node_id) → NodeDefinition` | `storage/repositories/` |
| | `list_all(mvp_only: bool) → list[NodeDefinition]` | |
| | `search_by_embedding(query, limit) → list[NodeDefinition]` | |
| | `upsert(definition) → NodeDefinition` | |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ValidateGraphUseCase` | `WorkflowSchema → ValidationErrorResponse` | 워크플로우 그래프 무결성 검증 |
| `SearchNodesUseCase` | `query: str, limit: int → list[NodeDefinition]` | 벡터 임베딩 기반 노드 검색 |

### adapters

| 어댑터 | 설명 |
|--------|------|
| `ToolToNodeWrapper` | REQ-005 `BaseTool` → `NodeDefinition` 변환 래퍼 |

## 의존 관계

```
이 모듈 → common-schemas (WorkflowSchema, NodeConfig, NodeInstance, Edge, ValidationErrorResponse)
이 모듈 ← ai-agent (GraphValidator 호출, NodeRegistry 퍼사드로 래핑)
이 모듈 ← execution-engine (실행 시 위상 정렬)
이 모듈 ← storage (NodeDefinitionRepository 구현)
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| 없음 | — | 순수 도메인 로직, 환경 변수 불필요 |

## 노드 카탈로그 요약

| 카테고리 | MVP | 추후 |
|---------|:---:|:---:|
| 데이터 소스 | 5종 | ~13종 |
| 트리거 | 8종 | — |
| AI / LLM | 10종 | ~6종 |
| 데이터 처리 | 14종 | — |
| 조건 / 제어 | 8종 | — |
| 문서 생성 | 4종 | ~8종 |
| 커뮤니케이션 | 2종 | ~8종 |
| 외부 API 연동 | 3종 | ~2종 |
| **합계** | **54종** | **~37종** |

## 노드 인터페이스 표준

```python
class BaseNode(Generic[TInput, TOutput], ABC):
    metadata: NodeMetadata  # node_id, name, category, risk_level, is_mvp
    input_schema: type[TInput]
    output_schema: type[TOutput]

    @abstractmethod
    async def process(self, input: TInput) -> TOutput: ...
```

- `is_mvp` 플래그로 MVP/추후 노드 구분
- Plugin discovery: `nodes/` 패키지 자동 import → BGE-M3 임베딩 생성 → `node_definitions` UPSERT

## 검증 책임 분리

| 검증 유형 | 담당 |
|----------|------|
| DB 제약 조건 (FK, UNIQUE, NOT NULL) | 본 모듈 |
| 그래프 정적/의미적 검증 (순환, 타입 호환) | REQ-004 AI_Agent SchemaValidation |
| Runtime Validation | REQ-007 / REQ-005 |

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

## 외부 서비스 정책

- Google Workspace + Slack만 지원 (MVP)
- Microsoft (Outlook/OneDrive/Teams), Notion은 범위 외
- 외부 LLM API 호출 금지 — Gemma4 자체 호스팅만 사용

## 테스트

```bash
pytest modules/nodes-graph/tests/
```
