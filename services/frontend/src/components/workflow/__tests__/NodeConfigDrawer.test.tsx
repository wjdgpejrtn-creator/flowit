import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RiskLevel } from '@common/generated';
import type { NodeConfig, WorkflowSchema } from '@common/generated';
import { useWorkflowStore } from '@/stores/workflowStore';

const mockGetCatalog = jest.fn();
jest.mock('../../../lib/api/nodeApi', () => ({
  getCatalog: (...args: unknown[]) => mockGetCatalog(...args),
}));

import NodeConfigDrawer from '../NodeConfigDrawer';

const HTTP_NODE: NodeConfig = {
  node_id: 'id-http',
  node_type: 'http_request',
  name: 'HTTP 요청',
  category: 'integration',
  version: '1.0.0',
  input_schema: {
    type: 'object',
    properties: {
      url: { type: 'string', format: 'uri' },
      method: { type: 'string', enum: ['GET', 'POST'], default: 'GET' },
      timeout: { type: 'number', default: 30 },
      verify_ssl: { type: 'boolean', default: true },
    },
    required: ['url'],
  },
  output_schema: {},
  parameter_schema: {},
  risk_level: RiskLevel.HIGH,
  required_connections: [],
  description: 'HTTP call',
  is_mvp: true,
};

const WORKFLOW: WorkflowSchema = {
  workflow_id: 'wf-1',
  owner_user_id: null,
  name: 'Test',
  description: null,
  scope: 'private',
  is_draft: true,
  draft_spec: null,
  nodes: [
    {
      instance_id: 'inst-1',
      node_id: 'id-http',
      parameters: {},
      credential_id: null,
      credential_ids: {},
      position: { x: 0, y: 0 },
    },
  ],
  connections: [],
  version: 1,
  sha256: null,
  created_via_session_id: null,
};

beforeEach(() => {
  mockGetCatalog.mockReset();
  useWorkflowStore.setState({
    workflow: null,
    selectedNodeId: null,
    dirty: false,
    validationErrors: [],
  });
});

describe('NodeConfigDrawer', () => {
  it('shows placeholder when no node selected', () => {
    render(<NodeConfigDrawer catalog={[HTTP_NODE]} />);
    expect(screen.getByText(/노드를 선택하면/)).toBeInTheDocument();
  });

  it('renders input_schema fields with required marker for selected node', async () => {
    act(() => {
      useWorkflowStore.getState().setWorkflow(WORKFLOW);
      useWorkflowStore.getState().setSelectedNodeId('inst-1');
    });
    const { container } = render(<NodeConfigDrawer catalog={[HTTP_NODE]} />);
    await waitFor(() => screen.getByText('HTTP 요청'));
    const labels = container.querySelectorAll('label');
    const labelNames = Array.from(labels).map((l) => l.textContent ?? '');
    expect(labelNames.some((t) => t.startsWith('url'))).toBe(true);
    expect(labelNames.some((t) => t.startsWith('method'))).toBe(true);
    expect(labelNames.some((t) => t.startsWith('timeout'))).toBe(true);
    expect(labelNames.some((t) => t.startsWith('verify_ssl'))).toBe(true);
    expect(screen.getByText(/필수 입력 누락: url/)).toBeInTheDocument();
  });

  function getInputByLabel(container: HTMLElement, name: string): HTMLInputElement | HTMLSelectElement {
    const labels = Array.from(container.querySelectorAll('label'));
    const target = labels.find((l) => (l.textContent ?? '').trimStart().startsWith(name));
    if (!target) throw new Error(`label not found: ${name}`);
    const ctrl = target.querySelector('input, select');
    if (!ctrl) throw new Error(`control not found for: ${name}`);
    return ctrl as HTMLInputElement | HTMLSelectElement;
  }

  it('updates store.workflow.nodes[0].parameters on user input', async () => {
    act(() => {
      useWorkflowStore.getState().setWorkflow(WORKFLOW);
      useWorkflowStore.getState().setSelectedNodeId('inst-1');
    });
    const { container } = render(<NodeConfigDrawer catalog={[HTTP_NODE]} />);
    await screen.findByText('HTTP 요청');
    const urlInput = getInputByLabel(container, 'url') as HTMLInputElement;
    fireEvent.change(urlInput, { target: { value: 'https://example.com' } });

    const params = useWorkflowStore.getState().workflow!.nodes[0].parameters as Record<string, unknown>;
    expect(params.url).toBe('https://example.com');
    expect(useWorkflowStore.getState().dirty).toBe(true);
  });

  it('coerces number/boolean fields correctly', async () => {
    act(() => {
      useWorkflowStore.getState().setWorkflow(WORKFLOW);
      useWorkflowStore.getState().setSelectedNodeId('inst-1');
    });
    const { container } = render(<NodeConfigDrawer catalog={[HTTP_NODE]} />);
    await screen.findByText('HTTP 요청');

    const timeoutInput = getInputByLabel(container, 'timeout') as HTMLInputElement;
    fireEvent.change(timeoutInput, { target: { value: '45' } });

    const sslSelect = getInputByLabel(container, 'verify_ssl') as HTMLSelectElement;
    await userEvent.selectOptions(sslSelect, 'false');

    const params = useWorkflowStore.getState().workflow!.nodes[0].parameters as Record<string, unknown>;
    expect(params.timeout).toBe(45);
    expect(params.verify_ssl).toBe(false);
  });
});
