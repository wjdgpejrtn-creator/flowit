import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

beforeAll(() => {
  Element.prototype.scrollIntoView = jest.fn();
  // @ts-expect-error jsdom has no EventSource
  global.EventSource = jest.fn(() => ({
    onmessage: null, onerror: null, close: jest.fn(),
  }));
});

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), refresh: jest.fn() }),
  useParams: () => ({}),
  usePathname: () => '/agent',
  useSearchParams: () => new URLSearchParams(),
}));

let streamOnFrame: ((frame: Record<string, unknown>) => void) | null = null;
const mockStreamCreateSession = jest.fn().mockImplementation(
  (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
    streamOnFrame = onFrame;
    return Promise.resolve();
  },
);
jest.mock('../../../lib/api/agentApi', () => ({
  streamCreateSession: (...args: unknown[]) => mockStreamCreateSession(...args),
  getStreamUrl: (id: string) => `/api/v1/ai/sessions/${id}/stream`,
  sendSlotAnswer: jest.fn(),
}));

jest.mock('../../../hooks/useSSEStream', () => ({
  useSSEStream: () => {},
}));

jest.mock('../../../lib/api/workflowApi', () => ({
  executeWorkflow: jest.fn(),
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

jest.mock('@xyflow/react', () => ({
  ReactFlow: () => <div data-testid="reactflow" />,
  Background: () => null,
  Controls: () => null,
  useNodesState: (n: unknown[]) => [n, jest.fn(), jest.fn()],
  useEdgesState: (e: unknown[]) => [e, jest.fn(), jest.fn()],
}));

import AgentPage from '../page';
import { useAgentStore } from '../../../stores/agentStore';

beforeEach(() => {
  mockStreamCreateSession.mockClear();
  streamOnFrame = null;
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

describe('AgentPage — handleSend SSE 연동', () => {
  it('메시지 전송 시 streamCreateSession을 호출한다', async () => {
    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '슬랙 알림 워크플로우');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(mockStreamCreateSession).toHaveBeenCalledTimes(1);
      expect(mockStreamCreateSession).toHaveBeenCalledWith(
        { message: '슬랙 알림 워크플로우', session_id: undefined },
        expect.any(Function),
      );
    });
  });

  it('전송한 메시지가 채팅에 표시된다', async () => {
    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '테스트 메시지');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(screen.getByText('테스트 메시지')).toBeInTheDocument();
    });
  });

  it('session frame 수신 시 sessionId가 설정된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-123', langgraph_thread_id: 'tid-1' });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(useAgentStore.getState().sessionId).toBe('sid-123');
    });
  });

  it('agent_node frame 수신 시 currentStep이 업데이트된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({ frame_type: 'agent_node', node_name: 'security' });
        onFrame({ frame_type: 'agent_node', node_name: 'intent' });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(useAgentStore.getState().currentStep).toBe('intent');
    });
  });

  it('result frame의 ready_to_execute 시 실행 버튼이 표시된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({
          frame_type: 'result',
          message: '워크플로우 완성!',
          payload: { status: 'ready_to_execute', workflow_id: 'wf-99', message: '실행 준비 완료' },
        });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(useAgentStore.getState().readyToExecute).toEqual({
        workflowId: 'wf-99',
        message: '실행 준비 완료',
      });
    });
  });

  it('error frame 수신 시 에러 메시지가 채팅에 표시된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'error', code: 'E_PROXY', message: '연결 실패' });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(screen.getByText(/오류가 발생했습니다: 연결 실패/)).toBeInTheDocument();
    });
  });

  it('streamCreateSession 실패 시 연결 오류 메시지가 표시된다', async () => {
    mockStreamCreateSession.mockRejectedValueOnce(new Error('Failed to fetch'));

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(screen.getByText(/연결 오류: Failed to fetch/)).toBeInTheDocument();
    });
  });

  it('스트리밍 중 입력이 비활성화된다', async () => {
    let resolveStream: () => void;
    mockStreamCreateSession.mockImplementation(
      () => new Promise<void>((resolve) => { resolveStream = resolve; }),
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('AI가 처리 중입니다…')).toBeDisabled();
      expect(screen.getByRole('button', { name: '처리 중…' })).toBeDisabled();
    });

    await act(async () => resolveStream!());

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/워크플로우를 자연어로/)).not.toBeDisabled();
      expect(screen.getByRole('button', { name: '전송 ↑' })).not.toBeDisabled();
    });
  });

  it('기존 sessionId가 있으면 요청에 포함한다', async () => {
    useAgentStore.setState({ sessionId: 'existing-sid' });

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/워크플로우를 자연어로/);
    await userEvent.type(textarea, '후속 메시지');
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));

    await waitFor(() => {
      expect(mockStreamCreateSession).toHaveBeenCalledWith(
        { message: '후속 메시지', session_id: 'existing-sid' },
        expect.any(Function),
      );
    });
  });

  it('빈 메시지는 전송하지 않는다', async () => {
    render(<AgentPage />);
    await userEvent.click(screen.getByRole('button', { name: '전송 ↑' }));
    expect(mockStreamCreateSession).not.toHaveBeenCalled();
  });
});
