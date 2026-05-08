# frontend

> REQ-010: Next.js 14 + React Flow + AI Agent Chat + SSE Streaming
>
> 구현 명세 → [`docs/specs/REQ-010-frontend.md`](../../docs/specs/REQ-010-frontend.md)

## 설치

```bash
cd services/frontend
npm install
```

## 실행

```bash
npm run dev    # 개발 서버 (http://localhost:3000)
npm run build  # 프로덕션 빌드
npm run start  # 프로덕션 서버
```

## common_schemas에서 import하는 타입 (TypeScript)

**import 소스**: `packages/common_schemas/typescript/src/generated/index.ts`
> Python common_schemas에서 `scripts/generate_ts.py`로 자동 생성. **절대 수동 편집 금지**.

### Interfaces

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

### Enums

| Enum | 용도 |
|------|------|
| `AgentMode` | 에이전트 모드 뱃지/UI 분기 (onboarding/wizard/edit/general/security) |
| `ExecutionStatus` | 실행 상태 인디케이터 (running/paused/completed/failed) |
| `RiskLevel` | 노드 위험도 뱃지 색상 (Low=green, Medium=yellow, High=orange, Restricted=red) |
| `ErrorCode` | 검증 에러 코드별 아이콘/메시지 매핑 |

### SSE Frame 타입

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

### import 예시

```typescript
import {
  AgentMode, ExecutionStatus, RiskLevel, ErrorCode,
  WorkflowSchema, NodeInstance, NodeConfig, Edge, Position,
  AgentState, DraftSpec, IntentResult, SlotFillingState, UnresolvedNode,
  DocumentBlock, ContentBlock, FileMeta, AnalysisResult,
  ValidationErrorItem, ValidationErrorResponse,
  SSEFrame, SessionFrame, AgentNodeFrame, RationaleDeltaFrame,
  SlotFillQuestionFrame, DraftSpecDeltaFrame, ResultFrame, ErrorFrame, AnySSEFrame,
} from '@workflow-automation/common_schemas';
```

## Pages (Next.js App Router)

| 페이지 | 파일 경로 | 설명 |
|--------|-----------|------|
| `DashboardPage` | `app/page.tsx` | 대시보드 메인 |
| `LoginPage` | `app/login/page.tsx` | OAuth2 로그인 |
| `WorkflowListPage` | `app/workflows/page.tsx` | 워크플로우 목록/검색 |
| `WorkflowEditorPage` | `app/workflows/[id]/page.tsx` | 워크플로우 캔버스 편집 |
| `AgentChatPage` | `app/agent/page.tsx` | 에이전트 대화 인터페이스 |
| `DocumentsPage` | `app/documents/page.tsx` | 문서 목록/업로드 |
| `DocumentDetailPage` | `app/documents/[id]/page.tsx` | 문서 상세 + 분석 결과 |

## Components

### workflow/ — 워크플로우 캔버스

| 컴포넌트 | 설명 |
|----------|------|
| `WorkflowCanvas` | React Flow 기반 노드 캔버스 (드래그/드롭, 줌, 패닝) |
| `CustomNode` | NodeInstance를 렌더링하는 커스텀 노드 컴포넌트 |
| `NodePalette` | NodeConfig[] 기반 드래그 가능한 노드 팔레트 |
| `EdgeLine` | Edge를 렌더링하는 커스텀 엣지 컴포넌트 |
| `ValidationPanel` | ValidationErrorResponse 결과 표시 패널 |
| `ExecutionStatusBadge` | ExecutionStatus에 따른 상태 뱃지 |
| `RiskLevelBadge` | RiskLevel에 따른 색상 뱃지 |
| `NodeConfigDrawer` | 노드 선택 시 파라미터 편집 드로어 |

### agent/ — AI 에이전트 채팅

| 컴포넌트 | 설명 |
|----------|------|
| `AgentChat` | SSE 스트리밍 기반 에이전트 대화 UI |
| `MessageBubble` | 개별 메시지 버블 (사용자/에이전트) |
| `RationaleStream` | RationaleDeltaFrame 실시간 텍스트 표시 |
| `SlotFillForm` | SlotFillQuestionFrame → 입력 폼 렌더링 |
| `DraftSpecPreview` | DraftSpec 실시간 미리보기 카드 |
| `AgentModeBadge` | AgentMode 표시 뱃지 |
| `UnresolvedNodeList` | UnresolvedNode[] 후보 목록 표시 |

### document/ — 문서 뷰어

| 컴포넌트 | 설명 |
|----------|------|
| `DocumentViewer` | DocumentBlock 전체 렌더링 |
| `ContentBlockRenderer` | block_type별 분기 렌더링 (text/table/image/heading/code) |
| `AnalysisResultCard` | AnalysisResult 요약 카드 |
| `FileMetaHeader` | FileMeta 파일 정보 헤더 |

