import { RiskLevel } from '@common/generated';
import type { WorkflowSchema, NodeInstance, NodeConfig } from '@common/generated';
import {
  stripInternalParams,
  rehydratePaletteMetadata,
  computeMissingRequired,
} from '../WorkflowEditPane';

function makeNode(
  instance_id: string,
  parameters: Record<string, unknown> = {},
  node_id = 'node-type-uuid',
): NodeInstance {
  return {
    instance_id,
    node_id,
    parameters,
    credential_id: null,
    position: { x: 0, y: 0 },
  };
}

function makeWorkflow(nodes: NodeInstance[]): WorkflowSchema {
  return {
    workflow_id: 'wf-1',
    owner_user_id: null,
    name: 'Test',
    description: null,
    scope: 'private',
    is_draft: true,
    draft_spec: null,
    nodes,
    connections: [],
    version: 1,
    sha256: null,
    created_via_session_id: null,
  };
}

describe('stripInternalParams', () => {
  it('removes __palette while preserving other parameter keys', () => {
    const wf = makeWorkflow([
      makeNode('n-1', { url: 'https://x', __palette: { name: 'HTTP', risk_level: 'high' } }),
      makeNode('n-2', { method: 'GET', __palette: { name: 'foo' } }),
    ]);
    const stripped = stripInternalParams(wf);
    expect(stripped.nodes[0].parameters).toEqual({ url: 'https://x' });
    expect(stripped.nodes[1].parameters).toEqual({ method: 'GET' });
  });

  it('is a no-op when no __palette present', () => {
    const wf = makeWorkflow([makeNode('n-1', { url: 'x' })]);
    const stripped = stripInternalParams(wf);
    expect(stripped.nodes[0].parameters).toEqual({ url: 'x' });
  });

  it('handles empty parameters', () => {
    const wf = makeWorkflow([makeNode('n-1', {})]);
    const stripped = stripInternalParams(wf);
    expect(stripped.nodes[0].parameters).toEqual({});
  });

  it('does not mutate input workflow', () => {
    const wf = makeWorkflow([makeNode('n-1', { __palette: { name: 'X' } })]);
    stripInternalParams(wf);
    expect(wf.nodes[0].parameters).toEqual({ __palette: { name: 'X' } });
  });
});

describe('rehydratePaletteMetadata', () => {
  it('re-attaches __palette by instance_id (not by index)', () => {
    const previous = makeWorkflow([
      makeNode('n-1', { url: 'x', __palette: { name: 'HTTP', risk_level: 'high' } }),
      makeNode('n-2', { method: 'GET', __palette: { name: 'DataMap', risk_level: 'low' } }),
    ]);
    // 서버가 노드 순서를 재정렬해서 반환
    const saved = makeWorkflow([
      makeNode('n-2', { method: 'GET' }),
      makeNode('n-1', { url: 'x' }),
    ]);
    const rehydrated = rehydratePaletteMetadata(saved, previous);
    // 순서는 saved 그대로, 메타는 instance_id에 매칭되어야 함
    expect(rehydrated.nodes[0].instance_id).toBe('n-2');
    expect((rehydrated.nodes[0].parameters as Record<string, unknown>).__palette).toEqual({
      name: 'DataMap',
      risk_level: 'low',
    });
    expect(rehydrated.nodes[1].instance_id).toBe('n-1');
    expect((rehydrated.nodes[1].parameters as Record<string, unknown>).__palette).toEqual({
      name: 'HTTP',
      risk_level: 'high',
    });
  });

  it('preserves saved node parameters alongside re-attached metadata', () => {
    const previous = makeWorkflow([
      makeNode('n-1', { url: 'old', __palette: { name: 'HTTP' } }),
    ]);
    const saved = makeWorkflow([
      makeNode('n-1', { url: 'new', extra: 'added-by-server' }),
    ]);
    const rehydrated = rehydratePaletteMetadata(saved, previous);
    expect(rehydrated.nodes[0].parameters).toEqual({
      url: 'new',
      extra: 'added-by-server',
      __palette: { name: 'HTTP' },
    });
  });

  it('skips nodes that have no previous metadata', () => {
    const previous = makeWorkflow([
      makeNode('n-1', { __palette: { name: 'HTTP' } }),
    ]);
    const saved = makeWorkflow([
      makeNode('n-1', { url: 'x' }),
      makeNode('n-2', { method: 'GET' }), // 서버가 새로 만든 노드 (실제로는 거의 없음)
    ]);
    const rehydrated = rehydratePaletteMetadata(saved, previous);
    expect((rehydrated.nodes[0].parameters as Record<string, unknown>).__palette).toEqual({
      name: 'HTTP',
    });
    expect((rehydrated.nodes[1].parameters as Record<string, unknown>).__palette).toBeUndefined();
  });

  it('handles previous workflow with no palette metadata at all', () => {
    const previous = makeWorkflow([makeNode('n-1', { url: 'x' })]);
    const saved = makeWorkflow([makeNode('n-1', { url: 'x' })]);
    const rehydrated = rehydratePaletteMetadata(saved, previous);
    expect(rehydrated.nodes[0].parameters).toEqual({ url: 'x' });
  });
});

