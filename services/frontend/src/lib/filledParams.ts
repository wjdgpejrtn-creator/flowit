import type { NodeConfig, WorkflowSchema } from '@common/generated';

// 컨펌 게이트 "실행 전 확인할 입력값" — 워크플로우 노드 파라미터 × 카탈로그 input_schema로
// AI가 자동으로 채운(또는 채웠을) 입력값을 계산한다. provenance(사용자 입력 vs 자동) 정확
// 추적은 백엔드에 없으므로(프론트 휴리스틱), **과다노출=안전** 쪽으로 표시한다:
//   - 값 == input_schema default        → 'default' (기본값 자동 적용)
//   - placeholder/template 패턴         → 'review'  (AI 추정값 확률↑ — 확인 필요)
//   - 그 외 required 필드의 실제 값       → 'normal'  (사용자값일 수 있으나 확인용 표시)
// 비-required + 비-default + 실제값은 생략(노이즈 방지).
// loadedWorkflow·editCatalog는 confirm 시점 page.tsx가 이미 보유 → 백엔드/SSOT 변경 0.

export type FillTag = 'default' | 'review' | 'normal';

export interface FilledField {
  name: string;
  value: string;
  tag: FillTag;
  /** 카탈로그 input_schema의 필드 설명 — 사용자가 값의 의미를 알도록 (없으면 생략) */
  description?: string;
}

export interface FilledNode {
  nodeName: string;
  fields: FilledField[];
}

interface SchemaProp {
  default?: unknown;
  description?: string;
}

function parseSchema(input: unknown): { required: Set<string>; props: Record<string, SchemaProp> } {
  if (!input || typeof input !== 'object') return { required: new Set(), props: {} };
  const s = input as { properties?: Record<string, unknown>; required?: string[] };
  return {
    required: new Set(s.required ?? []),
    props: (s.properties ?? {}) as Record<string, SchemaProp>,
  };
}

// AI가 미지정 필드를 채울 때 흔히 넣는 자리표시자/템플릿 패턴. 매치되면 '확인 필요'.
const PLACEHOLDER_RE =
  /(\{\{.*\}\})|(^<.*>$)|(example\.(com|org|net))|(\byour[-_ ])|(change[-_ ]?me)|(placeholder)|(\bTODO\b)/i;

function isPlaceholder(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === 'string') return v.trim() === '' || PLACEHOLDER_RE.test(v);
  return false;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

function displayValue(v: unknown): string {
  if (v === null || v === undefined) return '(비어 있음)';
  if (typeof v === 'string') return v.trim() === '' ? '(비어 있음)' : v;
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

export function computeFilledParams(
  workflow: WorkflowSchema | null,
  catalog: NodeConfig[] | null,
): FilledNode[] {
  if (!workflow || !catalog) return [];
  const byNodeId = new Map(catalog.map((c) => [c.node_id, c]));
  const out: FilledNode[] = [];
  for (const node of workflow.nodes) {
    const cfg = byNodeId.get(node.node_id);
    if (!cfg) continue;
    const { required, props } = parseSchema(cfg.input_schema);
    const params = (node.parameters ?? {}) as Record<string, unknown>;
    const fields: FilledField[] = [];
    for (const key of Object.keys(props)) {
      const isReq = required.has(key);
      const prop = props[key] ?? {};
      const hasDefault = Object.prototype.hasOwnProperty.call(prop, 'default');
      const has = Object.prototype.hasOwnProperty.call(params, key);
      const v = params[key];
      let tag: FillTag | null = null;
      if (hasDefault && has && deepEqual(v, prop.default)) tag = 'default';
      else if ((isReq || has) && isPlaceholder(v)) tag = 'review';
      else if (isReq && has) tag = 'normal';
      if (tag === null) continue;
      const desc = typeof prop.description === 'string' && prop.description.trim() !== '' ? prop.description : undefined;
      fields.push({ name: key, value: displayValue(v), tag, description: desc });
    }
    if (fields.length > 0) out.push({ nodeName: cfg.name, fields });
  }
  return out;
}

export function reviewCount(nodes: FilledNode[]): number {
  return nodes.reduce((n, node) => n + node.fields.filter((f) => f.tag === 'review').length, 0);
}
