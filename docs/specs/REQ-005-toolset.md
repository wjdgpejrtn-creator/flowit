# REQ-005 Toolset — 구현 명세

> **담당**: 햄햄  
> **모듈 경로**: `modules/toolset/`  
> **기준 문서**: 클래스 다이어그램 교차분석 확정본 (2026-05-05)

---

## common-schemas에서 import할 클래스

아래 타입은 `packages/common-schemas`(REQ-012)에서 정의된 SSOT이다. **절대로 모듈 내 재정의 금지.**

| 클래스명 | 소스 모듈 | import 경로 | 용도 |
|----------|-----------|-------------|------|
| `RiskLevel` | `common_schemas.enums` | `from common_schemas.enums import RiskLevel` | 도구별 위험도 Enum (Low, Medium, High, Restricted). `BaseTool.risk_level` 필드에 사용 |
| `NodeConfig` | `common_schemas.workflow` | `from common_schemas import NodeConfig` | 노드 정의/설정 스키마. 도구가 어떤 노드에 바인딩되는지 참조할 때 사용 |
| `ErrorCode` | `common_schemas.enums` | `from common_schemas.enums import ErrorCode` | 도구 실행 에러 분류 코드 (E_NODE_TYPE_MISMATCH, E_PERMISSION_DENIED 등) |

---

## 이 모듈에서 구현할 클래스

### Domain Layer (`domain/`)

#### `domain/entities/`

| 클래스명 | 설명 | 주요 필드/메서드 |
|----------|------|-----------------|
| `ToolExecutionRecord` | 도구 실행 결과 기록 엔티티 | `execution_id: UUID`, `tool_name: str`, `input_data: dict`, `output_data: Optional[dict]`, `status: Literal["success", "failed", "timeout"]`, `error_message: Optional[str]`, `duration_ms: int`, `executed_at: datetime` |
| `ToolMetadata` | 도구 카탈로그 메타데이터 | `tool_id: UUID`, `name: str`, `version: str`, `category: str`, `risk_level: RiskLevel`, `input_schema: dict[str, Any]`, `output_schema: dict[str, Any]`, `description: str`, `is_enabled: bool` |

#### `domain/value_objects/`

| 클래스명 | 설명 | 비고 |
|----------|------|------|
| `ToolInput` | 검증된 도구 입력 (불변) | `data: dict[str, Any]`, `schema_version: str` |
| `ToolOutput` | 검증된 도구 출력 (불변) | `data: dict[str, Any]`, `metadata: dict[str, Any]` |
| `ExecutionTimeout` | 도구별 타임아웃 설정 | `seconds: int`, `DEFAULT = 30`, `MAX = 300` |

#### `domain/services/`

| 클래스명 | 설명 | 주요 메서드 | 의존성 |
|----------|------|-------------|--------|
| `RuntimeValidator` | 도구 실행 시점 I/O 스키마 검증 | `validate_input(data: dict, schema: dict) -> ToolInput`, `validate_output(data: dict, schema: dict) -> ToolOutput` | 없음 (순수 로직, jsonschema 사용) |
| `ToolExecutionService` | 도구 실행 오케스트레이션 (검증→실행→검증) | `execute(tool: BaseTool, input_data: dict) -> ToolOutput` | `RuntimeValidator`, `BaseTool` |
| `RiskAssessmentService` | 실행 전 리스크 평가 | `assess(tool: BaseTool, context: PermissionSource) -> bool` | 없음 (순수 비즈니스 규칙) |

> **RuntimeValidator vs QAEvaluatorService (REQ-004) 역할 구분**:
> - `RuntimeValidator`: 도구 하나의 실행 시점에서 입력/출력 데이터가 해당 도구의 JSON Schema에 맞는지 "데이터 타입 검증" (per-tool, 구조적 검증)
> - `QAEvaluatorService`: 워크플로우 전체 "초안 품질"을 LLM으로 평가 (의미적 평가, score >= 8 통과)

#### `domain/ports/`

| 포트(ABC) | 설명 | 주요 메서드 | Adapter 구현 위치 |
|-----------|------|-------------|-------------------|
| `ToolRegistry` | 등록된 도구 목록 관리 | `get(tool_name: str) -> BaseTool`, `list_all() -> list[ToolMetadata]`, `list_by_category(category: str) -> list[ToolMetadata]` | `adapters/tool_registry_adapter.py` |
| `SecureConnectorPort` | 외부 API 호출 시 인증 주입 | `connect(endpoint: str, credentials: PlaintextCredential, **kwargs) -> httpx.Response` | `adapters/secure_connector.py` |
| `ToolExecutionRepository` | 실행 이력 저장 | `save(record: ToolExecutionRecord) -> None`, `find_by_tool(tool_name: str, limit: int) -> list[ToolExecutionRecord]` | `modules/storage/repositories/` |

