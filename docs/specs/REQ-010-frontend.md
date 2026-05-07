# REQ-010 Frontend — 구현 명세

- **담당자**: 황대원
- **모듈 경로**: `services/frontend/`
- **기술 스택**: React 18+, TypeScript 5.x, Next.js 14, React Flow (노드 에디터)
- **아키텍처 계층**: Frameworks & Drivers (UI — 최외곽)

---

## 1. common-schemas에서 import할 타입 (TypeScript)

### 1.1 import 소스

```
packages/common-schemas/typescript/src/generated/index.ts
```

> 이 파일은 Python common_schemas에서 `scripts/generate_ts.py`로 자동 생성됨.
> **절대 수동 편집 금지** — Python 측 수정 후 codegen 재실행.

### 1.2 Interfaces

| 인터페이스 | 용도 |
|-----------|------|
| `WorkflowSchema` | 워크플로우 캔버스 전체 데이터 모델 |
| `NodeInstance` | 캔버스 위 개별 노드 (position 포함) |
| `NodeConfig` | 노드 팔레트 카탈로그 아이템 |
| `Edge` | 노드 간 연결선 |
| `Position` | 노드 캔버스 좌표 (x, y) |
| `AgentState` | 에이전트 채팅 상태 표시 |
| `DraftSpec` | 에이전트가 생성 중인 드래프트 스펙 |
| `IntentResult` | 에이전트 의도 분석 결과 |
| `SlotFillingState` | 슬롯 필링 진행 상태 (asked/pending/filled) |
| `UnresolvedNode` | 아직 확정되지 않은 노드 표시 |
| `DocumentBlock` | 문서 뷰어 전체 블록 |
| `ContentBlock` | 문서 내 개별 콘텐츠 블록 |
| `FileMeta` | 파일 메타데이터 표시 |
| `AnalysisResult` | 문서 분석 결과 렌더링 |
| `ValidationErrorItem` | 검증 에러 개별 항목 표시 |
| `ValidationErrorResponse` | 워크플로우 검증 결과 전체 응답 |
| `HandoffPayload` | 에이전트 핸드오프 상태 표시 |

### 1.3 Enums

| Enum | 용도 |
|------|------|
| `AgentMode` | 에이전트 모드 뱃지/UI 분기 (onboarding/wizard/edit/general/security) |
| `ExecutionStatus` | 실행 상태 인디케이터 (running/paused/completed/failed) |
| `RiskLevel` | 노드 위험도 뱃지 색상 (Low=green, Medium=yellow, High=orange, Restricted=red) |
| `ErrorCode` | 검증 에러 코드별 아이콘/메시지 매핑 |

### 1.4 SSE Frame 타입

| 타입 | 용도 |
|------|------|
| `SSEFrame` | 베이스 프레임 (frame_type 필드) |
| `SessionFrame` | 세션 연결 성공 시 session_id 수신 |
| `AgentNodeFrame` | 현재 실행 중인 에이전트 노드 표시 |
| `RationaleDeltaFrame` | 추론 과정 실시간 텍스트 스트리밍 |
| `SlotFillQuestionFrame` | 슬롯 필링 질문 UI 렌더링 |
| `DraftSpecDeltaFrame` | 드래프트 스펙 실시간 업데이트 |
| `ResultFrame` | 최종 결과 수신 및 UI 전환 |
| `ErrorFrame` | 에러 토스트/모달 표시 |
| `AnySSEFrame` | Discriminated union — frame_type 기반 타입 가드 |

### 1.5 import 코드 예시

```typescript
import {
  // Enums
  AgentMode,
  ExecutionStatus,
  RiskLevel,
  ErrorCode,
  // Workflow
  WorkflowSchema,
  NodeInstance,
  NodeConfig,
  Edge,
  Position,
  // Agent
  AgentState,
  DraftSpec,
  IntentResult,
  SlotFillingState,
  UnresolvedNode,
  // Document
  DocumentBlock,
  ContentBlock,
  FileMeta,
  AnalysisResult,
  // Validation
  ValidationErrorItem,
  ValidationErrorResponse,
  // SSE Transport
  SSEFrame,
  SessionFrame,
  AgentNodeFrame,
  RationaleDeltaFrame,
  SlotFillQuestionFrame,
  DraftSpecDeltaFrame,
  ResultFrame,
  ErrorFrame,
  AnySSEFrame,
} from '@workflow-automation/common-schemas';
```

---

## 2. 이 모듈에서 구현할 컴포넌트

### 2.1 Pages (Next.js App Router)

