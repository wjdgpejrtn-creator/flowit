import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowDetailPage from '../[id]/page';
import {
  getWorkflow,
  getLatestExecution,
  executeWorkflow,
  resumeExecution,
  pauseExecution,
  type WorkflowLatestExecution,
} from '../../../lib/api/workflowApi';
import type { WorkflowSchema } from '@common/generated';

// ReactFlow는 jsdom에서 렌더 불가 — 스텁.
jest.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="rf">{children}</div>,
  Background: () => null,
  Controls: () => null,
  useNodesState: (init: unknown) => [init, jest.fn(), jest.fn()],
  useEdgesState: (init: unknown) => [init, jest.fn(), jest.fn()],
}));

// AppBar는 next/navigation usePathname에 의존 — 테스트 무관하므로 스텁.
jest.mock('../../../components/common/AppBar', () => ({ __esModule: true, default: () => null }));
// 편집 패널도 store/캔버스 의존 — view 모드만 테스트하므로 스텁.
jest.mock('../../../components/workflow/WorkflowEditPane', () => ({ __esModule: true, default: () => null }));

jest.mock('../../../lib/api/workflowApi');

const mockGetWorkflow = getWorkflow as jest.MockedFunction<typeof getWorkflow>;
const mockGetLatest = getLatestExecution as jest.MockedFunction<typeof getLatestExecution>;
const mockExecute = executeWorkflow as jest.MockedFunction<typeof executeWorkflow>;
const mockResume = resumeExecution as jest.MockedFunction<typeof resumeExecution>;
const mockPause = pauseExecution as jest.MockedFunction<typeof pauseExecution>;

function makeWorkflow(nodes = 1): WorkflowSchema {
  return {
    workflow_id: 'wf-1',
    owner_user_id: null,
    name: '테스트 워크플로우',
    description: null,
    scope: 'private',
    is_draft: false,
    draft_spec: null,
    nodes: Array.from({ length: nodes }, (_, i) => ({
      instance_id: `n-${i}`,
      node_id: '11111111-1111-1111-1111-111111111111',
      parameters: {},
      credential_id: null,
      credential_ids: {},
      position: { x: 0, y: 0 },
    })),
    connections: [],
    version: 1,
    sha256: null,
    created_via_session_id: null,
  } as WorkflowSchema;
}

function exec(status: WorkflowLatestExecution['status']): WorkflowLatestExecution {
  return {
    execution_id: 'exec-1',
    workflow_id: 'wf-1',
    status,
    started_at: '2026-06-05T00:00:00Z',
    finished_at: null,
    error: null,
    node_states_summary: {},
    node_results: [],
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockGetWorkflow.mockResolvedValue(makeWorkflow());
});

describe('WorkflowDetailPage 실행/재개 버튼', () => {
  it('실행 이력이 없으면 ▶ 실행 버튼을 노출하고 클릭 시 executeWorkflow를 호출한다', async () => {
    mockGetLatest.mockResolvedValue(null);
    mockExecute.mockResolvedValue({ execution_id: 'exec-new', status: 'queued', task_id: 't-1' });

    render(<WorkflowDetailPage params={{ id: 'wf-1' }} />);

    const runBtn = await screen.findByText('▶ 실행');
    await userEvent.click(runBtn);
    expect(mockExecute).toHaveBeenCalledWith('wf-1');
  });

  it('완료된 실행이면 ↻ 다시 실행 버튼을 노출한다', async () => {
    mockGetLatest.mockResolvedValue(exec('completed'));

    render(<WorkflowDetailPage params={{ id: 'wf-1' }} />);

    expect(await screen.findByText('↻ 다시 실행')).toBeInTheDocument();
    expect(screen.queryByText('▶ 재개')).not.toBeInTheDocument();
  });

  it('일시정지 상태면 ▶ 재개 버튼을 노출하고 클릭 시 resumeExecution을 호출한다', async () => {
    mockGetLatest.mockResolvedValue(exec('paused'));
    mockResume.mockResolvedValue({ execution_id: 'exec-1', action: 'resume', task_id: 't-1' });

    render(<WorkflowDetailPage params={{ id: 'wf-1' }} />);

    const resumeBtn = await screen.findByText('▶ 재개');
    await userEvent.click(resumeBtn);
    expect(mockResume).toHaveBeenCalledWith('exec-1');
    expect(screen.queryByText('▶ 실행')).not.toBeInTheDocument();
  });

  it('실행 중이면 ⏸ 일시정지 버튼을 노출하고 클릭 시 pauseExecution을 호출한다', async () => {
    mockGetLatest.mockResolvedValue(exec('running'));
    mockPause.mockResolvedValue({ execution_id: 'exec-1', action: 'pause', task_id: 't-1' });

    render(<WorkflowDetailPage params={{ id: 'wf-1' }} />);

    const pauseBtn = await screen.findByText('⏸ 일시정지');
    await userEvent.click(pauseBtn);
    expect(mockPause).toHaveBeenCalledWith('exec-1');
  });
});