## Hooks

| Hook | 설명 |
|------|------|
| `useSSEStream` | EventSource 기반 SSE 연결 관리. AnySSEFrame discriminated union 파싱 |
| `useWorkflow` | 워크플로우 CRUD + 상태 관리 |
| `useAgentSession` | 에이전트 세션 생성/메시지 전송 |
| `useValidation` | 워크플로우 검증 요청 + 결과 관리 |
| `useAuth` | 인증 상태 관리 + 토큰 갱신 |

## Services (API Client)

| 서비스 | 설명 |
|--------|------|
| `apiClient` | Axios/Fetch 래퍼, JWT 자동 첨부, 에러 인터셉터 |
| `workflowApi` | `/workflows` 엔드포인트 호출 함수 |
| `agentApi` | `/agents` 엔드포인트 호출 함수 |
| `documentApi` | `/documents` 엔드포인트 호출 함수 |
| `authApi` | `/auth` 엔드포인트 호출 함수 |

## State Management (Zustand)

| Store | 설명 |
|-------|------|
| `workflowStore` | 현재 편집 중인 WorkflowSchema 상태 |
| `agentStore` | AgentState + 메시지 히스토리 |
| `authStore` | 인증 토큰 + 사용자 정보 |

## React Flow ↔ common_schemas 어댑터

React Flow는 자체 `Node`, `Edge` 타입을 사용하므로 common_schemas 타입과의 변환 어댑터 필요:

```typescript
// lib/adapters/reactFlowAdapter.ts
import { NodeInstance, Edge as SchemaEdge } from '@workflow-automation/common_schemas';
import { Node as RFNode, Edge as RFEdge } from '@xyflow/react';

function toReactFlowNode(instance: NodeInstance): RFNode { ... }
function toReactFlowEdge(edge: SchemaEdge): RFEdge { ... }
function fromReactFlowNode(rfNode: RFNode): Partial<NodeInstance> { ... }
```

## SSE 프레임 처리

| 프레임 | UI 처리 |
|--------|---------|
| `session` | store에 session_id + langgraph_thread_id 저장 |
| `agent_node` | 채팅 상단 "현재 단계" 인디케이터 |
| `rationale_delta` | 접을 수 있는 "AI 사고 과정" 영역에 스트림 조립 |
| `slot_fill_question` | chip 형태 (예/아니오/자유 입력) |
| `draft_spec_delta` | Draft Spec 시각화 카드 형태 렌더 |
| `result` | intent별 분기 (clarify/draft/refine/propose). propose → Skill 수락 배너 |
| `error` | ErrorCode enum 매핑 → 사용자 친화적 토스트/모달 |

## Risk Level 배지 + Permission Filter

| risk_level | 배지 색상 | User 권한 동작 | Admin 권한 동작 |
|-----------|----------|-------------|---------------|
| Low | 회색 | 정상 | 정상 |
| Medium | 노랑 | 정상 | 정상 |
| High | 주황 | 정상 (미연결 시 "Connect first" CTA) | 정상 |
| Restricted | 빨강 | 회색 처리 + 드래그 차단 + tooltip "관리자만 사용 가능" | 정상 |

## 의존 관계

```
Upstream (이 서비스가 의존):
  ├── common_schemas/typescript (REQ-012) → 모든 TypeScript 타입 (자동 생성)
  └── api_server (REQ-009)               → HTTP REST + SSE 스트리밍

Downstream (이 서비스를 소비):
  └── End Users (웹 브라우저)
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `NEXT_PUBLIC_API_URL` | Y | API 서버 URL |
| `NEXT_PUBLIC_SSE_URL` | N | SSE 엔드포인트 (미지정 시 API_URL 사용) |

## 보안 제약

- JWT Access Token은 메모리만, localStorage 금지
- `dangerouslySetInnerHTML` 사용 금지 (LLM 출력 XSS 방어)
- `NEXT_PUBLIC_*`에 시크릿 금지
- `.env.local` git 추적 금지
- 자격증명 입력 폼은 상태 보존 금지 (전송 직후 초기화)

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 워크플로우 에디터 첫 로드 (LCP) | < 2초 |
| SSE 첫 프레임 → 화면 표시 | < 100ms |
| 마켓플레이스 검색 | < 500ms (캐시 hit) / < 1초 (cold) |
| localStorage에 토큰 저장 | 0건 |
| dangerouslySetInnerHTML 사용 | 0건 |
| 브라우저 호환 | Chrome / Edge / Firefox 최신 + Safari 17+ |

## 테스트

```bash
npm run test      # Jest 단위 테스트
npm run lint      # ESLint 검사
npx tsc --noEmit  # 타입 체크
npx next build    # 빌드 검증
```
