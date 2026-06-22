'use client';

import { useEffect, useMemo, useState } from 'react';
import { getCatalog } from '@/lib/api/nodeApi';
import { RiskLevel } from '@common/generated';
import type { NodeConfig } from '@common/generated';
import Icon from '@/components/common/Icon';
import { resolveNodeIcon } from '@/lib/nodeIcon';

const PALETTE_MIME = 'application/x-wf-node-config';

export interface NodePaletteDragPayload {
  node_id: string;
  node_type: string;
  name: string;
  risk_level: RiskLevel;
}

export function readPaletteDragPayload(e: React.DragEvent | DragEvent): NodePaletteDragPayload | null {
  const raw = e.dataTransfer?.getData(PALETTE_MIME);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as NodePaletteDragPayload;
  } catch {
    return null;
  }
}

export default function NodePalette({
  mvpOnly = false,
  catalog: providedCatalog,
  onPick,
}: {
  mvpOnly?: boolean;
  catalog?: NodeConfig[] | null;
  /** 항목 클릭 시 호출 — 드래그&드롭 외에 클릭으로도 노드 추가(시안 addCustomNode) */
  onPick?: (node: NodeConfig) => void;
}) {
  const [fetched, setFetched] = useState<NodeConfig[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (providedCatalog !== undefined) return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await getCatalog(mvpOnly);
        if (!cancelled) setFetched(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '카탈로그 조회 실패');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mvpOnly, providedCatalog]);

  const catalog = providedCatalog ?? fetched;

  const grouped = useMemo(() => {
    if (!catalog) return new Map<string, NodeConfig[]>();
    const filtered = query
      ? catalog.filter(
          (n) =>
            n.name.toLowerCase().includes(query.toLowerCase()) ||
            n.node_type.toLowerCase().includes(query.toLowerCase()) ||
            n.category.toLowerCase().includes(query.toLowerCase()),
        )
      : catalog;
    const map = new Map<string, NodeConfig[]>();
    for (const n of filtered) {
      const key = n.category || 'other';
      const list = map.get(key) ?? [];
      list.push(n);
      map.set(key, list);
    }
    return new Map([...map.entries()].sort(([a], [b]) => a.localeCompare(b)));
  }, [catalog, query]);

  const handleDragStart = (e: React.DragEvent, node: NodeConfig) => {
    const payload: NodePaletteDragPayload = {
      node_id: node.node_id,
      node_type: node.node_type,
      name: node.name,
      risk_level: node.risk_level,
    };
    e.dataTransfer.setData(PALETTE_MIME, JSON.stringify(payload));
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <div
      data-testid="node-palette"
      className="flex flex-col h-full border-r border-[var(--color-line-soft)]"
      style={{ width: 320, background: 'var(--color-paper2)' }}
    >
      <div className="p-4 border-b border-[var(--color-line-soft)]">
        <h4 className="text-xs font-bold text-[var(--color-ink)] mb-2 uppercase tracking-wider">
          노드 팔레트
        </h4>
        <div className="relative">
          <input
            type="search"
            placeholder="노드 검색 (이름/타입/카테고리)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-[var(--color-line-soft)] focus:outline-none focus:border-[var(--color-accent-coral)] bg-white text-[var(--color-ink)] font-bold"
          />
          <Icon
            name="search"
            className="w-3.5 h-3.5 text-[var(--color-ink3)] absolute left-2.5 top-2.5 pointer-events-none"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-3">
        {error && (
          <div className="text-[12px] text-[var(--color-status-failed)]">⚠ {error}</div>
        )}
        {!catalog && !error && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">로딩 중…</div>
        )}
        {catalog && grouped.size === 0 && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">결과 없음</div>
        )}
        {[...grouped.entries()].map(([category, nodes]) => (
          <div key={category} className="space-y-2">
            <div className="text-[10px] uppercase tracking-wide text-[var(--color-ink3)] font-bold">
              {category}
            </div>
            <div className="flex flex-col gap-2">
              {nodes.map((node) => {
                const { icon, color } = resolveNodeIcon(node.node_type, node.category);
                return (
                  <div
                    key={node.node_id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, node)}
                    onClick={() => onPick?.(node)}
                    data-testid={`palette-item-${node.node_type}`}
                    className="p-3 rounded-xl border border-[var(--color-line-soft)] hover:border-[var(--color-accent-coral)] hover:bg-[var(--color-hl)] cursor-grab active:cursor-grabbing transition-all shadow-sm bg-white"
                    title={node.description}
                  >
                    <div className="flex items-center space-x-2 min-w-0">
                      <Icon name={icon} className="w-4 h-4 flex-shrink-0" style={{ color }} />
                      <span title={node.name} className="text-xs font-bold text-[var(--color-ink)] truncate">
                        {node.name}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export { PALETTE_MIME };
