# REQ-003 Nodes-Graph — 구현 명세

- **담당자**: 박아름
- **작성일**: 2026-05-05
- **참조**: `docs/class_diagram_resolution_proposal.md` (H-1, H-4 확정), `modules/nodes_graph/README.md`

---

## common_schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `WorkflowSchema` | `common_schemas.workflow` | 워크플로우 전체 구조 (노드 + 엣지). GraphValidator 입력 타입 |
| `NodeInstance` | `common_schemas.workflow` | 워크플로우 내 노드 인스턴스. WorkflowSchema.nodes의 요소 |
| `NodeConfig` | `common_schemas.workflow` | 노드 설정 스키마. NodeDefinition의 상위 구조 참조 |
| `Edge` | `common_schemas.workflow` | 노드 간 연결. WorkflowSchema.connections의 요소 |
| `Position` | `common_schemas.workflow` | 캔버스 좌표 (x, y). NodeInstance.position 타입 |
| `RiskLevel` | `common_schemas.enums` | 노드 위험 등급 (Low/Medium/High/Restricted) |
| `ErrorCode` | `common_schemas.enums` | 그래프 검증 에러 코드 (E_CYCLE_DETECTED, E_ISOLATED_NODE 등) |
| `ValidationError` | `common_schemas.exceptions` | 스키마 검증 실패 시 raise |
| `NotFoundError` | `common_schemas.exceptions` | 노드 미발견 시 raise |
| `ValidationErrorItem` | `common_schemas.validation` | 개별 검증 에러 항목 |
| `ValidationErrorResponse` | `common_schemas.validation` | 검증 에러 응답 (items 리스트) |

```python
from common_schemas import (
    WorkflowSchema, NodeInstance, NodeConfig, Edge, Position,
    ValidationErrorItem, ValidationErrorResponse,
)
from common_schemas.enums import RiskLevel, ErrorCode
from common_schemas.exceptions import ValidationError, NotFoundError
```

**중요 (H-1 합의)**: 이 모듈은 WorkflowSchema, NodeInstance, Edge를 자체 정의하지 않는다. 반드시 common_schemas에서 import한다.

---

## 이 모듈에서 구현할 클래스

### Domain Layer (`modules/nodes_graph/domain/`)

#### entities/node_definition.py — `NodeDefinition`

```python
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID
from common_schemas.enums import RiskLevel

@dataclass
class NodeDefinition:
    """54종 노드 타입의 카탈로그 엔티티.
    
    NodeConfig(REQ-012)의 필드를 모두 포함하며,
    추가로 embedding, service_type 등 REQ-003 전용 필드를 확장한다.
    
    H-4 합의: REQ-002 CredentialInjectionService가 get_by_id() 후
    이 객체의 risk_level, required_connections, service_type을 필드 접근으로 사용한다.
    """
    # === NodeConfig 동일 필드 (REQ-012 참조) ===
    node_id: UUID
    node_type: str                          # e.g. "gmail_send", "slack_post", "llm_generate"
    name: str                               # 사람이 읽을 수 있는 이름
    category: str                           # DB CHECK 영문 8종: "trigger"|"action"|"condition"|"transform"|"ai"|"integration"|"utility"|"output"
    version: str                            # semver e.g. "1.0.0"
    input_schema: dict[str, Any]            # JSON Schema
    output_schema: dict[str, Any]           # JSON Schema
    parameter_schema: dict[str, Any]        # JSON Schema (사용자 설정 파라미터)
    risk_level: RiskLevel                   # REQ-002가 참조하는 필드
    required_connections: list[str]         # REQ-002가 참조 (e.g. ["google", "slack"])
    description: str                        # 노드 설명
    is_mvp: bool                            # MVP 54종 여부
    
    # === REQ-003 확장 필드 ===
    service_type: Optional[str] = None      # REQ-002가 참조 (e.g. "google_workspace")
    embedding: Optional[list[float]] = None # BGE-M3 벡터 (768차원) — 검색용
```

