import { useState } from 'react';
import RiskLevelBadge from './RiskLevelBadge';
import type { NodeConfig } from '@common/generated';

interface Props {
  nodes: NodeConfig[];
  onDragStart?: (node: NodeConfig) => void;
}

const CATEGORY_ICONS: Record<string, string> = {
  external: '🌐',
  domain: '⚙',
  toolset: '🔧',
};

export default function NodePalette({ nodes, onDragStart }: Props) {
  const [search, setSearch] = useState('');

  const filtered = search.trim()
    ? nodes.filter(
        (n) =>
          n.name.toLowerCase().includes(search.toLowerCase()) ||
          n.category.toLowerCase().includes(search.toLowerCase()) ||
          n.description.toLowerCase().includes(search.toLowerCase()),
      )
    : nodes;

  const grouped = filtered.reduce<Record<string, NodeConfig[]>>((acc, n) => {
    if (!acc[n.category]) acc[n.category] = [];
    acc[n.category].push(n);
    return acc;
  }, {});

  const handleDragStart = (e: React.DragEvent, node: NodeConfig) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('application/x-node-config', JSON.stringify(node));
    onDragStart?.(node);
  };

  return (
    <div className="flex flex-col h-full">
      {/* 검색 */}
      <div className="p-2 border-b border-[var(--color-line-soft)]">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="노드 검색…"
          className="w-full border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-2 py-[4px] text-[12px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)]"
        />
      </div>

      {/* 카테고리별 목록 */}
      <div className="flex-1 overflow-auto">
        {Object.entries(grouped).map(([category, catNodes]) => (
          <div key={category}>
            <div className="px-2 py-1 text-[10px] font-bold text-[var(--color-ink3)] uppercase tracking-wider bg-[var(--color-paper2)] border-b border-[var(--color-line-soft)] sticky top-0">
              {CATEGORY_ICONS[category] ?? '📦'} {category} ({catNodes.length})
            </div>
            {catNodes.map((node) => (
              <div
                key={node.node_id}
                draggable
                onDragStart={(e) => handleDragStart(e, node)}
                className="flex items-center gap-2 px-2 py-[6px] border-b border-[var(--color-line-soft)] cursor-grab hover:bg-[var(--color-hl)] active:cursor-grabbing"
              >
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-[12px] truncate">{node.name}</div>
                  <div className="text-[10px] text-[var(--color-ink3)] truncate">{node.description}</div>
                </div>
                <RiskLevelBadge level={node.risk_level} showLabel={false} />
              </div>
            ))}
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="p-4 text-center text-[12px] text-[var(--color-ink4)] italic">
            검색 결과가 없습니다.
          </div>
        )}
      </div>
    </div>
  );
}
