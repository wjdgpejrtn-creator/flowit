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
    useAgentStore.getState().addSession({ id: 's-1', title: 'First', createdAt: 1 });
    useAgentStore.getState().addSession({ id: 's-2', title: 'Second', createdAt: 2 });
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
