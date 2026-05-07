# common-schemas

> REQ-012: Pydantic v2 공유 스키마 — 전체 시스템의 Single Source of Truth (SSOT)

## 설치

```bash
# 모노레포 루트에서
pip install -e packages/common-schemas/python

# 개발 의존성 포함
pip install -e "packages/common-schemas/python[dev]"

# TypeScript (프론트엔드에서 사용)
# packages/common-schemas/typescript/src/generated/ 에서 자동 생성된 타입 import
```

## Quick Start

```python
from common_schemas import (
    WorkflowSchema, NodeInstance, Edge, Position,
    NodeConfig,
    AgentState, DraftSpec, IntentResult, SlotFillingState, UnresolvedNode,
    DocumentBlock, ContentBlock, FileMeta, SourceRef, BBox, ParserMeta, SheetMeta,
    AnalysisResult,
    PermissionSource, PlaintextCredential,
    HandoffPayload, EvaluationResult,
)
from common_schemas.enums import AgentMode, ExecutionStatus, RiskLevel, ErrorCode
from common_schemas.exceptions import DomainError, ValidationError, NotFoundError
from common_schemas.transport import (
    SSEFrame, SessionFrame, AgentNodeFrame, RationaleDeltaFrame,
    SlotFillQuestionFrame, DraftSpecDeltaFrame, ResultFrame, ErrorFrame, AnySSEFrame,
)
```

## Public API

### workflow.py — 워크플로우 정의

| 클래스 | 설명 |
|--------|------|
| `WorkflowSchema` | 워크플로우 전체 정의 (nodes, edges, metadata) |
| `NodeInstance` | 워크플로우 내 노드 인스턴스 (position, config, credential_id) |
| `Edge` | 노드 간 연결 (source → target, 조건부 분기 포함) |
| `Position` | 캔버스 좌표 VO (x, y) |

### node.py — 노드 설정

| 클래스 | 설명 |
|--------|------|
| `NodeConfig` | 노드 기본 설정 (node_type, input/output_schema, required_fields) |

### agent.py — AI 에이전트 상태

| 클래스 | 설명 |
|--------|------|
| `AgentState` | LangGraph 상태 컨테이너 (messages, draft, intent, mode) |
| `DraftSpec` | 워크플로우 초안 명세 |
| `IntentResult` | 의도 분석 결과 (clarify/draft/refine/propose) |
| `SlotFillingState` | 온보딩 슬롯 채움 상태 |
| `UnresolvedNode` | 미확정 노드 참조 |

### document.py — 문서 파싱 결과

| 클래스 | 설명 |
|--------|------|
| `DocumentBlock` | 파싱된 문서 최상위 컨테이너 |
| `ContentBlock` | 개별 콘텐츠 블록 (text, table, image, heading, code) |
| `FileMeta` | 원본 파일 메타데이터 |
| `SourceRef` | 원본 위치 참조 VO (page, section, bbox) |
| `BBox` | OCR/레이아웃 바운딩 박스 (x1, y1, x2, y2) |
| `ParserMeta` | 파서 이름, 버전, 실행시간 메타 |
| `SheetMeta` | Excel 시트 메타 (sheet_name, row_count, col_count) |
| `AnalysisResult` | AI 분석 결과 (요약, 핵심 포인트) |

### security.py — 보안 모델

| 클래스 | 설명 |
|--------|------|
| `PermissionSource` | 사용자 권한 컨텍스트 (user_id, role, department_id, risk_ceiling) |
| `PlaintextCredential` | 복호화된 자격증명 (자동 wipe 지원) |

### transport.py — SSE 스트리밍 프레임

| 클래스 | 설명 |
|--------|------|
| `SSEFrame` | 기본 SSE 프레임 (frame_type 필드) |
| `SessionFrame` | 세션 초기화 (session_id, langgraph_thread_id) |
| `AgentNodeFrame` | 현재 실행 에이전트 노드 |
| `RationaleDeltaFrame` | AI 추론 실시간 스트리밍 |
| `SlotFillQuestionFrame` | 사용자 질문 프레임 |
| `DraftSpecDeltaFrame` | 초안 증분 업데이트 |
| `ResultFrame` | 최종 결과 (intent: clarify/draft/refine/propose) |
| `ErrorFrame` | 에러 알림 |
| `AnySSEFrame` | Discriminated union — frame_type 기반 역직렬화 |

### handoff.py — 에이전트 → 실행엔진 핸드오프

| 클래스 | 설명 |
|--------|------|
| `HandoffPayload` | REQ-004 → REQ-007 전달 페이로드 |
| `EvaluationResult` | QA 평가 결과 (score, pass_flag, reason) |

### enums.py — 공유 열거형

| Enum | 값 |
|------|-----|
| `AgentMode` | ONBOARDING, WIZARD, EDIT, GENERAL, SECURITY |
| `ExecutionStatus` | RUNNING, PAUSED, COMPLETED, FAILED |
| `RiskLevel` | Low, Medium, High, Restricted |
| `ErrorCode` | 도메인 에러 코드 열거 |

### exceptions.py — 도메인 예외 계층

| 예외 | 용도 |
|------|------|
| `DomainError` | 기본 클래스 (code: ErrorCode, message: str) |
| `ValidationError` | 데이터 검증 실패 |
| `AuthorizationError` | 권한 부족 |
| `NotFoundError` | 리소스 미존재 |
| `ConflictError` | 상태 충돌 |
| `IntegrityError` | 데이터 무결성 위반 |

### validation.py — 검증 에러 리포팅

| 클래스 | 설명 |
|--------|------|
| `ValidationErrorResponse` | 배치 에러 응답 (errors, is_valid) |
| `ValidationErrorItem` | 개별 검증 에러 (field, error_code, severity) |

## 의존 관계

```
Upstream (이 패키지가 의존):
  └── pydantic >= 2.7.0 (유일한 외부 의존성)

Downstream (이 패키지에 의존):
  ├── modules/auth (REQ-002)
  ├── modules/nodes-graph (REQ-003)
  ├── modules/ai-agent (REQ-004)
  ├── modules/toolset (REQ-005)
  ├── modules/doc-parser (REQ-006)
  ├── modules/storage (REQ-008)
  ├── services/execution-engine (REQ-007)
  ├── services/api-server (REQ-009)
  └── services/frontend (REQ-010) — TypeScript 자동 생성 타입
```

## 설계 규칙

- 이 패키지는 **어떤 프레임워크도 import하지 않음** (FastAPI, SQLAlchemy, LangGraph 금지)
- 모든 Enum은 `str`을 상속하여 JSON 직렬화 호환
- 필드 타입 불일치 시 이 패키지의 정의가 우선 (SSOT 원칙)
- TypeScript 타입은 `pydantic2ts`로 Python에서 자동 생성 — 수동 편집 금지

## TypeScript 사용 (프론트엔드)

```typescript
import type { WorkflowSchema, NodeInstance } from "@workflow-automation/common-schemas";
```

`tsconfig.json`의 `@common/*` 경로 별칭으로 참조합니다.

## 코드 생성

```bash
pip install -e "packages/common-schemas/python[codegen]"
cd packages/common-schemas/scripts
python generate_ts.py
```

## 테스트

```bash
pytest packages/common-schemas/python/tests/
ruff check packages/common-schemas/python/
```