---

### Application Layer (`application/`)

#### `application/use_cases/`

| 유스케이스 | 설명 | 입력 | 출력 | 호출하는 서비스/포트 |
|-----------|------|------|------|---------------------|
| `ExecuteToolUseCase` | 단일 도구 실행 (REQ-007 실행 엔진에서 호출) | `tool_name: str`, `input_data: dict`, `context: PermissionSource` | `ToolOutput` | `ToolRegistry`, `RuntimeValidator`, `ToolExecutionService`, `RiskAssessmentService`, `ToolExecutionRepository` |
| `ListToolsUseCase` | 도구 카탈로그 조회 | `category: Optional[str]`, `risk_level: Optional[RiskLevel]` | `list[ToolMetadata]` | `ToolRegistry` |
| `ValidateToolConfigUseCase` | 도구 설정 유효성 사전 검증 (드래프트 단계) | `tool_name: str`, `parameters: dict` | `bool` (+ 에러 목록) | `ToolRegistry`, `RuntimeValidator` |

---

### Adapters Layer (`adapters/`)

| 어댑터 | 설명 | 구현하는 Port | 외부 의존성 |
|--------|------|---------------|-------------|
| `ToolRegistryAdapter` | 도구 인스턴스 관리 (등록/검색) | `ToolRegistry` | 없음 (in-memory 또는 config 기반) |
| `SecureConnectorAdapter` | httpx 기반 외부 API 호출 + 인증 주입 | `SecureConnectorPort` | `httpx`, auth의 `CredentialInjectionService` |

---

### BaseTool ABC 및 구체 Tool 구현체

#### `domain/base_tool.py` — BaseTool ABC

```python
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from common_schemas.enums import RiskLevel


class BaseTool(ABC):
    """모든 도구의 기본 추상 클래스."""

    @property
    @abstractmethod
    def name(self) -> str:
        """도구 고유 이름."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """도구 버전 (semver)."""
        ...

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel:
        """도구 위험도 등급 (common-schemas에서 import)."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """입력 JSON Schema 정의."""
        ...

    @property
    @abstractmethod
    def output_schema(self) -> dict[str, Any]:
        """출력 JSON Schema 정의."""
        ...

    @abstractmethod
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        """도구 실행. RuntimeValidator가 호출 전후로 I/O를 검증한다."""
        ...
```

#### 구체 Tool 구현체 (~15개 클래스)

아래는 구현해야 할 구체 도구 목록이다. 모두 `BaseTool`을 상속한다.

| 카테고리 | 클래스명 | risk_level | 설명 |
|----------|----------|------------|------|
| **API 호출** | `HttpRequestTool` | Medium | 범용 HTTP 요청 (GET/POST/PUT/DELETE) |
| **API 호출** | `RestApiTool` | Medium | REST API 호출 + 응답 파싱 |
| **API 호출** | `GraphqlTool` | Medium | GraphQL 쿼리/뮤테이션 실행 |
| **API 호출** | `WebhookTool` | Low | 웹훅 발송 (fire-and-forget) |
| **파일 처리** | `FileReadTool` | Low | 파일 읽기 (텍스트/바이너리) |
| **파일 처리** | `FileWriteTool` | Medium | 파일 쓰기/생성 |
| **파일 처리** | `FileTransformTool` | Low | 파일 포맷 변환 (CSV↔JSON, Excel→CSV 등) |
| **데이터 변환** | `JsonTransformTool` | Low | JMESPath/JSONPath 기반 JSON 변환 |
| **데이터 변환** | `TextTemplateTool` | Low | Jinja2 템플릿 렌더링 |
| **데이터 변환** | `DataMappingTool` | Low | 필드 매핑/리네이밍 |
| **조건/제어** | `ConditionalTool` | Low | 조건 분기 (if/else 로직) |
| **조건/제어** | `LoopTool` | Medium | 반복 실행 (배열 순회) |
| **조건/제어** | `DelayTool` | Low | 대기/지연 (sleep) |
| **알림** | `EmailSendTool` | High | 이메일 발송 |
| **알림** | `SlackNotifyTool` | Medium | Slack 메시지 전송 |

> **구현 위치**: `adapters/tools/` 디렉토리에 카테고리별 서브폴더로 배치한다.

---

## 합의된 변경사항 (클래스 다이어그램 교차분석)

