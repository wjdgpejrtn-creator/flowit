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
  type WorkflowLatestExecution,
} from '../../../lib/api/workflowApi';
import { getCatalog } from '../../../lib/api/nodeApi';

jest.mock('../../../lib/api/workflowApi');
jest.mock('../../../lib/api/nodeApi');

const mockGetLatest = getLatestExecution as jest.MockedFunction<typeof getLatestExecution>;
const mockExecute = executeWorkflow as jest.MockedFunction<typeof executeWorkflow>;
const mockCancel = cancelExecution as jest.MockedFunction<typeof cancelExecution>;
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
});
