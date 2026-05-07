# toolset

> REQ-005: 8종 외부 도구 어댑터, 런타임 I/O 검증, 보안 커넥터

## 설치

```bash
pip install -e modules/toolset
pip install -e "modules/toolset[dev]"
```

## Quick Start

```python
from toolset.domain.entities import BaseTool
from toolset.domain.services import RuntimeValidator
from toolset.domain.ports import ToolRegistry, SecureConnectorPort
from toolset.application.use_cases import ExecuteToolUseCase, RegisterToolUseCase
```

## Public API

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `BaseTool` (ABC) | tool_id, name, description, risk_level, input_schema, output_schema | 모든 도구의 추상 기본 클래스 |

```python
class BaseTool(ABC):
    @abstractmethod
    def run(self, params: dict, credential: PlaintextCredential) -> dict:
        ...
```

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `RuntimeValidator` | `validate_input(params, schema) → ValidationResult` | 실행 전 입력 스키마 검증 |
| | `validate_output(result, schema) → ValidationResult` | 실행 후 출력 스키마 검증 |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `ToolRegistry` | `get_tool(tool_id) → BaseTool`, `list_tools()`, `register_tool(tool)` | `toolset/adapters/` |
| `SecureConnectorPort` | `acquire_credential(credential_id, service) → PlaintextCredential` | `toolset/adapters/` |
| | `release_credential(credential_id) → None` | |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ExecuteToolUseCase` | `tool_id, params, credential_id → dict` | 검증 → 실행 → 검증 파이프라인 |
| `RegisterToolUseCase` | `BaseTool → None` | 새 도구 등록 |

### adapters/tools — 8종 도구 구현체

| 도구 | 클래스 | 주요 기능 |
|------|--------|----------|
| Google Drive | `GoogleDriveTool` | upload, download, list, share |
| Gmail | `GmailTool` | send, read, archive |
| Slack | `SlackTool` | send_message, post_thread, upload_file |
| Google Calendar | `GoogleCalendarTool` | create_event, list_events, update |
| Google Sheets | `GoogleSheetsTool` | read_sheet, write_cells, create_sheet |
| Webhook | `WebhookTool` | POST/GET/PUT 요청 전송 |
| HTTP Request | `HttpRequestTool` | 커스텀 HTTP 요청 (headers, auth, body) |
| LLM | `LLMTool` | Modal L4 Gemma4 텍스트 생성 |

## 의존 관계

```
이 모듈 → common-schemas (PlaintextCredential, RiskLevel, ValidationErrorResponse)
이 모듈 → auth (SecureConnectorPort가 CredentialInjectionService 활용)
이 모듈 ← execution-engine (워크플로우 실행 시 ExecuteToolUseCase 호출)
이 모듈 ← nodes-graph (ToolToNodeWrapper로 BaseTool → NodeDefinition 변환)
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `TOOL_EXECUTION_TIMEOUT` | N | 도구 실행 타임아웃 (기본: 30s) |
| `SLACK_BOT_TOKEN` | 조건부 | Slack 도구 사용 시 필요 |
| `WEBHOOK_MAX_RETRIES` | N | 웹훅 재시도 횟수 (기본: 3) |

## 새 도구 추가 방법

```python
from toolset.domain.entities import BaseTool
from common_schemas.enums import RiskLevel

class MyCustomTool(BaseTool):
    tool_id = "my_custom_tool"
    name = "My Custom Tool"
    risk_level = RiskLevel.MEDIUM
    input_schema = {"type": "object", "properties": {...}}
    output_schema = {"type": "object", "properties": {...}}

    def run(self, params: dict, credential: PlaintextCredential) -> dict:
        # 구현
        return {"result": ...}
```

## 보안 파이프라인

모든 도구 호출은 단일 보안 파이프라인을 따른다:

```
권한 미들웨어 (REQ-002) → 보안 어댑터 (본 모듈) → Repository (REQ-001)
```

- `PermissionSource`를 모든 Tool 호출에 필수 인자로 전달
- Tool은 자체 JWT 디코딩 / DB 권한 조회 금지 (단일 권한 결정자 원칙)
- `permission_source.risk_ceiling`보다 높은 `risk_level` Tool 호출 즉시 거부

## Secure Connector

```python
class SecureCredentialConnector(CredentialStore):
    async def retrieve(self, credential_id: str) -> PlaintextCredential:
        # 1. PermissionSource.granted_scopes 검증
        # 2. credential_kind 분기 (Fernet / AES-GCM)
        # 3. SecureAccessHelper 호출
        # 4. with 컨텍스트로 사용 직후 즉시 메모리 폐기
```

## State Manager

- Redis key: `session:{session_id}:tool:{tool_name}:{purpose}`
- TTL: 세션 TTL 동일 (idle 30분 / max 24시간)
- Redis 장애 시 PostgreSQL fallback (Degraded Mode)

## Tool-to-Node Wrapper

- 본 모듈의 Tool 메타데이터를 `POST /api/v1/nodes/register-tool`로 REQ-003에 등록
- 등록 시 BGE-M3 임베딩 자동 생성
- `node_definitions`에 `category=tool_wrapper`로 분류

## 비기능 제약

| 항목 | 기준 |
|------|------|
| Tool 단일 호출 P95 | < 500ms (LLM/외부 API 제외) |
| State Manager 응답 | < 50ms (Redis hit) |
| credential 평문 유출 | 0건 (memory 즉시 폐기) |
| RAG Faithfulness | >= 0.9 (Ragas) |
| Document Generator 양식 준수 | >= 0.85 (G-Eval) |

## 테스트

```bash
pytest modules/toolset/tests/
```