| 필드 | 타입 | REQ-002 참조 | 설명 |
|------|------|:---:|------|
| `node_id` | `UUID` | | 노드 정의 PK |
| `node_type` | `str` | | 고유 타입 식별자 |
| `name` | `str` | | 표시 이름 |
| `category` | `str` | | 카테고리 분류 |
| `version` | `str` | | 버전 (semver) |
| `input_schema` | `dict[str, Any]` | | 입력 JSON Schema |
| `output_schema` | `dict[str, Any]` | | 출력 JSON Schema |
| `parameter_schema` | `dict[str, Any]` | | 파라미터 JSON Schema |
| `risk_level` | `RiskLevel` | YES | 위험 등급 |
| `required_connections` | `list[str]` | YES | 필수 외부 서비스 연결 |
| `description` | `str` | | 노드 설명 |
| `is_mvp` | `bool` | | MVP 포함 여부 |
| `service_type` | `Optional[str]` | YES | 외부 서비스 유형 |
| `embedding` | `Optional[list[float]]` | | BGE-M3 임베딩 벡터 |

---

#### entities/node_metadata.py — `NodeMetadata`

```python
@dataclass(frozen=True)
class NodeMetadata:
    """BaseNode 추상 클래스의 메타데이터."""
    node_id: UUID
    name: str
    category: str
    risk_level: RiskLevel
    is_mvp: bool
```

---

#### entities/base_node.py — `BaseNode` (ABC, Generic)

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")

class BaseNode(Generic[TInput, TOutput], ABC):
    """모든 노드의 추상 기본 클래스.
    
    54종 노드가 이 클래스를 상속하여 process()를 구현한다.
    """
    metadata: NodeMetadata
    input_schema: type[TInput]
    output_schema: type[TOutput]
    
    @abstractmethod
    async def process(self, input: TInput) -> TOutput:
        """노드 로직 실행. Input → Output 변환."""
        ...
```

---

#### services/graph_validator.py — `GraphValidator`

```python
class GraphValidator:
    """워크플로우 그래프 무결성 검증 서비스.
    
    검증 항목:
    1. 사이클 감지 (Kahn's algorithm 기반 위상 정렬)
    2. 고립 노드 검출 (연결 없는 노드)
    3. 노드 타입 불일치 (from_handle ↔ to_handle 타입 호환)
    4. 중복 instance_id 검출
    5. 필수 연결 누락 (required_connections 확인)
    """
    
    def __init__(self, node_def_repo: NodeDefinitionRepository):
        ...
    
    async def validate(self, workflow: WorkflowSchema) -> ValidationErrorResponse:
        """
        전체 검증 수행 후 ValidationErrorResponse 반환.
        errors가 비어있으면 유효한 그래프.
        
        반환 예시:
        ValidationErrorResponse(errors=[
            ValidationErrorItem(field="connections[0]", message="Cycle detected", code="E_CYCLE_DETECTED"),
        ])
        """
        ...
    
    def _detect_cycles(self, nodes: list[NodeInstance], edges: list[Edge]) -> list[ValidationErrorItem]:
        """Kahn's algorithm으로 위상 정렬. 정렬 불가 시 사이클."""
        ...
    
    def _detect_isolated_nodes(self, nodes: list[NodeInstance], edges: list[Edge]) -> list[ValidationErrorItem]:
        """연결이 하나도 없는 노드 검출."""
        ...
    
    def _check_type_compatibility(self, edges: list[Edge]) -> list[ValidationErrorItem]:
        """from_handle 출력 타입과 to_handle 입력 타입 호환 검증."""
        ...
    
    def _check_duplicate_ids(self, nodes: list[NodeInstance]) -> list[ValidationErrorItem]:
        """instance_id 중복 검출."""
        ...
```

---

#### services/graph_serializer.py — `GraphSerializer`

```python
class GraphSerializer:
    """워크플로우 직렬화/역직렬화 서비스."""
    
    def serialize(self, workflow: WorkflowSchema) -> dict:
        """WorkflowSchema → JSON-serializable dict.
        Pydantic model_dump() 래핑 + 커스텀 직렬화 로직."""
        ...
    
    def deserialize(self, data: dict) -> WorkflowSchema:
        """dict → WorkflowSchema.
        Pydantic model_validate() 래핑 + 추가 검증."""
        ...
```

---

#### ports/node_definition_repository.py — `NodeDefinitionRepository` (ABC)

```python
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

