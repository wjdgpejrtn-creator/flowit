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
  (_req: unknown, onFrame: (frame: Record<string, unknown>) => void, _signal?: AbortSignal) => {
    streamOnFrame = onFrame;
    return Promise.resolve();
  },
);
jest.mock('../../../lib/api/agentApi', () => ({
  streamCreateSession: (...args: unknown[]) => mockStreamCreateSession(...args),
  getStreamUrl: (id: string) => `/api/v1/ai/sessions/${id}/stream`,
  streamSlotAnswer: jest.fn(),
}));

jest.mock('../../../hooks/useSSEStream', () => ({
  useSSEStream: () => {},
}));

const mockValidateWorkflow = jest.fn();
jest.mock('../../../lib/api/workflowApi', () => ({
  executeWorkflow: jest.fn(),
  getWorkflow: jest.fn(() => Promise.resolve(null)),
  validateWorkflow: (...args: unknown[]) => mockValidateWorkflow(...args),
  // RunMode(저장 성공 → 실행 모드 전환)가 렌더될 때 호출하는 API 스텁
  getLatestExecution: jest.fn(() => Promise.resolve(null)),
  cancelExecution: jest.fn(),
  resumeExecution: jest.fn(),
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
  mockValidateWorkflow.mockReset();
  streamOnFrame = null;
  useAgentStore.setState({
    mode: 'wizard',
    sessionId: null,
    sessions: [],
    messages: [],
    currentStep: null,
    compositeFlow: false,
    rationaleText: '',
    slotQuestion: null,
    readyToExecute: null,
    sseFrames: [],
    artifactKind: 'workflow',
  });
});

describe('AgentPage — handleSend SSE 연동', () => {
  it('메시지 전송 시 streamCreateSession을 호출한다', async () => {
    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '슬랙 알림 워크플로우');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(mockStreamCreateSession).toHaveBeenCalledTimes(1);
      expect(mockStreamCreateSession).toHaveBeenCalledWith(
        { message: '슬랙 알림 워크플로우', session_id: undefined },
        expect.any(Function),
        expect.any(AbortSignal),
      );
    });
  });

  it('전송한 메시지가 채팅에 표시된다', async () => {
    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트 메시지');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

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

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(useAgentStore.getState().sessionId).toBe('sid-123');
    });
  });

  it('agent_node frame 수신 시 currentStep이 업데이트된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({ frame_type: 'agent_node', agent_node_name: 'security' });
        onFrame({ frame_type: 'agent_node', agent_node_name: 'intent' });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(useAgentStore.getState().currentStep).toBe('intent');
    });
  });

  it('복합 흐름(build_skill) 수신 시 compositeFlow가 켜지고 "스킬 생성" 단계가 채팅 인라인에 표시된다', async () => {
    // 작업과정은 스트리밍 중에만 채팅 인라인(AgentWorkProcess)으로 보이므로 스트림을 열어둔다.
    let resolveStream: () => void;
    mockStreamCreateSession.mockImplementation(
      (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) =>
        new Promise<void>((resolve) => {
          resolveStream = resolve;
          onFrame({ frame_type: 'session', session_id: 'sid-1' });
          onFrame({ frame_type: 'agent_node', agent_node_name: 'build_skill' });
          onFrame({ frame_type: 'agent_node', agent_node_name: 'composer' });   // 홉 마커 — 유지
          onFrame({ frame_type: 'agent_node', agent_node_name: 'security' });   // 컴포저 진입 — 전진
        }),
    );

    render(<AgentPage />);
    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '스킬 만들어서 워크플로우 만들어줘');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(useAgentStore.getState().compositeFlow).toBe(true);
      expect(useAgentStore.getState().currentStep).toBe('security');
    });
    // 선두 '스킬 생성'이 완료 단계로 채팅 인라인에 노출된다 (비복합이면 안 보임)
    expect(screen.getByText('스킬 생성 완료')).toBeInTheDocument();

    await act(async () => resolveStream!());
  });

  it('skill_builder_wizard frame 수신 시 스킬 캔버스로 전환 + 좌측 재료 선택 카드 노출 + 실행 모드 숨김 (REQ-010)', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({ frame_type: 'skill_builder_wizard' });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '스킬 만들어줘');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    // 산출물이 스킬로 전환된다(우측 캔버스 = 스킬 상세 편집).
    await waitFor(() => {
      expect(useAgentStore.getState().artifactKind).toBe('skill');
    });
    // 좌측 대화에 위저드 '재료 선택' 카드가 인라인으로 뜬다.
    expect(await screen.findByText('업무 관련 문서가 있으신가요?')).toBeInTheDocument();
    // 스킬은 실행 개념이 없으므로 모드 토글에서 '실행'은 숨겨진다(정확 매칭 — '실행 지침 도움말' 제외).
    expect(screen.queryByRole('button', { name: '실행' })).not.toBeInTheDocument();
  });

  it('result frame의 ready_to_execute 시 실행 버튼이 표시된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({
          frame_type: 'result',
          intent: 'create_workflow',
          payload: { status: 'ready_to_execute', workflow_id: 'wf-99', message: '실행 준비 완료' },
        });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

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

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(screen.getByText(/오류가 발생했습니다: 연결 실패/)).toBeInTheDocument();
    });
  });

  it('streamCreateSession 실패 시 연결 오류 메시지가 표시된다', async () => {
    mockStreamCreateSession.mockRejectedValueOnce(new Error('Failed to fetch'));

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

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

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('AI가 처리 중입니다…')).toBeDisabled();
      expect(screen.getByRole('button', { name: '전송' })).toBeDisabled();
    });

    await act(async () => resolveStream!());

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/이어서 말씀해/)).not.toBeDisabled();
      expect(screen.getByRole('button', { name: '전송' })).not.toBeDisabled();
    });
  });

  it('session frame 수신 후 후속 메시지에 sessionId가 포함된다', async () => {
    // 첫 번째 전송: session frame 수신 → sessionId 설정
    mockStreamCreateSession
      .mockImplementationOnce(
        async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
          onFrame({ frame_type: 'session', session_id: 'server-sid', langgraph_thread_id: 'tid-1' });
        },
      )
      .mockImplementationOnce(() => Promise.resolve());

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);

    await userEvent.type(textarea, '첫 메시지');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(useAgentStore.getState().sessionId).toBe('server-sid');
    });

    await userEvent.type(textarea, '후속 메시지');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(mockStreamCreateSession).toHaveBeenCalledTimes(2);
      expect(mockStreamCreateSession).toHaveBeenLastCalledWith(
        { message: '후속 메시지', session_id: 'server-sid' },
        expect.any(Function),
        expect.any(AbortSignal),
      );
    });
  });

  it('빈 메시지는 전송하지 않는다', async () => {
    render(<AgentPage />);
    await userEvent.click(screen.getByRole('button', { name: '전송' }));
    expect(mockStreamCreateSession).not.toHaveBeenCalled();
  });

  it('result frame의 payload.message가 채팅에 표시된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({
          frame_type: 'result',
          intent: 'create_workflow',
          payload: { message: 'AI 응답입니다' },
        });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(screen.getByText('AI 응답입니다')).toBeInTheDocument();
    });
  });

  it('slot_fill_question frame 수신 시 question이 표시된다', async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (frame: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({ frame_type: 'slot_fill_question', question: '대상 시트를 선택하세요', field_name: 'target_sheet' });
      },
    );

    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(useAgentStore.getState().slotQuestion).toEqual({
        fieldName: 'target_sheet',
        question: '대상 시트를 선택하세요',
      });
    });
  });

  it('AbortController signal이 streamCreateSession에 전달된다', async () => {
    render(<AgentPage />);

    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '테스트');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      const call = mockStreamCreateSession.mock.calls[0];
      expect(call[2]).toBeInstanceOf(AbortSignal);
    });
  });

  it('컨펌(readyToExecute) 상태에서 후속 메시지는 같은 세션을 이어간다 (refine, 새 채팅 X)', async () => {
    mockStreamCreateSession
      .mockImplementationOnce(async (_req: unknown, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({ frame_type: 'result', intent: 'propose', payload: { status: 'ready_to_execute', workflow_id: 'wf-1', message: '완성' } });
      })
      .mockImplementationOnce(() => Promise.resolve());

    render(<AgentPage />);
    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '슬랙 알림 워크플로우');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));
    await waitFor(() => expect(useAgentStore.getState().readyToExecute).not.toBeNull());

    // refine 후속 — 같은 세션 이어가야(이전엔 새 세션으로 리셋되는 버그)
    await userEvent.type(textarea, 'url을 바꿔줘');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    await waitFor(() => {
      expect(mockStreamCreateSession).toHaveBeenLastCalledWith(
        { message: 'url을 바꿔줘', session_id: 'sid-1' },  // 같은 session_id
        expect.any(Function),
        expect.any(AbortSignal),
      );
    });
    expect(useAgentStore.getState().sessions).toHaveLength(0);  // 새 세션 아카이브 안 함
    const contents = useAgentStore.getState().messages.map((m) => m.content);
    expect(contents).toContain('슬랙 알림 워크플로우');
    expect(contents).toContain('url을 바꿔줘');
  });

  it('컨펌 상태에서 refine 실패(ErrorFrame) 시 에러를 띄우고 카드(readyToExecute)는 사라진다', async () => {
    // #369: 카드 떠 있는 상태에서 파라미터 수정(refine) 요청 → 검증/QA 소진 시 백엔드는
    // ready_to_execute 대신 ErrorFrame(E_VALIDATION_EXHAUSTED)을 보낸다. 프론트는 에러 메시지를
    // 띄우고, ready_to_execute가 다시 오지 않으므로 카드는 복귀하지 않아야 한다(정혜님 플래그 케이스).
    mockStreamCreateSession
      .mockImplementationOnce(async (_req: unknown, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({ frame_type: 'result', intent: 'propose', payload: { status: 'ready_to_execute', workflow_id: 'wf-1', message: '완성' } });
      })
      .mockImplementationOnce(async (_req: unknown, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'error', code: 'E_VALIDATION_EXHAUSTED', message: '워크플로우 검증 3회 실패 — 요청을 더 구체적으로 말씀해 주세요.' });
      });

    render(<AgentPage />);
    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '슬랙 알림 워크플로우');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));
    await waitFor(() => expect(useAgentStore.getState().readyToExecute).not.toBeNull());

    // refine — 파라미터 수정 요청(같은 세션 이어감)
    await userEvent.type(textarea, '슬랙 채널을 마케팅으로 바꿔줘');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    // ErrorFrame → 에러 메시지 표시
    await waitFor(() => {
      expect(screen.getByText(/오류가 발생했습니다: 워크플로우 검증 3회 실패/)).toBeInTheDocument();
    });
    // 검증 실패라 ready_to_execute가 다시 오지 않음 → 카드는 복귀하지 않는다
    expect(useAgentStore.getState().readyToExecute).toBeNull();
  });

  it('컨펌 상태에서 refine 성공 시 ready_to_execute가 다시 와 카드가 재표시된다', async () => {
    // #369: 카드 떠 있는 상태에서 파라미터 수정(refine) 요청 → 검증/QA 통과 시 백엔드는
    // 처음 생성과 동일한 ready_to_execute를 다시 emit한다(#337). 프론트는 같은 result 핸들러로
    // 카드를 갱신해 다시 띄워야 한다 — 따로 처리 없이 자동 재표시되는지 고정한다.
    mockStreamCreateSession
      .mockImplementationOnce(async (_req: unknown, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({ frame_type: 'result', intent: 'propose', payload: { status: 'ready_to_execute', workflow_id: 'wf-1', message: '완성' } });
      })
      .mockImplementationOnce(async (_req: unknown, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'result', intent: 'propose', payload: { status: 'ready_to_execute', workflow_id: 'wf-2', message: '수정 완료' } });
      });

    render(<AgentPage />);
    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '슬랙 알림 워크플로우');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));
    await waitFor(() => expect(useAgentStore.getState().readyToExecute?.workflowId).toBe('wf-1'));

    // refine — 파라미터 수정 요청(같은 세션 이어감)
    await userEvent.type(textarea, '슬랙 채널을 마케팅으로 바꿔줘');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));

    // 수정 결과 ready_to_execute가 다시 와 카드가 새 워크플로우로 갱신·재표시된다
    await waitFor(() => {
      expect(useAgentStore.getState().readyToExecute).toEqual({
        workflowId: 'wf-2',
        message: '수정 완료',
      });
    });
  });
});