describe('computeMissingRequired', () => {
  const GEMMA: NodeConfig = {
    node_id: 'id-gemma',
    node_type: 'gemma_chat',
    name: 'Gemma Chat',
    category: 'ai',
    version: '1.0.0',
    input_schema: {
      type: 'object',
      properties: {
        prompt: { type: 'string' },
        max_tokens: { type: 'integer', default: 1024 },
      },
      required: ['prompt'],
    },
    output_schema: {},
    parameter_schema: {},
    risk_level: RiskLevel.LOW,
    required_connections: [],
    description: 'gemma',
    is_mvp: true,
  };
  const HTTP: NodeConfig = {
    ...GEMMA,
    node_id: 'id-http',
    node_type: 'http_request',
    name: 'HTTP',
    input_schema: {
      type: 'object',
      properties: { url: { type: 'string' }, method: { type: 'string' } },
      required: ['url'],
    },
  };
  const NO_REQ: NodeConfig = {
    ...GEMMA,
    node_id: 'id-mapper',
    node_type: 'data_mapping',
    name: 'Map',
    input_schema: { type: 'object', properties: {} },
  };

  it('returns empty when workflow or catalog is null', () => {
    expect(computeMissingRequired(null, [GEMMA])).toEqual([]);
    expect(computeMissingRequired(makeWorkflow([]), null)).toEqual([]);
  });

  it('flags nodes whose required fields are empty', () => {
    const wf = makeWorkflow([
      makeNode('inst-gemma', {}, 'id-gemma'),
      makeNode('inst-http', { url: 'https://x' }, 'id-http'),
    ]);
    const missing = computeMissingRequired(wf, [GEMMA, HTTP]);
    expect(missing).toEqual([
      { instance_id: 'inst-gemma', node_name: 'Gemma Chat', fields: ['prompt'] },
    ]);
  });

  it('treats empty-string value as missing', () => {
    const wf = makeWorkflow([makeNode('inst-gemma', { prompt: '' }, 'id-gemma')]);
    const missing = computeMissingRequired(wf, [GEMMA]);
    expect(missing).toHaveLength(1);
    expect(missing[0].fields).toEqual(['prompt']);
  });

  it('does not flag nodes that have all required fields populated', () => {
    const wf = makeWorkflow([
      makeNode('inst-gemma', { prompt: 'hello' }, 'id-gemma'),
      makeNode('inst-http', { url: 'https://x' }, 'id-http'),
    ]);
    expect(computeMissingRequired(wf, [GEMMA, HTTP])).toEqual([]);
  });

  it('skips nodes whose input_schema has no required fields', () => {
    const wf = makeWorkflow([makeNode('inst-map', {}, 'id-mapper')]);
    expect(computeMissingRequired(wf, [NO_REQ])).toEqual([]);
  });

  it('skips nodes not present in catalog (unknown node_id)', () => {
    const wf = makeWorkflow([makeNode('inst-unk', {}, 'id-unknown')]);
    expect(computeMissingRequired(wf, [GEMMA, HTTP])).toEqual([]);
  });

  it('aggregates multiple missing fields per node', () => {
    const MULTI: NodeConfig = {
      ...GEMMA,
      node_id: 'id-multi',
      input_schema: {
        type: 'object',
        properties: { a: { type: 'string' }, b: { type: 'string' }, c: { type: 'string' } },
        required: ['a', 'b'],
      },
    };
    const wf = makeWorkflow([makeNode('inst-multi', { c: 'ok' }, 'id-multi')]);
    const missing = computeMissingRequired(wf, [MULTI]);
    expect(missing).toEqual([
      { instance_id: 'inst-multi', node_name: 'Gemma Chat', fields: ['a', 'b'] },
    ]);
  });
});
