# frontend

> REQ-010: Next.js 14 + React Flow 캔버스 + AI 챗 패널 + 실행 뷰어

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

## Quick Start (타입 import)

```typescript
// common-schemas에서 생성된 타입 사용
import type { WorkflowSchema, NodeInstance, Edge } from "@common/generated";
import type { SSEFrame, AgentNodeFrame } from "@common/generated";

// 내부 컴포넌트
import { WorkflowCanvas } from "@/components/canvas";
import { ChatPanel } from "@/components/chat";
import { ExecutionViewer } from "@/components/execution";
```

## 주요 컴포넌트

### components/canvas — 워크플로우 캔버스

| 컴포넌트 | 설명 |
|----------|------|
| `WorkflowCanvas` | React Flow 기반 워크플로우 에디터 (드래그 앤 드롭) |
| `NodePanel` | 노드 팔레트 (54종 노드 카탈로그) |
| `EdgeEditor` | 엣지 조건 편집기 |

### components/chat — AI 에이전트 채팅

| 컴포넌트 | 설명 |
|----------|------|
| `ChatPanel` | 실시간 대화 패널 (SSE 스트리밍) |
| `MessageBubble` | 메시지 버블 (사용자/에이전트) |
| `SlotFillForm` | 온보딩 질문 폼 |

### components/execution — 실행 모니터링

| 컴포넌트 | 설명 |
|----------|------|
| `ExecutionViewer` | 노드별 실행 상태 시각화 |
| `LogStream` | 실시간 로그 스트리밍 |
| `ResultPanel` | 실행 결과 표시 |

### stores/ — Zustand 상태 관리 (5개)

| 스토어 | 상태 |
|--------|------|
| `editor-store` | 현재 워크플로우 / dirty / undo-redo (zundo) / validationErrors / pendingDraft |
| `composer-store` | SSE 스트림 상태 / agent_node 인디케이터 / draft_spec_delta / Time-travel checkpoints |
| `skill-wizard-store` | WizardDraft / followUpQueue / proposedSkills |
| `consultant-store` | Onboarding Consultant slot_filling_state |
| `connections-store` | 외부 서비스 연결 캐시 (REQ-002 GET /connections) |

### TanStack Query 키

| 키 | 용도 |
|----|------|
| `['workflows']` | 워크플로우 목록 |
| `['workflow', id]` | 단일 워크플로우 |
| `['execution', id]` | 실행 상태 (TERMINAL_STATUSES 까지 폴링) |
| `['nodes', 'catalog']` | 노드 카탈로그 |
| `['skills', filters]` | Skill 라이브러리 |
| `['marketplace', searchKey]` | 마켓플레이스 검색 결과 |
| `['connections']` | 외부 서비스 연결 |
| `['account', 'sessions']` | 세션 목록 |

### services/ — API 클라이언트

| 서비스 | 설명 |
|--------|------|
| `apiClient` | Axios/Fetch 래퍼 (인증 헤더 자동 주입) |
| `sseParser` | SSE 스트림 파서 (EventSource 기반) |

## 경로 별칭

| 별칭 | 실제 경로 |
|------|----------|
| `@/*` | `./src/*` |
| `@common/*` | `../../packages/common-schemas/typescript/src/*` |

## 라우트 카탈로그

| 경로 | 설명 | 주요 컴포넌트 |
|------|------|-------------|
| `/` | 워크플로우 목록 + Skill Wizard 진입 | WorkflowsList, OnboardingEntry |
| `/workflows/[id]` | 워크플로우 에디터 | WorkflowCanvas, NodePalette, PropertyPanel, ChatPanel, TimeTravelPanel |
| `/skills/new` | Skill Bootstrap Wizard 진입 | DomainPicker, AskingTurn, WizardDraft |
| `/skills` | Skill 라이브러리 (5 상태 필터) | SkillCard, SkillFilters, ProposedBanner |
| `/skills/marketplace` | 전사 / 팀 마켓플레이스 | MarketplaceSearch, FeaturedRow, SkillDetailDrawer |
| `/connections` | 외부 서비스 연결 관리 | ConnectionList, ConnectButton, ReconnectCTA |
| `/account` | 프로필 / 부서 / 세션 | AccountSummary |
| `/account/sessions` | 활성 / 최근 세션 + Resume / End | SessionList, ResumeButton |
| `/account/memories` | 조직 메모리 통찰 (Phase 2) | MemoryViewer |