class NodeDefinitionRepository(ABC):
    """노드 정의 카탈로그 저장소 인터페이스.
    
    구현은 REQ-008(storage) / REQ-001(database)이 담당.
    
    H-4 합의: REQ-002가 필요한 risk_level, required_connections, service_type은
    get_by_id() 반환값인 NodeDefinition 객체의 필드로 접근한다.
    별도 get_risk_level(), get_service_type() 등의 메서드를 추가하지 않는다.
    """
    
    @abstractmethod
    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        """노드 정의 생성 또는 갱신. 
        Plugin discovery 시 54종 노드를 일괄 등록할 때 사용."""
        ...
    
    @abstractmethod
    async def list_all(self, mvp_only: bool = False) -> list[NodeDefinition]:
        """전체 노드 목록 조회.
        mvp_only=True면 is_mvp=True인 노드만 반환."""
        ...
    
    @abstractmethod
    async def get_by_id(self, node_id: UUID) -> Optional[NodeDefinition]:
        """node_id로 단일 노드 정의 조회.
        REQ-002 CredentialInjectionService가 이 메서드를 사용한다."""
        ...
    
    @abstractmethod
    async def search_by_embedding(self, query_embedding: list[float], limit: int = 10) -> list[NodeDefinition]:
        """벡터 유사도 기반 노드 검색.
        AI Agent(REQ-004)의 노드 추천에 사용.
        pgvector cosine similarity 활용."""
        ...
```

---

### Application Layer (`modules/nodes_graph/application/`)

#### use_cases/validate_graph_use_case.py — `ValidateGraphUseCase`

```python
class ValidateGraphUseCase:
    """워크플로우 그래프 무결성 검증 유스케이스."""
    
    def __init__(self, validator: GraphValidator):
        ...
    
    async def execute(self, workflow: WorkflowSchema) -> ValidationErrorResponse:
        """
        1. workflow.validate_graph() — 기본 참조 무결성 (common_schemas 내장)
        2. GraphValidator.validate() — 정적/의미적 검증
        3. ValidationErrorResponse 반환
        """
        ...
```

---

#### use_cases/search_nodes_use_case.py — `SearchNodesUseCase`

```python
class SearchNodesUseCase:
    """벡터 임베딩 기반 노드 검색 유스케이스."""
    
    def __init__(self, node_def_repo: NodeDefinitionRepository, embedder: EmbedderPort):
        ...
    
    async def execute(self, query: str, limit: int = 10) -> list[NodeDefinition]:
        """
        1. embedder.embed(query) → query_embedding (768차원)
        2. node_def_repo.search_by_embedding(query_embedding, limit)
        3. 결과 반환
        """
        ...
```

---

#### use_cases/register_nodes_use_case.py — `RegisterNodesUseCase`

```python
class RegisterNodesUseCase:
    """Plugin discovery로 노드를 일괄 등록하는 유스케이스."""
    
    def __init__(self, node_def_repo: NodeDefinitionRepository, embedder: EmbedderPort):
        ...
    
    async def execute(self, nodes: list[NodeDefinition]) -> int:
        """
        1. 각 노드에 대해 embedding 생성 (없는 경우)
        2. node_def_repo.upsert(definition) 호출
        3. 등록된 건수 반환
        """
        ...
```

---

#### application/catalog_registry.py — `CatalogRegistry`

```python
class CatalogRegistry:
    """카탈로그 전체 NodeDefinition 조립 클래스.

    domain/catalog/* 개별 노드 + adapters/catalog/external/* 노드를
    application 레이어에서 조립한다.
    domain/__init__.py에서 adapter를 import하면 Clean Architecture 위반이므로
    반드시 이 클래스를 통해 조립한다 (PR #30 리뷰 확정, PR #34 spec 반영).
    """

    def get_all_node_definitions(self) -> list[NodeDefinition]:
        """카탈로그 전체 30종 NodeDefinition 반환.
        RegisterNodesUseCase.execute()의 입력으로 사용."""
        ...
```

---

### Infrastructure/Adapter Layer (`modules/nodes_graph/adapters/`)

#### tool_to_node_wrapper.py — `ToolToNodeWrapper`

```python
class ToolToNodeWrapper:
    """REQ-005 BaseTool → REQ-003 BaseNode 변환 어댑터.
    
    REQ-005 toolset 모듈의 BaseTool 인터페이스를 REQ-003의 BaseNode 인터페이스로
    래핑하여, 기존 도구를 워크플로우 노드로 사용할 수 있게 한다.
    """
    
    def __init__(self, tool: "BaseTool"):  # REQ-005의 BaseTool
        """
        tool의 메타데이터로부터 NodeMetadata 생성:
        - tool.tool_id → node_id
        - tool.name → name
        - tool.risk_level → risk_level
        - tool.input_schema → input_schema
        - tool.output_schema → output_schema
        """
        ...
    
    async def process(self, input: dict) -> dict:
        """
        tool.run(params, credential) 호출을 BaseNode.process() 시그니처로 래핑.
        credential은 CredentialInjectionService를 통해 주입받아야 하므로
        input에 credential 정보가 포함되어야 한다.
        """
        ...
    
    def to_node_definition(self) -> NodeDefinition:
        """BaseTool의 메타데이터로 NodeDefinition 엔티티 생성.
        RegisterNodesUseCase에서 카탈로그 등록 시 사용."""
        ...