| 페이지 | 파일 경로 | 설명 |
|--------|-----------|------|
| `WorkflowEditorPage` | `app/workflows/[id]/page.tsx` | 워크플로우 캔버스 편집 페이지 |
| `WorkflowListPage` | `app/workflows/page.tsx` | 워크플로우 목록/검색 |
| `AgentChatPage` | `app/agent/page.tsx` | 에이전트 대화 인터페이스 |
| `DocumentsPage` | `app/documents/page.tsx` | 문서 목록/업로드 |
| `DocumentDetailPage` | `app/documents/[id]/page.tsx` | 문서 상세 + 분석 결과 |
| `DashboardPage` | `app/page.tsx` | 대시보드 메인 |
| `LoginPage` | `app/login/page.tsx` | OAuth2 로그인 |

### 2.2 Components — WorkflowCanvas

| 컴포넌트 | 파일 경로 | 설명 |
|----------|-----------|------|
| `WorkflowCanvas` | `components/workflow/WorkflowCanvas.tsx` | React Flow 기반 노드 캔버스 (드래그/드롭, 줌, 패닝) |
| `CustomNode` | `components/workflow/CustomNode.tsx` | NodeInstance를 렌더링하는 커스텀 노드 컴포넌트 |
| `NodePalette` | `components/workflow/NodePalette.tsx` | NodeConfig[] 기반 드래그 가능한 노드 팔레트 |
| `EdgeLine` | `components/workflow/EdgeLine.tsx` | Edge를 렌더링하는 커스텀 엣지 컴포넌트 |
| `ValidationPanel` | `components/workflow/ValidationPanel.tsx` | ValidationErrorResponse 결과 표시 패널 |
| `ExecutionStatusBadge` | `components/workflow/ExecutionStatusBadge.tsx` | ExecutionStatus에 따른 상태 뱃지 |
| `RiskLevelBadge` | `components/workflow/RiskLevelBadge.tsx` | RiskLevel에 따른 색상 뱃지 |
| `NodeConfigDrawer` | `components/workflow/NodeConfigDrawer.tsx` | 노드 선택 시 파라미터 편집 드로어 |

### 2.3 Components — AgentChat

| 컴포넌트 | 파일 경로 | 설명 |
|----------|-----------|------|
| `AgentChat` | `components/agent/AgentChat.tsx` | SSE 스트리밍 기반 에이전트 대화 UI |
| `MessageBubble` | `components/agent/MessageBubble.tsx` | 개별 메시지 버블 (사용자/에이전트) |
| `RationaleStream` | `components/agent/RationaleStream.tsx` | RationaleDeltaFrame 실시간 텍스트 표시 |
| `SlotFillForm` | `components/agent/SlotFillForm.tsx` | SlotFillQuestionFrame → 입력 폼 렌더링 |
| `DraftSpecPreview` | `components/agent/DraftSpecPreview.tsx` | DraftSpec 실시간 미리보기 카드 |
| `AgentModeBadge` | `components/agent/AgentModeBadge.tsx` | AgentMode 표시 뱃지 |
| `UnresolvedNodeList` | `components/agent/UnresolvedNodeList.tsx` | UnresolvedNode[] 후보 목록 표시 |

### 2.4 Components — DocumentViewer

| 컴포넌트 | 파일 경로 | 설명 |
|----------|-----------|------|
| `DocumentViewer` | `components/document/DocumentViewer.tsx` | DocumentBlock 전체 렌더링 |
| `ContentBlockRenderer` | `components/document/ContentBlockRenderer.tsx` | block_type별 분기 렌더링 (text/table/image/heading/code) |
| `AnalysisResultCard` | `components/document/AnalysisResultCard.tsx` | AnalysisResult 요약 카드 |
| `FileMetaHeader` | `components/document/FileMetaHeader.tsx` | FileMeta 파일 정보 헤더 |

### 2.5 Hooks (Custom React Hooks)

| Hook | 파일 경로 | 설명 |
|------|-----------|------|
| `useSSEStream` | `hooks/useSSEStream.ts` | EventSource 기반 SSE 연결 관리. AnySSEFrame discriminated union 파싱 |
| `useWorkflow` | `hooks/useWorkflow.ts` | 워크플로우 CRUD + 상태 관리 |
| `useAgentSession` | `hooks/useAgentSession.ts` | 에이전트 세션 생성/메시지 전송 |
| `useValidation` | `hooks/useValidation.ts` | 워크플로우 검증 요청 + 결과 관리 |
| `useAuth` | `hooks/useAuth.ts` | 인증 상태 관리 + 토큰 갱신 |

### 2.6 Services (API Client Layer)

| 서비스 | 파일 경로 | 설명 |
|--------|-----------|------|
| `apiClient` | `lib/apiClient.ts` | Axios/Fetch 래퍼, JWT 자동 첨부, 에러 인터셉터 |
| `workflowApi` | `lib/api/workflowApi.ts` | /workflows 엔드포인트 호출 함수 |
| `agentApi` | `lib/api/agentApi.ts` | /agents 엔드포인트 호출 함수 |
| `documentApi` | `lib/api/documentApi.ts` | /documents 엔드포인트 호출 함수 |
| `authApi` | `lib/api/authApi.ts` | /auth 엔드포인트 호출 함수 |

