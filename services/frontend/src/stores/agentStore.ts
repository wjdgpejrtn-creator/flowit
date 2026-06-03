import { create } from 'zustand';
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

export interface AgentSession {
  id: string;
  title: string;
  createdAt: number;
  messages: ChatMessage[];
}

interface AgentStoreState {
  mode: WorkspaceMode;
  setMode: (mode: WorkspaceMode) => void;

  sessionId: string | null;
  sessions: AgentSession[];
  setSessionId: (id: string) => void;
  addSession: (session: AgentSession) => void;

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

  slotQuestion: SlotFillQuestion | null;
  setSlotQuestion: (q: SlotFillQuestion | null) => void;

  readyToExecute: { workflowId: string; message: string; explanation?: WorkflowExplanation } | null;
  setReadyToExecute: (state: { workflowId: string; message: string; explanation?: WorkflowExplanation } | null) => void;

  sseFrames: string[];
  appendSSEFrame: (frame: string) => void;
}

export const useAgentStore = create<AgentStoreState>((set) => ({
  mode: 'wizard',
  setMode: (mode) => set({ mode }),

  sessionId: null,
  sessions: [],
  setSessionId: (id) => set({ sessionId: id }),
  addSession: (session) =>
    set((s) => ({ sessions: [session, ...s.sessions] })),

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

  slotQuestion: null,
  setSlotQuestion: (q) => set({ slotQuestion: q }),

  readyToExecute: null,
  setReadyToExecute: (state) => set({ readyToExecute: state }),

  sseFrames: [],
  appendSSEFrame: (frame) =>
    set((s) => ({ sseFrames: [...s.sseFrames, frame] })),
}));