```

---

#### ports/embedder_port.py — `EmbedderPort` (ABC)

```python
from abc import ABC, abstractmethod

class EmbedderPort(ABC):
    """텍스트 → 벡터 임베딩 변환 인터페이스.
    구현체: BGE-M3 모델 (768차원) — modules/ai_agent 또는 외부 서비스.
    ⚠️ 임베딩 차원 변경 시 storage ORM의 Vector 컬럼도 반드시 동기화 (REQ-008)."""
    
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """텍스트를 768차원 벡터로 변환."""
        ...
    
    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩. Plugin discovery 시 54종 노드 일괄 임베딩에 사용."""
        ...
```

---

## 합의된 변경사항 (클래스 다이어그램 교차분석)

| 이슈 ID | 합의 내용 | 이 모듈에 미치는 영향 |
|---------|-----------|---------------------|
| **H-1** | REQ-003의 자체 WorkflowSchema/NodeInstance/Edge 정의 삭제 → REQ-012 import | 자체 정의 전면 삭제. `from common_schemas import WorkflowSchema, NodeInstance, Edge, Position` 사용 |
| **H-1** | REQ-012 WorkflowSchema에 `description: Optional[str]` 추가 | 이 모듈은 description 필드를 활용 가능 (추가 작업 불필요) |
| **H-1** | NodeInstance.instance_id `str→UUID`, position `dict→Position` 통일 | 이 모듈의 코드가 UUID, Position 타입 기준으로 작성됨 |
| **H-4** | NodeDefinitionRepository에 get_service_type/get_risk_level/get_required_connections 메서드 추가 안 함 | `get_by_id()` 반환값인 NodeDefinition에 해당 필드가 존재함을 명시 |
| **H-4** | REQ-002가 `get_by_id()` 후 필드 접근으로 사용 | NodeDefinition에 `risk_level`, `required_connections`, `service_type` 필드 필수 포함 확인 |

---

## 의존성 관계

```
Upstream (이 모듈이 의존):
  ├── packages/common_schemas (REQ-012)
  │     └── WorkflowSchema, NodeInstance, NodeConfig, Edge, Position
  │     └── RiskLevel, ErrorCode
  │     └── ValidationErrorItem, ValidationErrorResponse
  └── modules/toolset (REQ-005) [Optional — ToolToNodeWrapper용]
        └── BaseTool (어댑터에서 래핑 대상)

Downstream (이 모듈에 의존):
  ├── modules/auth (REQ-002)
  │     └── NodeDefinitionRepository ABC import
  │     └── CredentialInjectionService가 get_by_id() → NodeDefinition 필드 접근
  ├── modules/ai_agent (REQ-004) — Workflow Composer
  │     └── GraphValidator 호출 (워크플로우 생성/수정 시 검증)
  │     └── SearchNodesUseCase (노드 추천)
  ├── modules/ai_agent (REQ-004) — Skills Builder
  │     └── NodeDefinitionRepository.upsert() 호출 — SOP 문서/산업 default에서 추출한
  │        SkillNode를 NodeDefinition으로 변환해 카탈로그에 등록
  │        (BuildFromSOPUseCase, BuildFromIndustryDefaultUseCase)
  ├── services/execution_engine (REQ-007)
  │     └── 위상 정렬로 실행 순서 결정
  ├── services/api_server (REQ-009)
  │     └── 노드 목록 조회, 그래프 검증 엔드포인트
  └── modules/storage (REQ-008) / database (REQ-001)
        └── NodeDefinitionRepository 구현체 제공
```

---

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| 없음 | — | 순수 도메인 로직 모듈. 환경 변수 불필요. 임베딩 모델 설정은 EmbedderPort 구현체(별도 모듈)가 관리 |

---

## 디렉토리 구조 (목표)

```
modules/nodes_graph/
├── __init__.py
├── domain/
│   ├── entities/
│   │   ├── node_definition.py      # NodeDefinition
│   │   ├── node_metadata.py        # NodeMetadata
│   │   └── base_node.py            # BaseNode (ABC, Generic)
│   ├── services/
│   │   ├── graph_validator.py      # GraphValidator
│   │   └── graph_serializer.py     # GraphSerializer
│   └── ports/
│       ├── node_definition_repository.py  # NodeDefinitionRepository (ABC)
│       └── embedder_port.py        # EmbedderPort (ABC)
├── application/
│   └── use_cases/
│       ├── validate_graph_use_case.py
│       ├── search_nodes_use_case.py
│       └── register_nodes_use_case.py
├── adapters/
│   └── tool_to_node_wrapper.py     # ToolToNodeWrapper (REQ-005 어댑터)
└── tests/
    ├── test_graph_validator.py
    ├── test_node_definition.py
    ├── test_search_nodes.py
    └── test_tool_to_node_wrapper.py
```

---

## 노드 카탈로그 요약 (Sprint 3 1주차 — 55종)

> 카테고리는 DB `node_definitions.category` CHECK 제약(영문 8종: `trigger`, `action`, `condition`, `transform`, `ai`, `integration`, `utility`, `output`)에 맞춤. Microsoft(Outlook/Teams/OneDrive), Notion, OpenAI는 데모 버전 후속 개발로 보류 (2026-05-11 조장 결정).
>
> 박아름 1주차 작업분 41종(28 domain + 13 external) + 박아름 5/14 야간 추가 `gemma_chat` 1종 (PR #68) + 햄햄(가원) toolset 영역 연결분 14종(REQ-005 toolset → nodes_graph 카탈로그) = **합계 56종**. toolset 연결은 햄햄 commit `59f0e26 feat(toolset+nodes_graph): toolset 14종 tool 노드를 nodes_graph 카탈로그에 연결`로 머지됨.

| 카테고리 | 종수 | 박아름 1주차 (41) + 5/14 (1) | + 햄햄 toolset (14) |
|---------|:---:|------|------|
| `trigger` | 6 | `schedule_trigger`, `webhook_trigger`, `manual_trigger`, `event_trigger`, `api_poll_trigger`, `file_watch_trigger` | — |
| `condition` | 10 | `if_condition`, `switch_case`, `loop_count`, `loop_list`, `retry`, `merge_branch`, `stop_workflow`, `delay` | + `conditional`, `loop` |
| `transform` | 18 | `text_transform`, `json_extract`, `json_merge`, `csv_parse`, `csv_build`, `number_calc`, `date_format`, `list_filter`, `list_map`, `string_template`, `regex_extract`, `regex_replace`, `base64_encode`, `base64_decode` | + `file_transform`, `json_transform`, `text_template`, `data_mapping` |
| `ai` | 2 (+후속) | `anthropic_chat` (외부 LLM, API key 자격증명), `gemma_chat` (시스템 내장 Gemma 4, 자격증명 불필요 — 5/14 야간 추가) — `openai_chat`은 데모 후속 보류 | — |
| `integration` | 11 | `http_request`, `google_drive_read`, `google_sheets_read`, `postgresql_query`, `mysql_query`, `bigquery_query`, `google_calendar_create_event`, `linear_create_issue` | + `rest_api`, `graphql`, `http_request_tool` |
| `output` | 2 | `pdf_generate`, `google_docs_write` | — |
| `action` | 5 (+후속) | `slack_post_message`, `gmail_send` (Microsoft `outlook_send`/`teams_post_message` 후속 보류) | + `webhook`, `slack_notify`, `email_send` |
| `utility` | 2 | (박아름 1주차엔 utility 분류 없음) | + `file_read`, `file_write` |
| **합계** | **56** | **42** (28 domain + 14 external, gemma_chat 포함) | **+14** (toolset) |

각 노드는 `BaseNode`를 상속하고, Plugin discovery 시 자동으로 `NodeDefinition` + BGE-M3 임베딩이 생성되어 `node_definitions` 테이블에 UPSERT된다. toolset 14종은 `modules/nodes_graph/adapters/catalog/tools/toolset_nodes.py`에서 `NodeDefinition` 형태로 정의되어 `catalog_registry.py`로 통합 등록된다.
