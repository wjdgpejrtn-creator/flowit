import { useWorkflowStore } from '../workflowStore';
import type { WorkflowSchema, NodeInstance, Edge } from '@common/generated';

function makeNode(id: string, x = 0, y = 0): NodeInstance {
  return {
    instance_id: id,
    node_id: 'node-type-uuid',
    parameters: {},
    credential_id: null,
    position: { x, y },
  };
}

function makeEdge(from: string, to: string): Edge {
  return {
    from_instance_id: from,
    to_instance_id: to,
    from_handle: 'out',
    to_handle: 'in',
  };
}

const BASE: WorkflowSchema = {
  workflow_id: 'wf-1',
  owner_user_id: null,
  name: 'Test',
  description: null,
  scope: 'private',
  is_draft: true,
  draft_spec: null,
  nodes: [makeNode('n-1', 0, 0), makeNode('n-2', 100, 0)],
  connections: [makeEdge('n-1', 'n-2')],
  version: 1,
  sha256: null,
  created_via_session_id: null,
};

beforeEach(() => {
  useWorkflowStore.setState({
    workflow: null,
    selectedNodeId: null,
    dirty: false,
    validationErrors: [],
  });
});

describe('setWorkflow', () => {
  it('sets workflow and resets transient state', () => {
    useWorkflowStore.setState({ selectedNodeId: 'old', dirty: true });
    useWorkflowStore.getState().setWorkflow(BASE);
    const s = useWorkflowStore.getState();
    expect(s.workflow).toEqual(BASE);
    expect(s.selectedNodeId).toBeNull();
    expect(s.dirty).toBe(false);
    expect(s.validationErrors).toEqual([]);
  });
});

describe('addNode', () => {
  it('appends a node and marks dirty', () => {
    useWorkflowStore.getState().setWorkflow(BASE);
    useWorkflowStore.getState().addNode(makeNode('n-3'));
    const s = useWorkflowStore.getState();
    expect(s.workflow?.nodes).toHaveLength(3);
    expect(s.dirty).toBe(true);
  });

  it('is a no-op when workflow is null', () => {
    expect(() => useWorkflowStore.getState().addNode(makeNode('x'))).not.toThrow();
    expect(useWorkflowStore.getState().workflow).toBeNull();
  });
});

describe('updateNodeParams', () => {
  it('updates the target node parameters and marks dirty', () => {
    useWorkflowStore.getState().setWorkflow(BASE);
    useWorkflowStore.getState().updateNodeParams('n-1', { url: 'https://x' });
    const s = useWorkflowStore.getState();
    expect(s.workflow?.nodes[0].parameters).toEqual({ url: 'https://x' });
    expect(s.workflow?.nodes[1].parameters).toEqual({});
    expect(s.dirty).toBe(true);
  });
});

describe('updateNodePosition', () => {
  it('updates the position only', () => {
    useWorkflowStore.getState().setWorkflow(BASE);
    useWorkflowStore.getState().updateNodePosition('n-1', { x: 50, y: 75 });
    expect(useWorkflowStore.getState().workflow?.nodes[0].position).toEqual({ x: 50, y: 75 });
  });
});

describe('removeNode', () => {
  it('removes the node and any incident edges, and clears selection if matched', () => {
    useWorkflowStore.getState().setWorkflow(BASE);
    useWorkflowStore.getState().setSelectedNodeId('n-2');
    useWorkflowStore.getState().removeNode('n-2');
    const s = useWorkflowStore.getState();
    expect(s.workflow?.nodes).toHaveLength(1);
    expect(s.workflow?.connections).toHaveLength(0);
    expect(s.selectedNodeId).toBeNull();
  });
});

describe('addEdge', () => {
  it('appends an edge and marks dirty', () => {
    useWorkflowStore.getState().setWorkflow({ ...BASE, connections: [] });
    useWorkflowStore.getState().addEdge(makeEdge('n-1', 'n-2'));
    expect(useWorkflowStore.getState().workflow?.connections).toHaveLength(1);
    expect(useWorkflowStore.getState().dirty).toBe(true);
  });

  it('deduplicates identical edges', () => {
    useWorkflowStore.getState().setWorkflow(BASE);
    useWorkflowStore.getState().addEdge(makeEdge('n-1', 'n-2'));
    expect(useWorkflowStore.getState().workflow?.connections).toHaveLength(1);
  });
});

describe('removeEdge', () => {
  it('removes the matching edge and marks dirty', () => {
    useWorkflowStore.getState().setWorkflow(BASE);
    useWorkflowStore.getState().removeEdge('n-1', 'n-2');
    expect(useWorkflowStore.getState().workflow?.connections).toHaveLength(0);
    expect(useWorkflowStore.getState().dirty).toBe(true);
  });
});

describe('selection + validation + markClean', () => {
  it('manages selection / validation errors / clean flag', () => {
    useWorkflowStore.getState().setWorkflow(BASE);
    useWorkflowStore.getState().setSelectedNodeId('n-1');
    useWorkflowStore.getState().setValidationErrors([
      {
        code: 'E_SCHEMA_INVALID' as never,
        message: 'fail',
        node_ids: ['n-1'],
        edge_id: null,
        validator: 'SchemaValidation',
        hint: null,
      },
    ]);
    useWorkflowStore.setState({ dirty: true });
    useWorkflowStore.getState().markClean();
    const s = useWorkflowStore.getState();
    expect(s.selectedNodeId).toBe('n-1');
    expect(s.validationErrors).toHaveLength(1);
    expect(s.dirty).toBe(false);
  });
});