| 항목 | 변경 전 | 변경 후 | 사유 |
|------|---------|---------|------|
| BaseTool.risk_level 타입 | 자체 Enum 정의 | `RiskLevel` (REQ-012 import) | SSOT 원칙 — common-schemas에 단일 정의 |
| RuntimeValidator 역할 | 모호 | "도구 실행 시점 I/O 스키마 검증"으로 명확화 | QAEvaluatorService(REQ-004)와 역할 중복 방지 |
| NodeDef 참조 | 자체 타입 | `NodeConfig` (REQ-012 import) | 클래스명 통일 |
| ErrorCode | 자체 정의 | REQ-012에서 import | 에러 코드 전역 통일 |

---

## 의존성 관계

### 이 모듈이 import하는 대상

```python
# common-schemas (REQ-012) — 공유 타입
from common_schemas import NodeConfig
from common_schemas.enums import RiskLevel, ErrorCode
from common_schemas.exceptions import ExecutionError, ValidationError

# auth (REQ-002) — domain/services만 허용
from auth.domain.services import CredentialInjectionService

# common-schemas 보안 타입
from common_schemas import PermissionSource, PlaintextCredential
```

### 이 모듈의 Port를 구현하는 외부 모듈

| Port | 구현 모듈 |
|------|-----------|
| `ToolExecutionRepository` | `modules/storage/repositories/` |

### 이 모듈을 import하는 외부 모듈

| 소비자 | import 대상 | 용도 |
|--------|-------------|------|
| `services/execution-engine/` (REQ-007) | `toolset.application.use_cases.ExecuteToolUseCase` | 워크플로우 실행 시 각 노드의 도구 호출 |
| `services/api-server/` (REQ-009) | `toolset.application.use_cases.ListToolsUseCase` | 도구 카탈로그 API 제공 |

---

## 테스트 전략

```
tests/
├── unit/
│   ├── domain/
│   │   ├── test_base_tool.py              # ABC 계약 검증
│   │   ├── test_runtime_validator.py      # 스키마 검증 (valid/invalid 케이스)
│   │   ├── test_tool_execution_service.py # 실행 흐름 (BaseTool mock)
│   │   ├── test_risk_assessment_service.py
│   │   └── test_tool_metadata.py
│   └── application/
│       ├── test_execute_tool_use_case.py  # 전체 흐름 (Port mock)
│       ├── test_list_tools_use_case.py
│       └── test_validate_tool_config_use_case.py
├── unit/tools/                            # 각 구체 Tool 단위 테스트
│   ├── test_http_request_tool.py
│   ├── test_json_transform_tool.py
│   ├── test_email_send_tool.py
│   └── ...
└── integration/
    ├── test_secure_connector.py           # 실제 HTTP 호출 (mock server)
    └── test_tool_registry_adapter.py
```

---

## 파일 배치 요약

```
modules/toolset/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── base_tool.py                  # BaseTool ABC
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── tool_execution_record.py  # ToolExecutionRecord
│   │   └── tool_metadata.py          # ToolMetadata
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── tool_input.py             # ToolInput
│   │   ├── tool_output.py            # ToolOutput
│   │   └── execution_timeout.py      # ExecutionTimeout
│   ├── services/
│   │   ├── __init__.py
│   │   ├── runtime_validator.py      # RuntimeValidator
│   │   ├── tool_execution_service.py # ToolExecutionService
│   │   └── risk_assessment_service.py # RiskAssessmentService
│   └── ports/
│       ├── __init__.py
│       ├── tool_registry.py          # ToolRegistry ABC
│       ├── secure_connector_port.py  # SecureConnectorPort ABC
│       └── tool_execution_repository.py # ToolExecutionRepository ABC
├── application/
│   ├── __init__.py
│   └── use_cases/
│       ├── __init__.py
│       ├── execute_tool_use_case.py
│       ├── list_tools_use_case.py
│       └── validate_tool_config_use_case.py
├── adapters/
│   ├── __init__.py
│   ├── tool_registry_adapter.py      # ToolRegistryAdapter
│   ├── secure_connector.py           # SecureConnectorAdapter
│   └── tools/                        # 구체 Tool 구현체들
│       ├── __init__.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── http_request_tool.py
│       │   ├── rest_api_tool.py
│       │   ├── graphql_tool.py
│       │   └── webhook_tool.py
│       ├── file/
│       │   ├── __init__.py
│       │   ├── file_read_tool.py
│       │   ├── file_write_tool.py
│       │   └── file_transform_tool.py
│       ├── transform/
│       │   ├── __init__.py
│       │   ├── json_transform_tool.py
│       │   ├── text_template_tool.py
│       │   └── data_mapping_tool.py
│       ├── control/
│       │   ├── __init__.py
│       │   ├── conditional_tool.py
│       │   ├── loop_tool.py
│       │   └── delay_tool.py
│       └── notification/
│           ├── __init__.py
│           ├── email_send_tool.py
│           └── slack_notify_tool.py
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   ├── application/
│   │   └── tools/
│   └── integration/
└── README.md
```