describe('AgentPage — 컨펌 게이트 저장 검증 피드백 위치 (#368)', () => {
  // 워크플로우 완성(ConfirmCard 노출) 상태까지 진입시키는 공용 셋업
  const arriveAtConfirmCard = async () => {
    mockStreamCreateSession.mockImplementation(
      async (_req: unknown, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({ frame_type: 'session', session_id: 'sid-1' });
        onFrame({
          frame_type: 'result',
          intent: 'propose',
          payload: { status: 'ready_to_execute', workflow_id: 'wf-1', message: '완성됐어요' },
        });
      },
    );
    render(<AgentPage />);
    const textarea = screen.getByPlaceholderText(/이어서 말씀해/);
    await userEvent.type(textarea, '슬랙 알림 워크플로우');
    await userEvent.click(screen.getByRole('button', { name: '전송' }));
    await waitFor(() => expect(useAgentStore.getState().readyToExecute).not.toBeNull());
  };

  it('검증 실패 시 에러가 ConfirmCard 아래에 표시되고 messages에 누수되지 않는다', async () => {
    mockValidateWorkflow.mockResolvedValue({
      validation_status: 'failed',
      errors: [{ message: 'Slack 채널 누락', hint: 'Slack 채널을 지정' }],
    });
    await arriveAtConfirmCard();

    await userEvent.click(screen.getByRole('button', { name: /저장하고 활성화/ }));

    const errorEl = await screen.findByText(/Slack 채널을 지정 부분 수정이 필요합니다/);
    // 에러는 messages가 아닌 별도 상태 → ConfirmCard('최종 확인') '뒤'에 위치해야 함
    const cardLabel = screen.getByText('최종 확인');
    expect(
      cardLabel.compareDocumentPosition(errorEl) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // messages 배열에는 들어가지 않음(위에 쌓이던 기존 버그 회귀 방지)
    expect(
      useAgentStore.getState().messages.some((m) => m.content.includes('수정이 필요합니다')),
    ).toBe(false);
  });

  it('검증 통과 시 실행 모드로 전환하고 에러를 표시하지 않는다', async () => {
    mockValidateWorkflow.mockResolvedValue({ validation_status: 'passed', errors: [] });
    await arriveAtConfirmCard();

    await userEvent.click(screen.getByRole('button', { name: /저장하고 활성화/ }));

    await waitFor(() => expect(useAgentStore.getState().mode).toBe('run'));
    expect(screen.queryByText(/수정이 필요합니다/)).not.toBeInTheDocument();
  });
});
