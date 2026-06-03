import { useAgentStore } from '../agentStore';

beforeEach(() => {
  useAgentStore.setState({
    mode: 'wizard',
    sessionId: null,
    sessions: [],
    messages: [],
    currentStep: null,
    rationaleText: '',
    slotQuestion: null,
    readyToExecute: null,
    sseFrames: [],
  });
});

describe('mode', () => {
  it('setMode updates mode', () => {
    useAgentStore.getState().setMode('edit');
    expect(useAgentStore.getState().mode).toBe('edit');
  });
});

describe('messages', () => {
  it('addMessage appends to list', () => {
    const msg = { id: 'm-1', role: 'user' as const, content: 'Hi', timestamp: 1 };
    useAgentStore.getState().addMessage(msg);
    expect(useAgentStore.getState().messages).toHaveLength(1);
    expect(useAgentStore.getState().messages[0]).toEqual(msg);
  });

  it('clearMessages empties list', () => {
    useAgentStore.getState().addMessage({ id: 'm-1', role: 'user', content: 'Hi', timestamp: 1 });
    useAgentStore.getState().clearMessages();
    expect(useAgentStore.getState().messages).toHaveLength(0);
  });
});

describe('sessions', () => {
  it('addSession prepends (newest first)', () => {
    useAgentStore.getState().addSession({ id: 's-1', title: 'First', createdAt: 1, messages: [] });
    useAgentStore.getState().addSession({ id: 's-2', title: 'Second', createdAt: 2, messages: [] });
    expect(useAgentStore.getState().sessions[0].id).toBe('s-2');
  });
});

describe('rationale', () => {
  it('appendRationale accumulates text', () => {
    useAgentStore.getState().appendRationale('Hello ');
    useAgentStore.getState().appendRationale('world');
    expect(useAgentStore.getState().rationaleText).toBe('Hello world');
  });

  it('clearRationale resets to empty string', () => {
    useAgentStore.getState().appendRationale('some text');
    useAgentStore.getState().clearRationale();
    expect(useAgentStore.getState().rationaleText).toBe('');
  });
});

describe('SSE frames', () => {
  it('appendSSEFrame appends in order', () => {
    useAgentStore.getState().appendSSEFrame('frame1');
    useAgentStore.getState().appendSSEFrame('frame2');
    expect(useAgentStore.getState().sseFrames).toEqual(['frame1', 'frame2']);
  });
});

describe('slotQuestion', () => {
  it('setSlotQuestion sets and clears', () => {
    const q = { fieldName: 'target', question: '대상 시트를 선택하세요' };
    useAgentStore.getState().setSlotQuestion(q);
    expect(useAgentStore.getState().slotQuestion).toEqual(q);
    useAgentStore.getState().setSlotQuestion(null);
    expect(useAgentStore.getState().slotQuestion).toBeNull();
  });
});

describe('readyToExecute', () => {
  it('setReadyToExecute sets workflow info', () => {
    const state = { workflowId: 'wf-123', message: '실행 버튼을 클릭해 실행하세요.' };
    useAgentStore.getState().setReadyToExecute(state);
    expect(useAgentStore.getState().readyToExecute).toEqual(state);
  });

  it('setReadyToExecute clears to null', () => {
    useAgentStore.getState().setReadyToExecute({ workflowId: 'wf-123', message: '...' });
    useAgentStore.getState().setReadyToExecute(null);
    expect(useAgentStore.getState().readyToExecute).toBeNull();
  });
});

describe('세션 아카이브/복원 (전체 상태 보존)', () => {
  it('addSession은 같은 id를 갱신(중복 누적 방지)', () => {
    const base = { id: 's1', title: 'A', createdAt: 1, messages: [] };
    useAgentStore.getState().addSession(base);
    useAgentStore.getState().addSession({ ...base, title: 'A-updated' });
    const { sessions } = useAgentStore.getState();
    expect(sessions).toHaveLength(1);
    expect(sessions[0].title).toBe('A-updated');
  });

  it('restoreSession은 워크플로우/판단근거/단계를 active로 복원하고 목록에서 제거', () => {
    const snap = {
      id: 'server-sid-9', title: '캠페인', createdAt: 1,
      messages: [{ id: 'm1', role: 'user' as const, content: '슬랙 알림', timestamp: 1 }],
      readyToExecute: { workflowId: 'wf-9', message: '완성' },
      rationaleText: '판단근거 텍스트',
      currentStep: 'promote' as const,
      compositeFlow: true,
    };
    useAgentStore.getState().addSession(snap);
    useAgentStore.getState().restoreSession(snap);
    const s = useAgentStore.getState();
    expect(s.sessionId).toBe('server-sid-9');           // 서버 세션 id 복원(continue/refine 가능)
    expect(s.readyToExecute).toEqual({ workflowId: 'wf-9', message: '완성' });
    expect(s.rationaleText).toBe('판단근거 텍스트');
    expect(s.currentStep).toBe('promote');
    expect(s.compositeFlow).toBe(true);
    expect(s.messages).toHaveLength(1);
    expect(s.sessions.find((x) => x.id === 'server-sid-9')).toBeUndefined();  // active 승격 → 목록 제거
  });

  it('local-* 세션 복원 시 sessionId는 비움(서버 세션 아님)', () => {
    const snap = { id: 'local-123', title: 'x', createdAt: 1, messages: [], readyToExecute: { workflowId: 'wf-1', message: 'm' } };
    useAgentStore.getState().restoreSession(snap);
    expect(useAgentStore.getState().sessionId).toBe('');
    expect(useAgentStore.getState().readyToExecute).toEqual({ workflowId: 'wf-1', message: 'm' });
  });

  it('구버전 아카이브(스냅샷 필드 없음) 복원은 기본값으로 안전', () => {
    const legacy = { id: 's-legacy', title: 'old', createdAt: 1, messages: [] };
    useAgentStore.getState().restoreSession(legacy);
    const s = useAgentStore.getState();
    expect(s.readyToExecute).toBeNull();
    expect(s.rationaleText).toBe('');
    expect(s.currentStep).toBeNull();
    expect(s.compositeFlow).toBe(false);
  });
});
