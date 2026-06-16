import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RiskLevel, ExecutionStatus } from '@common/generated';
import type { WorkflowSchema, NodeConfig } from '@common/generated';
import RunMode from '../RunMode';
import { useWorkflowStore } from '../../../stores/workflowStore';
import {
  getLatestExecution,
  executeWorkflow,
  cancelExecution,
  pauseExecution,
  resumeExecution,
  type WorkflowLatestExecution,
} from '../../../lib/api/workflowApi';
import { getCatalog } from '../../../lib/api/nodeApi';

jest.mock('../../../lib/api/workflowApi');
jest.mock('../../../lib/api/nodeApi');

const mockGetLatest = getLatestExecution as jest.MockedFunction<typeof getLatestExecution>;
const mockExecute = executeWorkflow as jest.MockedFunction<typeof executeWorkflow>;
const mockCancel = cancelExecution as jest.MockedFunction<typeof cancelExecution>;
const mockPause = pauseExecution as jest.MockedFunction<typeof pauseExecution>;
const mockResume = resumeExecution as jest.MockedFunction<typeof resumeExecution>;
const mockGetCatalog = getCatalog as jest.MockedFunction<typeof getCatalog>;

const NODE_ID_A = '11111111-1111-1111-1111-111111111111';
const NODE_ID_B = '22222222-2222-2222-2222-222222222222';

const catalog: NodeConfig[] = [
  {
    node_id: NODE_ID_A,
    node_type: 'google_sheets_read',
    name: 'Google Sheets',
    category: 'google_workspace',
    version: '1.0.0',
    input_schema: {},
    output_schema: {},
    parameter_schema: {},
    risk_level: RiskLevel.MEDIUM,
    required_connections: ['google_workspace'],
    description: '',
    is_mvp: true,
  },
  {
    node_id: NODE_ID_B,
    node_type: 'slack_notify',
    name: 'Slack 알림',
    category: 'slack',
    version: '1.0.0',
    input_schema: {},
    output_schema: {},
    parameter_schema: {},
    risk_level: RiskLevel.HIGH,
    required_connections: ['slack'],
    description: '',
    is_mvp: true,
  },
];

function makeWorkflow(): WorkflowSchema {
  return {
    workflow_id: 'wf-1',
    owner_user_id: null,
    name: 'Test',
    description: null,
    scope: 'private',
    is_draft: false,
    draft_spec: null,
    nodes: [
      { instance_id: 'n-a', node_id: NODE_ID_A, parameters: {}, credential_id: null, credential_ids: {}, position: { x: 0, y: 0 } },
      { instance_id: 'n-b', node_id: NODE_ID_B, parameters: {}, credential_id: null, credential_ids: {}, position: { x: 0, y: 0 } },
    ],
    connections: [],
    version: 1,
    sha256: null,
    created_via_session_id: null,
  };
}

function latest(status: ExecutionStatus, nodeResults: WorkflowLatestExecution['node_results']): WorkflowLatestExecution {
  return {
    execution_id: 'exec-1',
    workflow_id: 'wf-1',
    status,
    started_at: '2026-06-04T00:00:00Z',
    finished_at: null,
    error: null,
    node_states_summary: {},
    node_results: nodeResults,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockGetCatalog.mockResolvedValue(catalog);
  useWorkflowStore.setState({ workflow: makeWorkflow(), activeExecutionId: null });
});

afterEach(() => {
  useWorkflowStore.setState({ workflow: null, activeExecutionId: null });
});

