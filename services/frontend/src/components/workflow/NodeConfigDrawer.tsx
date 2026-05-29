'use client';

import { useEffect, useMemo, useState } from 'react';
import { getCatalog } from '@/lib/api/nodeApi';
import { useWorkflowStore } from '@/stores/workflowStore';
import type { NodeConfig } from '@common/generated';
import RiskPill from '@/components/common/RiskPill';

interface SchemaField {
  name: string;
  type: string;
  required: boolean;
  enumOptions?: unknown[];
  description?: string;
  format?: string;
  default?: unknown;
}

function parseSchema(input: unknown): SchemaField[] {
  if (!input || typeof input !== 'object') return [];
  const schema = input as {
    properties?: Record<string, unknown>;
    required?: string[];
  };
  const props = schema.properties;
  if (!props || typeof props !== 'object') return [];
  const required = new Set(schema.required ?? []);
  return Object.entries(props).map(([name, raw]) => {
    const def = (raw ?? {}) as {
      type?: string;
      enum?: unknown[];
      description?: string;
      format?: string;
      default?: unknown;
    };
    return {
      name,
      type: def.type ?? 'string',
      required: required.has(name),
      enumOptions: def.enum,
      description: def.description,
      format: def.format,
      default: def.default,
    };
  });
}

function coerce(value: string, type: string): unknown {
  if (type === 'number' || type === 'integer') {
    if (value === '') return undefined;
    const n = Number(value);
    return Number.isFinite(n) ? n : value;
  }
  if (type === 'boolean') return value === 'true';
  if (type === 'object' || type === 'array') {
    if (value.trim() === '') return type === 'array' ? [] : {};
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

function stringify(value: unknown, type: string): string {
  if (value === undefined || value === null) return '';
  if (type === 'object' || type === 'array') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export default function NodeConfigDrawer({
  catalog: providedCatalog,
}: {
  catalog?: NodeConfig[] | null;
} = {}) {
  const selectedNodeId = useWorkflowStore((s) => s.selectedNodeId);
  const workflow = useWorkflowStore((s) => s.workflow);
  const updateNodeParams = useWorkflowStore((s) => s.updateNodeParams);
  const setSelectedNodeId = useWorkflowStore((s) => s.setSelectedNodeId);

  const [fetched, setFetched] = useState<NodeConfig[] | null>(null);

  useEffect(() => {
    if (providedCatalog !== undefined) return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await getCatalog();
        if (!cancelled) setFetched(data);
      } catch {
        if (!cancelled) setFetched([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [providedCatalog]);

  const catalog = providedCatalog ?? fetched;

  const node = useMemo(
    () => workflow?.nodes.find((n) => n.instance_id === selectedNodeId) ?? null,
    [workflow, selectedNodeId],
  );

  const nodeConfig = useMemo<NodeConfig | null>(() => {
    if (!node || !catalog) return null;
    return catalog.find((c) => c.node_id === node.node_id) ?? null;
  }, [node, catalog]);

  const fields = useMemo(() => {
    if (!nodeConfig) return [];
    return parseSchema(nodeConfig.input_schema);
  }, [nodeConfig]);

  const params = (node?.parameters ?? {}) as Record<string, unknown>;

  if (!selectedNodeId) {
    return (
      <div
        data-testid="node-config-drawer"
        className="border-l-[1.5px] border-[var(--color-ink)] p-3 flex-shrink-0 overflow-auto"
        style={{ width: 320, background: 'var(--color-surface)' }}
      >
        <div className="text-[12px] text-[var(--color-ink4)] italic">
          노드를 선택하면 파라미터를 편집할 수 있습니다.
        </div>
      </div>
    );
  }

  if (!node) {
    return (
      <div
        data-testid="node-config-drawer"
        className="border-l-[1.5px] border-[var(--color-ink)] p-3 flex-shrink-0 overflow-auto"
        style={{ width: 320, background: 'var(--color-surface)' }}
      >
        <div className="text-[12px] text-[var(--color-status-failed)]">
          선택된 노드를 찾을 수 없습니다.
        </div>
      </div>
    );
  }

  const updateField = (name: string, raw: string, type: string) => {
    const next = { ...params };
    const value = coerce(raw, type);
    if (value === undefined) {
      delete next[name];
    } else {
      next[name] = value;
    }
    // preserve internal __palette metadata
    if (params.__palette) next.__palette = params.__palette;
    updateNodeParams(node.instance_id, next);
  };

  const missingRequired = fields
    .filter((f) => f.required)
    .filter((f) => {
      const v = params[f.name];
      return v === undefined || v === null || v === '';
    });

  return (
    <div
      data-testid="node-config-drawer"
      className="border-l-[1.5px] border-[var(--color-ink)] flex-shrink-0 overflow-auto flex flex-col"
      style={{ width: 320, background: 'var(--color-surface)' }}
    >
      <div className="p-3 border-b-[1.5px] border-[var(--color-line-soft)]">
        <div className="flex items-center justify-between gap-2">
          <div className="font-bold text-[13px] truncate">{nodeConfig?.name ?? '노드 설정'}</div>
          <button
            type="button"
            onClick={() => setSelectedNodeId(null)}
            className="text-[18px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] leading-none"
            aria-label="닫기"
          >
            ×
          </button>
        </div>
        {nodeConfig && (
          <div className="mt-1 flex items-center gap-2">
            <RiskPill level={nodeConfig.risk_level} />
            <span className="font-mono text-[10px] text-[var(--color-ink3)] truncate">
              {nodeConfig.node_type}
            </span>
          </div>
        )}
        {nodeConfig?.description && (
          <div className="text-[11px] text-[var(--color-ink3)] mt-2">{nodeConfig.description}</div>
        )}
      </div>

      <div className="p-3 flex-1 flex flex-col gap-3">
        {!catalog && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">카탈로그 로딩 중…</div>
        )}
        {catalog && !nodeConfig && (
          <div className="text-[12px] text-[var(--color-status-failed)]">
            ⚠ 노드 정의를 카탈로그에서 찾을 수 없습니다. (node_id: {node.node_id})
          </div>
        )}
        {nodeConfig && fields.length === 0 && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">
            설정 가능한 파라미터가 없습니다.
          </div>
        )}
        {fields.map((f) => {
          const value = stringify(params[f.name] ?? f.default, f.type);
          const isRequiredMissing = f.required && (params[f.name] === undefined || params[f.name] === '');
          return (
            <label key={f.name} className="flex flex-col gap-1">
              <span className="text-[12px] font-bold flex items-center gap-1">
                {f.name}
                {f.required && <span className="text-[var(--color-status-failed)]">*</span>}
                <span className="font-mono text-[10px] text-[var(--color-ink4)] font-normal">
                  : {f.type}
                  {f.format ? `/${f.format}` : ''}
                </span>
              </span>
              {f.description && (
                <span className="text-[11px] text-[var(--color-ink3)]">{f.description}</span>
              )}
              {f.enumOptions ? (
                <select
                  value={value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                >
                  <option value="">(선택)</option>
                  {f.enumOptions.map((opt) => (
                    <option key={String(opt)} value={String(opt)}>
                      {String(opt)}
                    </option>
                  ))}
                </select>
              ) : f.type === 'boolean' ? (
                <select
                  value={value === '' ? '' : value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                >
                  <option value="">(미지정)</option>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : f.type === 'object' || f.type === 'array' ? (
                <textarea
                  value={value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[11px] font-mono px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                  rows={4}
                  spellCheck={false}
                  placeholder={f.type === 'array' ? '[]' : '{}'}
                />
              ) : (
                <input
                  type={f.type === 'number' || f.type === 'integer' ? 'number' : 'text'}
                  value={value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                  placeholder={f.default !== undefined ? `기본 ${stringify(f.default, f.type)}` : ''}
                />
              )}
              {isRequiredMissing && (
                <span className="text-[11px] text-[var(--color-status-failed)]">필수 항목입니다.</span>
              )}
            </label>
          );
        })}
        {missingRequired.length > 0 && (
          <div
            className="text-[11px] text-[var(--color-status-failed)] border-[1.5px] border-[var(--color-status-failed)] rounded p-2 mt-2"
            role="alert"
          >
            ⚠ 필수 입력 누락: {missingRequired.map((f) => f.name).join(', ')}
          </div>
        )}
      </div>
    </div>
  );
}