### 2.7 State Management

| Store | 파일 경로 | 설명 |
|-------|-----------|------|
| `workflowStore` | `store/workflowStore.ts` | Zustand — 현재 편집 중인 WorkflowSchema 상태 |
| `agentStore` | `store/agentStore.ts` | Zustand — AgentState + 메시지 히스토리 |
| `authStore` | `store/authStore.ts` | Zustand — 인증 토큰 + 사용자 정보 |

---

## 3. SSE 클라이언트 구현 상세

### 3.1 useSSEStream Hook 핵심 로직

```typescript
import { AnySSEFrame } from '@workflow-automation/common-schemas';

type FrameHandler = {
  onSession?: (frame: SessionFrame) => void;
  onAgentNode?: (frame: AgentNodeFrame) => void;
  onRationaleDelta?: (frame: RationaleDeltaFrame) => void;
  onSlotFillQuestion?: (frame: SlotFillQuestionFrame) => void;
  onDraftSpecDelta?: (frame: DraftSpecDeltaFrame) => void;
  onResult?: (frame: ResultFrame) => void;
  onError?: (frame: ErrorFrame) => void;
};

function useSSEStream(sessionId: string, handlers: FrameHandler) {
  // EventSource 연결: GET /agents/sessions/{sessionId}/stream
  // 각 event의 data를 JSON.parse → frame_type으로 discriminate
  // 해당 handler 콜백 호출
}
```

### 3.2 frame_type 기반 Type Guard

```typescript
function isSessionFrame(frame: AnySSEFrame): frame is SessionFrame {
  return frame.frame_type === 'session';
}

function isRationaleDeltaFrame(frame: AnySSEFrame): frame is RationaleDeltaFrame {
  return frame.frame_type === 'rationale_delta';
}

// ... 각 프레임 타입별 type guard
```

### 3.3 Discriminated Union 처리 패턴

```typescript
function handleFrame(frame: AnySSEFrame): void {
  switch (frame.frame_type) {
    case 'session':
      // frame은 자동으로 SessionFrame 타입
      setSessionId(frame.session_id);
      break;
    case 'agent_node':
      setCurrentNode(frame.agent_node_name);
      break;
    case 'rationale_delta':
      appendRationale(frame.delta);
      break;
    case 'slot_fill_question':
      showQuestionForm(frame.question, frame.field_name);
      break;
    case 'draft_spec_delta':
      updateDraftSpec(frame.delta);
      break;
    case 'result':
      completeSession(frame.intent, frame.payload);
      break;
    case 'error':
      showErrorToast(frame.code, frame.message);
      break;
  }
}
```

---

## 4. 합의된 변경사항 (클래스 다이어그램 교차분석)

| # | 합의 사항 | 프론트엔드 영향 |
|---|-----------|----------------|
| 1 | TypeScript 타입은 Python에서 자동 생성 | `generated/index.ts`에서만 import, 수동 타입 정의 금지 |
| 2 | SSE frame_type 기반 discriminated union 확정 | switch-case 패턴으로 타입 안전한 프레임 처리 |
| 3 | ID 타입 = string (UUID 문자열) | TypeScript에서는 UUID를 string으로 표현 (Python의 UUID ↔ TS의 string) |
| 4 | `scope` 소문자 리터럴 유니온 | `"private" \| "team" \| "public"` 리터럴 타입 사용 |
| 5 | NodeConfig.risk_level → RiskLevel enum | 뱃지 색상 매핑에 enum 직접 사용 |
| 6 | Optional 필드 = `T \| null` 패턴 | undefined가 아닌 null 체크로 통일 |
| 7 | Position 타입으로 좌표 통일 | React Flow의 XYPosition과 매핑 필요 (어댑터 함수) |

---

## 5. 의존성 관계

```
services/frontend/
├── imports types from ─────────────────────────────────────┐
│   packages/common-schemas/typescript/src/generated/       │ (SSOT TypeScript 타입)
│                                                           │
├── calls API ──────────────────────────────────────────────┐
│   services/api-server/ (REQ-009)                          │
│     - REST: /workflows, /agents, /documents, /auth        │
│     - SSE:  /agents/sessions/{id}/stream                  │
│                                                           │
├── depends on (npm packages) ──────────────────────────────┐
│   react, react-dom                                        │
│   next (App Router)                                       │
│   @xyflow/react (React Flow — 노드 에디터)                │
│   zustand (상태 관리)                                      │
│   axios (HTTP 클라이언트)                                  │
│   tailwindcss (스타일링)                                   │
│                                                           │
└── consumed by ────────────────────────────────────────────┐
    End Users (웹 브라우저)                                  │
```

