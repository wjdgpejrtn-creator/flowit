'use client';

import { useWorkflowStore } from '@/stores/workflowStore';

export default function ValidationPanel() {
  const errors = useWorkflowStore((s) => s.validationErrors);

  if (errors.length === 0) return null;

  return (
    <div
      data-testid="validation-panel"
      className="border-t-[1.5px] border-[var(--color-status-failed)] p-2 max-h-[180px] overflow-auto"
      style={{ background: 'var(--color-surface)' }}
    >
      <div className="font-bold text-[12px] text-[var(--color-status-failed)] mb-1">
        ⚠ 검증 에러 ({errors.length}건)
      </div>
      <ul className="flex flex-col gap-1">
        {errors.map((err, i) => (
          <li
            key={i}
            className="text-[11px] border-[1.5px] border-[var(--color-status-failed)] rounded p-[6px] bg-[var(--color-paper)]"
          >
            <div className="font-bold">{err.code}</div>
            <div className="text-[var(--color-ink)]">{err.message}</div>
            {err.hint && <div className="text-[var(--color-ink3)] italic">힌트: {err.hint}</div>}
            {(err.node_ids?.length ?? 0) > 0 && (
              <div className="font-mono text-[10px] text-[var(--color-ink3)]">
                노드: {err.node_ids.map((id) => id.slice(0, 8)).join(', ')}
              </div>
            )}
            {err.edge_id && (
              <div className="font-mono text-[10px] text-[var(--color-ink3)]">
                엣지: {err.edge_id.slice(0, 12)}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
