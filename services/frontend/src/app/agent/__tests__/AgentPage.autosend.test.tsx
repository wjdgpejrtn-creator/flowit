import { render, screen, waitFor } from '@testing-library/react';

beforeAll(() => {
  Element.prototype.scrollIntoView = jest.fn();
  // @ts-expect-error jsdom has no EventSource
  global.EventSource = jest.fn(() => ({
    onmessage: null, onerror: null, close: jest.fn(),
  }));
});

// 홈에서 `/agent?q=...&autosend=1`로 진입하는 시나리오를 mock 차원에서 재현한다.
// URLSearchParams 인스턴스를 사례별로 교체하기 위해 wrapper 객체로 감쌌다.
const mockSearchParams = { value: new URLSearchParams() };
const mockRouterReplace = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    refresh: jest.fn(),
    replace: (...args: unknown[]) => mockRouterReplace(...args),
  }),
  useParams: () => ({}),
  usePathname: () => '/agent',
  useSearchParams: () => mockSearchParams.value,
}));

const mockStreamCreateSession = jest.fn().mockImplementation(
  (_req: unknown, _onFrame: unknown, _signal?: AbortSignal) => Promise.resolve(),
);
jest.mock('../../../lib/api/agentApi', () => ({
  streamCreateSession: (...args: unknown[]) => mockStreamCreateSession(...args),
  getStreamUrl: (id: string) => `/api/v1/ai/sessions/${id}/stream`,
  streamSlotAnswer: jest.fn(),
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
  mockRouterReplace.mockClear();
  mockSearchParams.value = new URLSearchParams();
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

describe('AgentPage — autosend (홈 ?q=&autosend=1 진입)', () => {
  it('q+autosend=1 있으면 mount 시 자동으로 SSE를 호출한다', async () => {
    mockSearchParams.value = new URLSearchParams('q=%EC%8A%AC%EB%9E%99%20%EC%95%8C%EB%A6%BC%20%EC%9B%8C%ED%81%AC%ED%94%8C%EB%A1%9C%EC%9A%B0&autosend=1');

    render(<AgentPage />);

    await waitFor(() => {
      expect(mockStreamCreateSession).toHaveBeenCalledTimes(1);
      expect(mockStreamCreateSession).toHaveBeenCalledWith(
        { message: '슬랙 알림 워크플로우', session_id: undefined },
        expect.any(Function),
        expect.any(AbortSignal),
      );
    });
  });

  it('autosend trigger 시 router.replace로 URL을 정리한다 (새로고침 재실행 방지)', async () => {
    mockSearchParams.value = new URLSearchParams('q=foo&autosend=1');

    render(<AgentPage />);

    await waitFor(() => {
      expect(mockRouterReplace).toHaveBeenCalledWith('/agent', { scroll: false });
    });
  });

  it('autosend 메시지가 input state 동기화와 무관하게 채팅에 즉시 표시된다', async () => {
    mockSearchParams.value = new URLSearchParams('q=%ED%85%8C%EC%8A%A4%ED%8A%B8%20%EC%9E%90%EB%8F%99%20%EC%A0%84%EC%86%A1&autosend=1');

    render(<AgentPage />);

    await waitFor(() => {
      expect(screen.getByText('테스트 자동 전송')).toBeInTheDocument();
    });
  });

  it('q만 있고 autosend가 없으면 자동 전송하지 않는다', async () => {
    mockSearchParams.value = new URLSearchParams('q=foo');

    render(<AgentPage />);

    // mount 후 짧은 대기 — autosend trigger 없음을 확인
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(mockStreamCreateSession).not.toHaveBeenCalled();
    expect(mockRouterReplace).not.toHaveBeenCalled();
  });
});
