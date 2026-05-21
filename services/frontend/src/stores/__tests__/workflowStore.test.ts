import { useWorkflowStore } from '../workflowStore';
import { RiskLevel, ExecutionStatus } from '@common/generated';
import type { Workflow } from '../workflowStore';

const BASE: Workflow = {
  id: 'w-1',
  name: 'Test',
  scope: 'private',
  nodes: [
    { id: 'n-1', name: 'Node 1', icon: 'N', risk: RiskLevel.LOW, position: { x: 0, y: 0 } },
    { id: 'n-2', name: 'Node 2', icon: 'M', risk: RiskLevel.HIGH, position: { x: 100, y: 0 } },
  ],
  edges: [],
  riskLevel: RiskLevel.LOW,
  status: ExecutionStatus.PENDING,
  nodeCount: 2,
  updatedAt: '2026-05-21T00:00:00Z',
};

beforeEach(() => {
  useWorkflowStore.setState({ current: null });
});

describe('setCurrent', () => {
  it('sets workflow', () => {
    useWorkflowStore.getState().setCurrent(BASE);
    expect(useWorkflowStore.getState().current).toEqual(BASE);
  });

  it('clears workflow when called with null', () => {
    useWorkflowStore.getState().setCurrent(BASE);
    useWorkflowStore.getState().setCurrent(null);
    expect(useWorkflowStore.getState().current).toBeNull();
  });
});

describe('updateNode', () => {
  it('updates matching node status', () => {
    useWorkflowStore.getState().setCurrent(BASE);
    useWorkflowStore.getState().updateNode('n-1', { status: 'running' });
    expect(useWorkflowStore.getState().current?.nodes[0].status).toBe('running');
  });

  it('does not affect other nodes', () => {
    useWorkflowStore.getState().setCurrent(BASE);
    useWorkflowStore.getState().updateNode('n-1', { status: 'succeeded' });
    expect(useWorkflowStore.getState().current?.nodes[1].status).toBeUndefined();
  });

  it('is a no-op when current is null', () => {
    expect(() => {
      useWorkflowStore.getState().updateNode('n-1', { status: 'running' });
    }).not.toThrow();
    expect(useWorkflowStore.getState().current).toBeNull();
  });
});
