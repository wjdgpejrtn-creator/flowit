'use client';

import { useEffect, useMemo, useState } from 'react';
import { getCatalog } from '@/lib/api/nodeApi';
import { RiskLevel } from '@common/generated';
import type { NodeConfig } from '@common/generated';
import RiskPill from '@/components/common/RiskPill';

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
}: {
  mvpOnly?: boolean;
  catalog?: NodeConfig[] | null;
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
      className="flex flex-col h-full border-r-[1.5px] border-[var(--color-ink)]"
      style={{ width: 240, background: 'var(--color-surface)' }}
    >
      <div className="p-2 border-b-[1.5px] border-[var(--color-line-soft)]">
        <div className="font-bold text-[13px] mb-1">노드 팔레트</div>
        <input
          type="search"
          placeholder="검색 (이름/타입/카테고리)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
        />
      </div>

      <div className="flex-1 overflow-auto p-2">
        {error && (
          <div className="text-[12px] text-[var(--color-status-failed)] mb-2">⚠ {error}</div>
        )}
        {!catalog && !error && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">로딩 중…</div>
        )}
        {catalog && grouped.size === 0 && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">결과 없음</div>
        )}
        {[...grouped.entries()].map(([category, nodes]) => (
          <div key={category} className="mb-3">
            <div className="text-[11px] uppercase tracking-wide text-[var(--color-ink3)] mb-1 font-bold">
              {category}
            </div>
            <div className="flex flex-col gap-1">
              {nodes.map((node) => (
                <div
                  key={node.node_id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, node)}
                  data-testid={`palette-item-${node.node_type}`}
                  className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_9px_5px_9px] px-2 py-[5px] bg-[var(--color-paper2)] cursor-grab active:cursor-grabbing hover:bg-[var(--color-hl)]"
                  title={node.description}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-bold text-[12px] truncate">{node.name}</span>
                    <RiskPill level={node.risk_level} />
                  </div>
                  <div className="font-mono text-[10px] text-[var(--color-ink3)] truncate">
                    {node.node_type}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export { PALETTE_MIME };
