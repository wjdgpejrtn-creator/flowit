import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { WorkflowExplanation } from '@common/generated';

export type WorkspaceMode = 'wizard' | 'edit' | 'run';

export type AgentStep =
  | 'skill'      // 복합(skill_then_compose) 흐름의 선두 단계 — 스킬 빌드 홉
  | 'security'
  | 'intent'
  | 'retriever'
  | 'drafter'
  | 'validator'
  | 'qa_eval'
  | 'promote';

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: number;
}

export interface SlotFillQuestion {
  fieldName: string;
  question: string;
}

// 검증 메시지 "검증 상세 보기" 패널용 — 스트리밍 중 SSE 프레임에서 캡처한 단계별 기록.
// (intent_result / qa_metric / workflow_draft). 백엔드가 안 보내는 필드는 비워두고 graceful.
export interface VerifyData {
  intentType?: string;                     // intent_result.intent
  intentEntities?: Record<string, unknown>; // intent_result.entities
  qaScore?: number;                         // qa_metric.score
  qaPassed?: boolean;                       // qa_metric.pass_flag
  draftNodeCount?: number;                  // workflow_draft.nodes.length
  draftConnCount?: number;                  // workflow_draft.connections.length
}

export interface AgentSession {
  id: string;
  title: string;
  createdAt: number;
  messages: ChatMessage[];
  // 전체 상태 스냅샷 — 이전 대화로 돌아갈 때 워크플로우/ConfirmCard/판단근거까지 복원.
  // 구버전 아카이브(미저장) 호환 위해 전부 optional.
  readyToExecute?: { workflowId: string; message: string; explanation?: WorkflowExplanation } | null;
  rationaleText?: string;
  currentStep?: AgentStep | null;
  compositeFlow?: boolean;
  verify?: VerifyData;
}

interface AgentStoreState {
  mode: WorkspaceMode;
  setMode: (mode: WorkspaceMode) => void;

  sessionId: string | null;
  sessions: AgentSession[];
  setSessionId: (id: string) => void;
  addSession: (session: AgentSession) => void;
  // 아카이브된 세션을 active로 복원(전체 상태). 목록에서 제거하고 store top-level에 적재.
  restoreSession: (session: AgentSession) => void;

  viewingSession: AgentSession | null;
  setViewingSession: (session: AgentSession | null) => void;

  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;

  currentStep: AgentStep | null;
  setCurrentStep: (step: AgentStep | null) => void;

  // 복합(skill_then_compose) 흐름 여부 — true면 단계 표시에 '스킬 생성' 선두 단계를 노출한다.
  // skill 단계 진입 시 set, 새 턴(handleSend/handleNewChat)에서만 reset (라운드2 resume은 유지).
  compositeFlow: boolean;
  setCompositeFlow: (v: boolean) => void;

  rationaleText: string;
  appendRationale: (delta: string) => void;
  clearRationale: () => void;

  // 검증 메시지 상세 기록 — 스트리밍 중 누적, 새 턴마다 reset.
  verify: VerifyData;
  setVerify: (patch: Partial<VerifyData>) => void;
  resetVerify: () => void;

  slotQuestion: SlotFillQuestion | null;
  setSlotQuestion: (q: SlotFillQuestion | null) => void;

  readyToExecute: { workflowId: string; message: string; explanation?: WorkflowExplanation } | null;
  setReadyToExecute: (state: { workflowId: string; message: string; explanation?: WorkflowExplanation } | null) => void;

  sseFrames: string[];
  appendSSEFrame: (frame: string) => void;
}

// persist(localStorage) 누적 상한 — 각 세션이 전체 messages를 보유하므로 무한 누적 시
// 브라우저 localStorage 한계(5~10MB)에 도달할 수 있다. 최근 N개만 유지(오래된 대화 eviction).
const MAX_PERSISTED_SESSIONS = 30;

export const useAgentStore = create<AgentStoreState>()(
  persist(
    (set) => ({
  mode: 'wizard',
  setMode: (mode) => set({ mode }),

  sessionId: null,
  sessions: [],
  setSessionId: (id) => set({ sessionId: id }),
  addSession: (session) =>
    // 같은 id는 갱신(아카이브 idempotent — 세션 전환 왕복 시 중복 누적 방지).
    // 최근 MAX_PERSISTED_SESSIONS개로 상한 — localStorage quota 누적 방지(가장 오래된 것부터 제거).
    set((s) => ({
      sessions: [session, ...s.sessions.filter((x) => x.id !== session.id)].slice(0, MAX_PERSISTED_SESSIONS),
    })),

  restoreSession: (session) =>
    set((s) => ({
      // local-* id는 서버 세션이 아니므로 sessionId 비움(워크플로우는 readyToExecute로 실행 가능).
      sessionId: session.id.startsWith('local-') ? '' : session.id,
      messages: [...session.messages],
      readyToExecute: session.readyToExecute ?? null,
      rationaleText: session.rationaleText ?? '',
      currentStep: session.currentStep ?? null,
      compositeFlow: session.compositeFlow ?? false,
      verify: session.verify ?? {},
      slotQuestion: null,
      viewingSession: null,
      sessions: s.sessions.filter((x) => x.id !== session.id),  // active로 승격 → 목록에서 제거
    })),

  viewingSession: null,
  setViewingSession: (session) => set({ viewingSession: session }),

  messages: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),

  currentStep: null,
  setCurrentStep: (step) => set({ currentStep: step }),

  compositeFlow: false,
  setCompositeFlow: (v) => set({ compositeFlow: v }),

  rationaleText: '',
  appendRationale: (delta) =>
    set((s) => ({ rationaleText: s.rationaleText + delta })),
  clearRationale: () => set({ rationaleText: '' }),

  verify: {},
  setVerify: (patch) => set((s) => ({ verify: { ...s.verify, ...patch } })),
  resetVerify: () => set({ verify: {} }),

  slotQuestion: null,
  setSlotQuestion: (q) => set({ slotQuestion: q }),

  readyToExecute: null,
  setReadyToExecute: (state) => set({ readyToExecute: state }),

  sseFrames: [],
  appendSSEFrame: (frame) =>
    set((s) => ({ sseFrames: [...s.sseFrames, frame] })),
    }),
    {
      // 새로고침(F5/Shift+Ctrl+R)에도 대화내역이 살아남도록 localStorage 영속화.
      // 새로고침 후 이어쓰기/복원은 page.tsx 마운트 가드(문서 최초 로드 시 유지)와 함께 동작한다.
      name: 'flowit-agent',
      storage: createJSONStorage(() => localStorage),
      version: 1,
      // 영속 대상 = 대화 맥락(durable)만. mode/viewingSession/slotQuestion/sseFrames 같은
      // 일시 UI 상태와 streaming 파생값은 새로고침 시 재계산되므로 저장하지 않는다.
      partialize: (s) => ({
        sessionId: s.sessionId,
        sessions: s.sessions,
        messages: s.messages,
        readyToExecute: s.readyToExecute,
        rationaleText: s.rationaleText,
        currentStep: s.currentStep,
        compositeFlow: s.compositeFlow,
        verify: s.verify,
      }),
    },
  ),
);
