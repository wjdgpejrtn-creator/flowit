import type { UnresolvedNode } from '@common/generated';

interface Props {
  nodes: UnresolvedNode[];
}

export default function UnresolvedNodeList({ nodes }: Props) {
  if (nodes.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider">
        미확정 노드 {nodes.length}개
      </div>
      {nodes.map((node) => (
        <div
          key={node.placeholder_id}
          className="border-[1.5px] border-[var(--color-risk-med)] rounded-[4px_8px_4px_8px] p-[8px] bg-orange-50"
        >
          <div className="text-[12px] font-bold text-[var(--color-ink)] mb-1">{node.hint}</div>
          {node.candidate_node_types.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {node.candidate_node_types.map((t) => (
                <span
                  key={t}
                  className="text-[10px] font-mono border border-[var(--color-ink4)] rounded px-1 bg-white text-[var(--color-ink3)]"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
