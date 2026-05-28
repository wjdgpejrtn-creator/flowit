import type { DraftSpec } from '@common/generated';

interface Props {
  spec: DraftSpec | null;
}

export default function DraftSpecPreview({ spec }: Props) {
  if (!spec) {
    return (
      <p className="text-[12px] text-[var(--color-ink4)] italic">
        AI가 워크플로우 초안을 작성하면 여기에 표시됩니다.
      </p>
    );
  }

  const filledCount = Object.keys(spec.slot_filling_state.filled).length;
  const pendingCount = spec.slot_filling_state.pending.length;

  return (
    <div className="flex flex-col gap-2 text-[12px]">
      {/* 의도 요약 */}
      <div className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] p-[8px] bg-[var(--color-surface)]">
        <div className="text-[10px] font-bold text-[var(--color-ink3)] uppercase tracking-wider mb-1">의도</div>
        <p className="text-[var(--color-ink2)] leading-relaxed">{spec.natural_language_intent}</p>
      </div>

      {/* 슬롯 필링 진행 */}
      {(filledCount > 0 || pendingCount > 0) && (
        <div className="border-[1.5px] border-[var(--color-line-soft)] rounded-[4px_8px_4px_8px] p-[8px] bg-[var(--color-paper2)]">
          <div className="text-[10px] font-bold text-[var(--color-ink3)] uppercase tracking-wider mb-1">
            슬롯 — {filledCount}개 완료 / {pendingCount}개 대기
          </div>
          <div className="flex flex-col gap-1">
            {Object.entries(spec.slot_filling_state.filled).map(([k, v]) => (
              <div key={k} className="flex items-center gap-1">
                <span className="text-[var(--color-risk-low)]">✓</span>
                <span className="font-mono text-[var(--color-ink3)]">{k}</span>
                <span className="text-[var(--color-ink4)]">= {String(v)}</span>
              </div>
            ))}
            {spec.slot_filling_state.pending.map((k) => (
              <div key={k} className="flex items-center gap-1">
                <span className="text-[var(--color-ink4)]">○</span>
                <span className="font-mono text-[var(--color-ink4)]">{k}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 미확정 노드 */}
      {spec.unresolved_nodes.length > 0 && (
        <div className="border-[1.5px] border-[var(--color-risk-med)] rounded-[4px_8px_4px_8px] p-[8px] bg-orange-50">
          <div className="text-[10px] font-bold text-[var(--color-risk-med)] uppercase tracking-wider mb-1">
            미확정 노드 {spec.unresolved_nodes.length}개
          </div>
          {spec.unresolved_nodes.map((n) => (
            <div key={n.placeholder_id} className="text-[11px] text-[var(--color-ink3)] flex items-start gap-1 mt-[2px]">
              <span className="text-[var(--color-risk-med)]">?</span>
              <span>{n.hint}</span>
            </div>
          ))}
        </div>
      )}

      <div className="text-[10px] text-[var(--color-ink4)] font-mono">
        대화 {spec.consultant_turn_count}턴
      </div>
    </div>
  );
}