describe('RunMode', () => {
  it('워크플로우가 없으면 안내 메시지를 렌더한다', () => {
    useWorkflowStore.setState({ workflow: null });
    render(<RunMode />);
    expect(screen.getByText(/실행할 워크플로우가 없습니다/)).toBeInTheDocument();
  });

  it('실행 중이면 node_results를 노드 카드 상태로 렌더하고 취소 버튼이 cancelExecution을 호출한다', async () => {
    mockGetLatest.mockResolvedValue(
      latest(ExecutionStatus.RUNNING, [
        { node_instance_id: 'n-a', status: 'succeeded' },
        { node_instance_id: 'n-b', status: 'running' },
      ]),
    );
    mockCancel.mockResolvedValue({ execution_id: 'exec-1', action: 'cancel', task_id: 't-1' });

    render(<RunMode />);

    expect(await screen.findByText('진행중')).toBeInTheDocument();
    // 카탈로그 메타가 노드 이름으로 반영
    expect(await screen.findByText('Google Sheets')).toBeInTheDocument();
    expect(screen.getByText('Slack 알림')).toBeInTheDocument();
    // 1/2 완료 (n-a succeeded)
    expect(screen.getByText('1 / 2 노드 완료')).toBeInTheDocument();

    await userEvent.click(screen.getByText('⏹ 취소'));
    expect(mockCancel).toHaveBeenCalledWith('exec-1');
  });

  it('실행 중이면 일시정지 버튼이 pauseExecution을 호출한다', async () => {
    mockGetLatest.mockResolvedValue(
      latest(ExecutionStatus.RUNNING, [
        { node_instance_id: 'n-a', status: 'succeeded' },
        { node_instance_id: 'n-b', status: 'running' },
      ]),
    );
    mockPause.mockResolvedValue({ execution_id: 'exec-1', action: 'pause', task_id: 't-1' });

    render(<RunMode />);

    await userEvent.click(await screen.findByText('⏸ 일시정지'));
    expect(mockPause).toHaveBeenCalledWith('exec-1');
  });

  it('일시정지 상태면 재개 버튼이 resumeExecution을 호출하고, 일시정지 버튼은 숨긴다', async () => {
    mockGetLatest.mockResolvedValue(
      latest(ExecutionStatus.PAUSED, [
        { node_instance_id: 'n-a', status: 'succeeded' },
      ]),
    );
    mockResume.mockResolvedValue({ execution_id: 'exec-1', action: 'resume', task_id: 't-1' });

    render(<RunMode />);

    expect(await screen.findByText('▶ 재개')).toBeInTheDocument();
    expect(screen.queryByText('⏸ 일시정지')).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('▶ 재개'));
    expect(mockResume).toHaveBeenCalledWith('exec-1');
  });

  it('skipped 노드(L2 분기 미선택)는 완료 카운트에서 제외하고 건너뜀 로그를 남긴다', async () => {
    mockGetLatest.mockResolvedValue(
      latest(ExecutionStatus.COMPLETED, [
        { node_instance_id: 'n-a', status: 'succeeded' },
        { node_instance_id: 'n-b', status: 'skipped' },
      ]),
    );

    render(<RunMode />);

    // succeeded 1건만 완료로 카운트(skipped 제외)
    expect(await screen.findByText('1 / 2 노드 완료')).toBeInTheDocument();
    expect(await screen.findByText(/건너뜀/)).toBeInTheDocument();
  });

  it('완료된 실행이면 다시 실행 버튼이 executeWorkflow를 호출한다', async () => {
    mockGetLatest.mockResolvedValue(
      latest(ExecutionStatus.COMPLETED, [
        { node_instance_id: 'n-a', status: 'succeeded' },
        { node_instance_id: 'n-b', status: 'succeeded' },
      ]),
    );
    mockExecute.mockResolvedValue({ execution_id: 'exec-2', status: 'queued', task_id: 't-2' });

    render(<RunMode />);

    expect(await screen.findByText('완료')).toBeInTheDocument();
    await userEvent.click(screen.getByText('↻ 다시 실행'));
    expect(mockExecute).toHaveBeenCalledWith('wf-1');
  });

  it('실행 이력이 없으면(idle) 실행 버튼을 노출한다', async () => {
    mockGetLatest.mockResolvedValue(null);
    mockExecute.mockResolvedValue({ execution_id: 'exec-3', status: 'queued', task_id: 't-3' });

    render(<RunMode />);

    expect(await screen.findByText('▶ 실행')).toBeInTheDocument();
    await userEvent.click(screen.getByText('▶ 실행'));
    expect(mockExecute).toHaveBeenCalledWith('wf-1');
  });

  it('카드 순서를 nodes 배열이 아닌 connections 기반 실행 순서로 렌더한다', async () => {
    // nodes 배열은 [Slack(n-b), Google Sheets(n-a)] 순이지만 엣지는 n-a → n-b.
    // 화면 순서는 위상 정렬을 따라 Google Sheets가 Slack보다 먼저 와야 한다.
    const wf = makeWorkflow();
    wf.nodes = [wf.nodes[1], wf.nodes[0]]; // 배열 순서를 일부러 뒤집음
    wf.connections = [
      {
        from_instance_id: 'n-a',
        to_instance_id: 'n-b',
        from_handle: 'output',
        to_handle: 'input',
        condition: null,
      } as WorkflowSchema['connections'][number],
    ];
    useWorkflowStore.setState({ workflow: wf, activeExecutionId: null });
    mockGetLatest.mockResolvedValue(null);

    render(<RunMode />);

    const sheets = await screen.findByText('Google Sheets');
    const slack = screen.getByText('Slack 알림');
    // Google Sheets 카드가 DOM 상 Slack 카드보다 앞에 위치(엣지 순서 반영)
    expect(sheets.compareDocumentPosition(slack) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
