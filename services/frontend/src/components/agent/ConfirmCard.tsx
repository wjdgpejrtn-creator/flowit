'use client';

import { useState } from 'react';
import type { WorkflowExplanation } from '@common/generated';
import { RiskLevel } from '@common/generated';
import Btn from '@/components/common/Btn';
import RiskPill from '@/components/common/RiskPill';

interface ConfirmCardProps {
  /** explanation 없는 레거시 응답 시 보여줄 기본 메시지 */
  message: string;
  /** 컨펌 게이트 신뢰 매니페스트 (영역 C composer _explain_node가 채움). 없으면 graceful fallback */
  explanation?: WorkflowExplanation;
  onExecute: () => void;
  onEdit: () => void;
  loading?: boolean;
}

const _HEADING = 'font-bold text-[11px] text-[var(--color-ink3)] uppercase tracking-wider mb-[6px]';

// high/restricted는 사용자가 실행 전에 반드시 인지해야 할 쓰기/위험 권한 → fill로 강조
function _isStrong(level: RiskLevel): boolean {
  return level === RiskLevel.HIGH || level === RiskLevel.RESTRICTED;
}

/**
 * 신뢰 가능한 컨펌 게이트 카드 (confirm-gate-explanation 영역 D).
 *
 * one-shot(HITL 없음) 철학에서 신뢰가 몰리는 최종 컨펌 지점. 실행 전에
 * 의도 재진술 / 단계 / 권한 매니페스트 / 가정을 보여주고, 틀리면 편집으로 유도한다.
 * explanation이 없으면(레거시 result 프레임) 기존 단순 메시지로 fallback.
 */
export default function ConfirmCard({ message, explanation, onExecute, onEdit, loading = false }: ConfirmCardProps) {
  const [showAssumptions, setShowAssumptions] = useState(false);

  return (
    <div className="flex items-end gap-2 justify-start">
      <span className="w-[26px] h-[26px] rounded-full bg-[var(--color-agent)] text-white text-[10px] flex items-center justify-center flex-shrink-0 font-bold mb-[1px]">
        AI
      </span>
      <div className="max-w-[78%] px-[12px] py-[10px] text-[13px] leading-relaxed border-[1.5px] bg-[var(--color-surface)] border-[var(--color-ink)] rounded-[8px_12px_12px_4px] flex flex-col gap-[12px]">
        {!explanation ? (
          // ── 레거시 fallback ──
          <p>{message}</p>
        ) : (
          <>
            {/* ① 의도 재진술 */}
            {explanation.intent_restatement && (
              <div>
                <div className={_HEADING}>요청하신 내용</div>
                <p className="text-[var(--color-ink2)]">{explanation.intent_restatement}</p>
              </div>
            )}

            {/* 요약 */}
            {explanation.summary && <p className="text-[var(--color-ink)]">{explanation.summary}</p>}

            {/* ② 단계별 설명 */}
            {explanation.steps.length > 0 && (
              <div>
                <div className={_HEADING}>실행 단계</div>
                <ol className="flex flex-col gap-[5px]">
                  {explanation.steps.map((step) => (
                    <li key={step.order} className="flex items-center gap-[8px]">
                      <span className="font-mono text-[11px] text-[var(--color-ink3)] flex-shrink-0">
                        {step.order}.
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="font-semibold">{step.node_name}</span>
                        {step.description && (
                          <span className="text-[var(--color-ink3)]"> — {step.description}</span>
                        )}
                      </span>
                      <RiskPill level={step.risk_level} />
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {/* ③ 권한 매니페스트 — 항상 노출 (가장 큰 신뢰 레버) */}
            {explanation.permissions.length > 0 && (
              <div className="border-[1.5px] border-[var(--color-line-soft)] rounded-[4px_8px_4px_8px] p-[8px] bg-[var(--color-paper2)]">
                <div className={_HEADING}>이 워크플로우가 접근하는 것</div>
                <ul className="flex flex-col gap-[5px]">
                  {explanation.permissions.map((perm) => (
                    <li
                      key={`${perm.connection}:${perm.node_name}`}
                      className="flex items-center gap-[8px] text-[12px]"
                    >
                      <RiskPill level={perm.risk_level} fill={_isStrong(perm.risk_level)} label={perm.connection} />
                      <span className="text-[var(--color-ink3)] truncate">{perm.node_name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* ④ 가정·기본값 — 접을 수 있음 */}
            {explanation.assumptions.length > 0 && (
              <div>
                <button
                  type="button"
                  onClick={() => setShowAssumptions((v) => !v)}
                  className="text-[11px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] font-semibold"
                >
                  {showAssumptions ? '▾' : '▸'} 가정한 항목 {explanation.assumptions.length}개 (다르면 편집에서 수정)
                </button>
                {showAssumptions && (
                  <ul className="mt-[5px] flex flex-col gap-[3px] list-disc list-inside text-[12px] text-[var(--color-ink2)]">
                    {explanation.assumptions.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </>
        )}

        {/* ⑤ 액션 — 실행 + 원클릭 교정 */}
        <div className="flex items-center gap-2 pt-[2px]">
          <Btn onClick={onExecute} disabled={loading} className="text-[12px]">
            {loading ? '실행 중…' : '▶ 실행'}
          </Btn>
          <Btn ghost onClick={onEdit} disabled={loading} className="text-[12px]">
            ✏️ 편집
          </Btn>
        </div>
      </div>
    </div>
  );
}
