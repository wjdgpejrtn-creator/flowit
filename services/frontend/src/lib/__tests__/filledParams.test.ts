import { computeFilledParams, reviewCount } from '../filledParams';
import type { NodeConfig, WorkflowSchema } from '@common/generated';

// 합성 카탈로그/워크플로우 — 타입 전부 채우지 않고 필요한 필드만(캐스팅).
function cfg(node_id: string, name: string, input_schema: object): NodeConfig {
  return { node_id, name, input_schema } as unknown as NodeConfig;
}
function wf(nodes: { node_id: string; parameters: Record<string, unknown> }[]): WorkflowSchema {
  return {
    nodes: nodes.map((n, i) => ({
      instance_id: `inst-${i}`,
      node_id: n.node_id,
      parameters: n.parameters,
      position: { x: 0, y: 0 },
    })),
    connections: [],
  } as unknown as WorkflowSchema;
}

const HTTP = cfg('http', 'HTTP 요청', {
  type: 'object',
  properties: {
    url: { type: 'string' },
    method: { type: 'string', default: 'GET' },
    timeout: { type: 'number', default: 30 },
    headers: { type: 'object' },
  },
  required: ['url'],
});

const SLACK = cfg('slack', 'Slack 메시지 전송', {
  type: 'object',
  properties: {
    channel: { type: 'string' },
    text: { type: 'string' },
  },
  required: ['channel', 'text'],
});

describe('computeFilledParams', () => {
  it('null 입력이면 빈 배열', () => {
    expect(computeFilledParams(null, [HTTP])).toEqual([]);
    expect(computeFilledParams(wf([]), null)).toEqual([]);
  });

  it('required + placeholder 값 → review, default 일치 → default', () => {
    const out = computeFilledParams(
      wf([{ node_id: 'http', parameters: { url: 'https://example.com', method: 'GET', timeout: 30 } }]),
      [HTTP],
    );
    expect(out).toHaveLength(1);
    const fields = Object.fromEntries(out[0].fields.map((f) => [f.name, f.tag]));
    expect(fields.url).toBe('review'); // example.com 자리표시자
    expect(fields.method).toBe('default'); // GET == schema default
    expect(fields.timeout).toBe('default'); // 30 == schema default
    expect(out[0].fields.find((f) => f.name === 'url')?.value).toBe('https://example.com');
  });

  it('required 실제값 → normal, 템플릿 {{}} → review', () => {
    const out = computeFilledParams(
      wf([{ node_id: 'slack', parameters: { channel: '#general', text: '{{payload}}' } }]),
      [SLACK],
    );
    const fields = Object.fromEntries(out[0].fields.map((f) => [f.name, f.tag]));
    expect(fields.channel).toBe('normal'); // 실제 채널명
    expect(fields.text).toBe('review'); // {{payload}} 템플릿
  });

  it('빈 문자열/누락 required → review', () => {
    const out = computeFilledParams(
      wf([{ node_id: 'slack', parameters: { channel: '', /* text 누락 */ } }]),
      [SLACK],
    );
    const fields = Object.fromEntries(out[0].fields.map((f) => [f.name, f.tag]));
    expect(fields.channel).toBe('review'); // 빈 문자열
    expect(fields.text).toBe('review'); // 누락(undefined)
  });

  it('비-required + 비-default + 실제값은 생략(노이즈 방지)', () => {
    const out = computeFilledParams(
      wf([{ node_id: 'http', parameters: { url: 'https://api.myapp.io/hook', headers: { 'X-Key': 'abc' } } }]),
      [HTTP],
    );
    const names = out[0].fields.map((f) => f.name);
    expect(names).toContain('url'); // required(실제값) → normal
    expect(names).not.toContain('headers'); // 비-required·비-default → 생략
  });

  it('카탈로그에 없는 노드는 건너뛴다', () => {
    expect(computeFilledParams(wf([{ node_id: 'unknown', parameters: { x: 1 } }]), [HTTP])).toEqual([]);
  });

  it('reviewCount는 review 태그 필드 수 합', () => {
    const out = computeFilledParams(
      wf([
        { node_id: 'http', parameters: { url: 'https://example.com', method: 'GET' } },
        { node_id: 'slack', parameters: { channel: '#general', text: '{{payload}}' } },
      ]),
      [HTTP, SLACK],
    );
    expect(reviewCount(out)).toBe(2); // http.url + slack.text
  });
});
