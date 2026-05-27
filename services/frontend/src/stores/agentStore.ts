import { create } from 'zustand';

export type WorkspaceMode = 'wizard' | 'edit' | 'run';

export type AgentStep =
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
}

interface AgentStoreState {
  mode: WorkspaceMode;
  setMode: (mode: WorkspaceMode) => void;

  sessionId: string | null;
  sessions: AgentSession[];
  setSessionId: (id: string) => void;
  addSession: (session: AgentSession) => void;

  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;

  currentStep: AgentStep | null;
  setCurrentStep: (step: AgentStep | null) => void;

  rationaleText: string;
  appendRationale: (delta: string) => void;
  clearRationale: () => void;

  slotQuestion: SlotFillQuestion | null;
  setSlotQuestion: (q: SlotFillQuestion | null) => void;

  readyToExecute: { workflowId: string; message: string } | null;
  setReadyToExecute: (state: { workflowId: string; message: string } | null) => void;

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

  messages: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),

  currentStep: null,
  setCurrentStep: (step) => set({ currentStep: step }),

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