### 5.1 React Flow ↔ common-schemas 어댑터

React Flow는 자체 `Node`, `Edge` 타입을 사용하므로, common-schemas 타입과의 변환 어댑터가 필요:

```typescript
// lib/adapters/reactFlowAdapter.ts

import { NodeInstance, Edge as SchemaEdge, Position } from '@workflow-automation/common-schemas';
import { Node as RFNode, Edge as RFEdge } from '@xyflow/react';

function toReactFlowNode(instance: NodeInstance): RFNode {
  return {
    id: instance.instance_id,
    position: { x: instance.position.x, y: instance.position.y },
    data: { ...instance.parameters, nodeId: instance.node_id },
    type: 'custom',
  };
}

function toReactFlowEdge(edge: SchemaEdge): RFEdge {
  return {
    id: `${edge.from_instance_id}-${edge.to_instance_id}`,
    source: edge.from_instance_id,
    target: edge.to_instance_id,
    sourceHandle: edge.from_handle,
    targetHandle: edge.to_handle,
  };
}

function fromReactFlowNode(rfNode: RFNode): Partial<NodeInstance> {
  return {
    instance_id: rfNode.id,
    position: { x: rfNode.position.x, y: rfNode.position.y },
  };
}
```

---

## 6. 디렉토리 구조 (최종)

```
services/frontend/
├── app/                                 # Next.js App Router
│   ├── layout.tsx                       # 루트 레이아웃
│   ├── page.tsx                         # 대시보드
│   ├── login/page.tsx                   # 로그인
│   ├── workflows/
│   │   ├── page.tsx                     # 워크플로우 목록
│   │   └── [id]/page.tsx               # 워크플로우 에디터
│   ├── agent/page.tsx                   # 에이전트 채팅
│   └── documents/
│       ├── page.tsx                     # 문서 목록
│       └── [id]/page.tsx               # 문서 상세
├── components/
│   ├── workflow/
│   │   ├── WorkflowCanvas.tsx
│   │   ├── CustomNode.tsx
│   │   ├── NodePalette.tsx
│   │   ├── EdgeLine.tsx
│   │   ├── ValidationPanel.tsx
│   │   ├── ExecutionStatusBadge.tsx
│   │   ├── RiskLevelBadge.tsx
│   │   └── NodeConfigDrawer.tsx
│   ├── agent/
│   │   ├── AgentChat.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── RationaleStream.tsx
│   │   ├── SlotFillForm.tsx
│   │   ├── DraftSpecPreview.tsx
│   │   ├── AgentModeBadge.tsx
│   │   └── UnresolvedNodeList.tsx
│   ├── document/
│   │   ├── DocumentViewer.tsx
│   │   ├── ContentBlockRenderer.tsx
│   │   ├── AnalysisResultCard.tsx
│   │   └── FileMetaHeader.tsx
│   └── ui/                              # 공통 UI 컴포넌트 (Button, Modal 등)
├── hooks/
│   ├── useSSEStream.ts
│   ├── useWorkflow.ts
│   ├── useAgentSession.ts
│   ├── useValidation.ts
│   └── useAuth.ts
├── store/
│   ├── workflowStore.ts
│   ├── agentStore.ts
│   └── authStore.ts
├── lib/
│   ├── apiClient.ts                     # HTTP 클라이언트 설정
│   ├── api/
│   │   ├── workflowApi.ts
│   │   ├── agentApi.ts
│   │   ├── documentApi.ts
│   │   └── authApi.ts
│   └── adapters/
│       └── reactFlowAdapter.ts          # common-schemas ↔ React Flow 변환
├── types/
│   └── index.ts                         # 프론트엔드 전용 타입 (UI 상태 등)
├── package.json
├── tsconfig.json
├── next.config.js
├── tailwind.config.ts
└── README.md
```

---

## 7. 주요 구현 주의사항

### 7.1 타입 안전성

- **AnySSEFrame의 exhaustive check**: switch-case에서 모든 frame_type을 처리하고, default에 `never` 타입 할당으로 누락 방지
- **null vs undefined**: common-schemas의 Optional 필드는 `T | null`로 생성됨. `undefined`와 혼동하지 않을 것

### 7.2 성능

- **SSE 재연결**: EventSource 연결 끊김 시 exponential backoff로 재연결
- **RationaleDelta 렌더링**: delta 문자열을 누적할 때 불필요한 리렌더 방지 (useRef + requestAnimationFrame)
- **React Flow 최적화**: 대량 노드(50+) 시 가상화 활성화

### 7.3 에러 처리

- `ErrorFrame` 수신 시 ErrorCode enum에 따라 사용자 친화적 메시지 매핑
- API 4xx/5xx 응답은 `ValidationErrorResponse` 포맷으로 통일 처리
