# toolset

> REQ-005: 15종 외부 도구, 런타임 I/O 검증, 보안 커넥터
>
> 구현 명세 → [`docs/specs/REQ-005-toolset.md`](../../docs/specs/REQ-005-toolset.md)

## 설치

```bash
pip install -e modules/toolset
pip install -e "modules/toolset[dev]"
```

## Quick Start

```python
from toolset.domain.base_tool import BaseTool
from toolset.domain.entities import ToolExecutionRecord, ToolMetadata
from toolset.domain.value_objects import ToolInput, ToolOutput, ExecutionTimeout
from toolset.domain.services import RuntimeValidator, ToolExecutionService, RiskAssessmentService
from toolset.domain.ports import ToolRegistry, SecureConnectorPort, ToolExecutionRepository
from toolset.application.use_cases import (
    ExecuteToolUseCase, ListToolsUseCase, ValidateToolConfigUseCase,
)
```

## Public API

### domain/base_tool.py — BaseTool (ABC)

```python
class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel: ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]: ...

    @property
    @abstractmethod
    def output_schema(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]: ...
```

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `ToolExecutionRecord` | `execution_id: UUID`, `tool_name: str`, `input_data: dict`, `output_data: Optional[dict]`, `status: Literal["success","failed","timeout"]`, `error_message: Optional[str]`, `duration_ms: int`, `executed_at: datetime` | 도구 실행 결과 기록 |
| `ToolMetadata` | `tool_id: UUID`, `name: str`, `version: str`, `category: str`, `risk_level: RiskLevel`, `input_schema: dict`, `output_schema: dict`, `description: str`, `is_enabled: bool` | 도구 카탈로그 메타데이터 |

### domain/value_objects

| 클래스 | 설명 |
|--------|------|
| `ToolInput` | 검증된 도구 입력 (frozen). `data: dict[str, Any]`, `schema_version: str` |
| `ToolOutput` | 검증된 도구 출력 (frozen). `data: dict[str, Any]`, `metadata: dict[str, Any]` |
| `ExecutionTimeout` | 타임아웃 설정. `seconds: int`, `DEFAULT = 30`, `MAX = 300` |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `RuntimeValidator` | `validate_input(data: dict, schema: dict) → ToolInput` | 실행 전 입력 스키마 검증 (jsonschema) |
| | `validate_output(data: dict, schema: dict) → ToolOutput` | 실행 후 출력 스키마 검증 |
| `ToolExecutionService` | `execute(tool: BaseTool, input_data: dict) → ToolOutput` | 도구 실행 오케스트레이션 (검증→실행→검증) |
| `RiskAssessmentService` | `assess(tool: BaseTool, context: PermissionSource) → bool` | 실행 전 리스크 평가 (risk_ceiling 기반) |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `ToolRegistry` | `get(tool_name: str) → BaseTool` | `toolset/adapters/` |
| | `list_all() → list[ToolMetadata]` | |
| | `list_by_category(category: str) → list[ToolMetadata]` | |
| `SecureConnectorPort` | `connect(endpoint: str, credentials: PlaintextCredential, **kwargs) → httpx.Response` | `toolset/adapters/` |
| `ToolExecutionRepository` | `save(record: ToolExecutionRecord) → None` | `storage/repositories/` |
| | `find_by_tool(tool_name: str, limit: int) → list[ToolExecutionRecord]` | |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ExecuteToolUseCase` | `tool_name: str, input_data: dict, context: PermissionSource → ToolOutput` | 리스크 평가 → 입력 검증 → 실행 → 출력 검증 → 기록 저장 |
| `ListToolsUseCase` | `category: Optional[str], risk_level: Optional[RiskLevel] → list[ToolMetadata]` | 도구 카탈로그 조회 (필터링) |
| `ValidateToolConfigUseCase` | `tool_name: str, parameters: dict → bool` (+ 에러 목록) | 드래프트 단계 도구 설정 사전 검증 |

### adapters/tools — 15종 도구 구현체

| 카테고리 | 클래스 | risk_level | 설명 |
|----------|--------|------------|------|
| API 호출 | `HttpRequestTool` | Medium | 범용 HTTP 요청 |
| API 호출 | `RestApiTool` | Medium | REST API 호출 + 응답 파싱 |
| API 호출 | `GraphqlTool` | Medium | GraphQL 쿼리/뮤테이션 |
| API 호출 | `WebhookTool` | Low | 웹훅 발송 (fire-and-forget) |
| 파일 처리 | `FileReadTool` | Low | 파일 읽기 |
| 파일 처리 | `FileWriteTool` | Medium | 파일 쓰기/생성 |
| 파일 처리 | `FileTransformTool` | Low | 포맷 변환 (CSV↔JSON 등) |
| 데이터 변환 | `JsonTransformTool` | Low | JMESPath/JSONPath 변환 |
| 데이터 변환 | `TextTemplateTool` | Low | Jinja2 템플릿 렌더링 |
| 데이터 변환 | `DataMappingTool` | Low | 필드 매핑/리네이밍 |
| 조건/제어 | `ConditionalTool` | Low | 조건 분기 (if/else) |
| 조건/제어 | `LoopTool` | Medium | 반복 실행 (배열 순회) |
| 조건/제어 | `DelayTool` | Low | 대기/지연 |
| 알림 | `EmailSendTool` | High | 이메일 발송 |
| 알림 | `SlackNotifyTool` | Medium | Slack 메시지 전송 |

## 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common-schemas (REQ-012)
  │     └── RiskLevel, NodeConfig, ErrorCode, PermissionSource, PlaintextCredential
  └── auth (REQ-002)
        └── CredentialInjectionService (SecureConnectorAdapter에서 활용)

Downstream (이 모듈에 의존):
  ├── execution-engine (REQ-007) → ExecuteToolUseCase 호출
  ├── api-server (REQ-009)       → ListToolsUseCase 호출
  ├── nodes-graph (REQ-003)      → ToolToNodeWrapper로 BaseTool → NodeDefinition 변환
  └── storage (REQ-008)          → ToolExecutionRepository 구현체 제공
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `TOOL_EXECUTION_TIMEOUT` | N | 도구 실행 타임아웃 (기본: 30s, 최대: 300s) |
| `SLACK_BOT_TOKEN` | 조건부 | Slack 도구 사용 시 필요 |
| `WEBHOOK_MAX_RETRIES` | N | 웹훅 재시도 횟수 (기본: 3) |

## 보안 파이프라인

```
PermissionSource 검증 (REQ-002) → RiskAssessmentService → ToolExecutionService → SecureConnectorAdapter
```

- `PermissionSource`를 모든 Tool 호출에 필수 인자로 전달
- `permission_source.risk_ceiling`보다 높은 `risk_level` Tool 호출 즉시 거부
- Tool은 자체 JWT 디코딩 / DB 권한 조회 금지 (단일 권한 결정자 원칙)

## 비기능 제약

| 항목 | 기준 |
|------|------|
| Tool 단일 호출 P95 | < 500ms (LLM/외부 API 제외) |
| credential 평문 유출 | 0건 (memory 즉시 폐기) |

## 테스트

```bash
pytest modules/toolset/tests/
```