## Risk Level 배지 + Permission Filter

| risk_level | 배지 색상 | User 권한 동작 | Admin 권한 동작 |
|-----------|----------|-------------|---------------|
| Low | 회색 | 정상 | 정상 |
| Medium | 노랑 | 정상 | 정상 |
| High | 주황 | 정상 (미연결 시 "Connect first" CTA) | 정상 |
| Restricted | 빨강 | 회색 처리 + 드래그 차단 + tooltip "관리자만 사용 가능" | 정상 |

## Validator 에러 노드 강조

- `errors[].node_ids` → React Flow 캔버스에서 해당 노드를 **Red outline + 경고 아이콘 badge** 로 강조
- `errors[].edge_id` → 엣지를 Red 대시 처리
- 노드 클릭 시 PropertyPanel에 `errors[].hint` 표시 + "자동 수정 적용" 버튼

## Draft Spec 시각화

- `workflow.is_draft=true`이고 `draft_spec` 존재 시 캔버스 상단에 "Draft from Consultant" 배너
- `draft_spec.unresolved_nodes`는 점선 스타일 노드로 표시

## SSE 프레임 처리

| 프레임 | UI 처리 |
|--------|---------|
| `session` | composer-store에 chat_session_id + langgraph_thread_id 저장 |
| `agent_node` | 채팅 상단 "현재 단계" 인디케이터 |
| `rationale_delta` | 접을 수 있는 "AI 사고 과정" 영역에 스트림 조립 |
| `slot_fill_question` | chip 형태 (예: 아니오 / 자유 입력) |
| `draft_spec_delta` | Draft Spec 시각화와 연결, 카드 형태 렌더 |
| `result.intent` | {clarify, draft, refine, propose} 분기. propose → Skill 수락 배너 |
| `error` | 표준 에러 스키마 → Validator 강조 + 채팅 에러 보드 |

## Time-travel UI

- 채팅 패널 우측에 타임라인 아이콘 → LangGraph thread checkpoint 타임라인 패널
- 각 카드: AgentNode 실행 시점 + agent_node_name + timestamp + 1줄 요약
- "이 시점으로 되돌리기" → `POST /api/v1/ai/compose/rewind`로 thread 되돌린 후 재스트림

## 마켓플레이스 탭 (FR-010-15)

- `/skills/marketplace`에서 Public + Team 스킬 검색 (하이브리드)
- 검색 바: 자연어 프롬프트 → MarketplaceSkillRepository.search 호출
- 카드 메타: Featured/Official/Pinned 테두리 + 통계 + 의존성 아이콘
- 상세: condition/action/rationale + sources + 평균 별점 + 리뷰 리스트 + 의존성 그래프
- deprecated_at 설정 스킬: 회색 처리 + replaced_by 링크

## 세션 / 메모리 관리 (FR-010-14)

- `/account/sessions`: 활성/최근 90일 세션 목록
- 세션 복원: 24시간 cutoff 이내 [Resume], 초과 [View Transcript]만
- [End Session]: Redis flush + chat_message_summaries 생성 트리거

## 외부 서비스 연결 (FR-010-12)

- `/connections`: Google / Slack 연결 상태 (MVP — Microsoft/Notion 제외)
- [Connect] / [Disconnect] / [Reconnect] 버튼
- 미연결 노드 선택 시 모달 + `/connections` 딥링크

## 의존 관계

```
이 서비스 → common-schemas/typescript (타입 정의 — @common/generated, REQ-012)
이 서비스 → api-server (HTTP REST + SSE 스트리밍)
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
- UI 텍스트 영어 통일

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 워크플로우 에디터 첫 로드 (LCP) | < 2초 |
| SSE 첫 프레임 → 화면 표시 | < 100ms |
| 마켓플레이스 검색 | < 500ms (캐시 hit) / < 1초 (cold) |
| localStorage에 토큰 저장 | 0건 |
| dangerouslySetInnerHTML 사용 | 0건 |
| 브라우저 호환 | Chrome / Edge / Firefox 최신 + Safari 17+ |

## PR 오픈 전 필수 검증

```bash
npx tsc --noEmit
npx next lint
npx next build
npx playwright test ai-composer skill-wizard smoke marketplace
```

## 테스트

```bash
npm run test      # Jest 단위 테스트
npm run lint      # ESLint 검사
```
