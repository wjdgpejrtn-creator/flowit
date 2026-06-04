'use client';

import { useState } from 'react';
import type { WorkflowExplanation } from '@common/generated';
import { RiskLevel } from '@common/generated';
import Icon from '@/components/common/Icon';
import RiskPill from '@/components/common/RiskPill';
import type { FilledNode } from '@/lib/filledParams';
import { reviewCount } from '@/lib/filledParams';
import { AiMarker } from '@/components/agent/ChatTurns';

interface ConfirmCardProps {
  /** explanation 없는 레거시 응답 시 보여줄 기본 메시지 */
  message: string;
  /** 컨펌 게이트 신뢰 매니페스트 (영역 C composer _explain_node가 채움). 없으면 graceful fallback */
  explanation?: WorkflowExplanation;
  /** AI가 자동으로 채운(또는 채웠을) 입력값 — loadedWorkflow × 카탈로그 input_schema로 프론트 계산 */
  filledParams?: FilledNode[];
  onSave: () => void;
  onEdit: () => void;
  loading?: boolean;
}

// high/restricted는 사용자가 실행 전에 반드시 인지해야 할 쓰기/위험 권한 → fill로 강조
function _isStrong(level: RiskLevel): boolean {
  return level === RiskLevel.HIGH || level === RiskLevel.RESTRICTED;
}

const _RISK_KO: Record<RiskLevel, string> = {
  [RiskLevel.LOW]: '낮음',
  [RiskLevel.MEDIUM]: '보통',
  [RiskLevel.HIGH]: '높음',
  [RiskLevel.RESTRICTED]: '제한',
};
const _RISK_RANK: Record<RiskLevel, number> = {
  [RiskLevel.LOW]: 0,
  [RiskLevel.MEDIUM]: 1,
  [RiskLevel.HIGH]: 2,
  [RiskLevel.RESTRICTED]: 3,
};

function _maxRisk(levels: RiskLevel[]): RiskLevel {
  return levels.reduce((hi, l) => (_RISK_RANK[l] > _RISK_RANK[hi] ? l : hi), RiskLevel.LOW);
}

/**
 * 신뢰 가능한 컨펌 게이트 (confirm-gate-explanation 영역 D) — 디자인 3-3.
 *
 * "대화는 텍스트, 카드는 최소" 원칙: 별도 카드 박스 없이 AI 본문 문장으로 워크플로우를
 * 서술하고, **권한(.em-perm) · 위험도(.em-risk) · 확인 필요 값(.em-val)** 만 인라인 강조한다.
 * 권한 매니페스트/filledParams 구조화 패널은 기본 접힘 — 본문 아래 작은 "상세 보기 ›" 링크로
 * 펼치는 감사용 탈출구로 둔다. 노드 파라미터 수정은 우측 캔버스 편집으로 유도(별도 입력 카드 X).
 * explanation이 없으면(레거시 result 프레임) 기존 단순 메시지로 fallback.
 */
export default function ConfirmCard({ message, explanation, filledParams, onSave, onEdit, loading = false }: ConfirmCardProps) {
  const [showDetail, setShowDetail] = useState(false);
  const filled = filledParams ?? [];
  const reviewN = reviewCount(filled);
  const reviewFields = filled.flatMap((n) =>
    n.fields.filter((f) => f.tag === 'review').map((f) => ({ node: n.nodeName, ...f })),
  );

  const perms = explanation?.permissions ?? [];
  const permNames = Array.from(new Set(perms.map((p) => p.connection)));
  const riskKo = perms.length > 0 ? _RISK_KO[_maxRisk(perms.map((p) => p.risk_level))] : null;
  const assumptions = explanation?.assumptions ?? [];
  const hasDetail = perms.length > 0 || filled.length > 0 || assumptions.length > 0;

  return (
    <div className="flex gap-3">
      <AiMarker />
      <div className="flex-1 min-w-0 pt-0.5">
        {/* 라벨 줄: 최종 확인 + 가로 구분선 */}
        <div className="flex items-center gap-1.5 mb-2">
          <Icon name="sparkles" className="w-3.5 h-3.5 text-[var(--color-accent-coral)]" />
          <span className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider">최종 확인</span>
          <span className="h-px flex-1 bg-[var(--color-line-soft)]" />
        </div>

        {/* 본문 — 박스 없이 문장 서술. 권한/위험도/확인값만 인라인 강조. */}
        <div className="ai-prose text-[14.5px] text-[var(--color-ink)] leading-[1.8] break-keep">
          <p>{explanation?.summary || explanation?.intent_restatement || message}</p>

          {permNames.length > 0 && (
            <p>
              이 워크플로우는{' '}
              {permNames.map((name, i) => (
                <span key={name}>
                  {i > 0 && (i === permNames.length - 1 ? '와(과) ' : ', ')}
                  <span className="em-perm">{name}</span>
                </span>
              ))}{' '}
              권한이 필요하며, 위험도는 <span className="em-risk">{riskKo}</span>입니다.
            </p>
          )}

          {reviewFields.length > 0 && (
            <p className="text-[var(--color-ink2)] text-[13px]">
              실행 전에{' '}
              {reviewFields.map((f, i) => (
                <span key={`${f.node}:${f.name}`}>
                  {i > 0 && ', '}
                  <span className="font-mono text-[12px] text-[var(--color-ink3)]">{f.name}</span>=
                  <span className="em-val">{f.value}</span>
                </span>
              ))}{' '}
              값을 다시 한 번 확인해 주세요. 다르면 우측 캔버스 편집에서 수정할 수 있어요.
            </p>
          )}
        </div>

        {/* 상세 보기 — 본문 아래 작은 텍스트 링크 한 줄. 기본 접힘(감사용 탈출구). */}
        {hasDetail && (
          <>
            <button
              type="button"
              onClick={() => setShowDetail((v) => !v)}
              className="mt-2 inline-flex items-center gap-1 text-[11px] font-bold text-[var(--color-ink3)] hover:text-[var(--color-ink)] transition-colors"
            >
              상세 보기
              {reviewN > 0 && !showDetail && (
                <span className="text-[10px] font-bold text-[var(--color-danger)]">확인 필요 {reviewN}</span>
              )}
              <Icon name={showDetail ? 'chevron-down' : 'chevron-right'} className="w-3 h-3" />
            </button>
            {showDetail && (
              <DetailPanel perms={perms} filled={filled} assumptions={assumptions} />
            )}
          </>
        )}

        {/* 액션 — 가볍게 두 개만 (디자인 3-3) */}
        <div className="flex items-center gap-2 mt-3.5">
          <button
            type="button"
            onClick={onSave}
            disabled={loading}
            className="px-4 py-2 rounded-xl bg-[var(--color-accent)] hover:bg-[var(--color-accent3)] text-white text-[12.5px] font-bold shadow-sm transition-all flex items-center gap-1.5 disabled:opacity-50"
          >
            <Icon name="check" className="w-3.5 h-3.5" /> {loading ? '저장 중…' : '저장하고 활성화'}
          </button>
          <button
            type="button"
            onClick={onEdit}
            disabled={loading}
            className="px-4 py-2 rounded-xl border border-[var(--color-line-soft)] hover:bg-[var(--color-paper2)] text-[var(--color-ink2)] text-[12.5px] font-bold transition-all flex items-center gap-1.5 disabled:opacity-50"
          >
            <Icon name="edit-3" className="w-3.5 h-3.5" /> 편집
          </button>
        </div>
      </div>
    </div>
  );
}

const _SUBHEAD = 'font-bold text-[11px] text-[var(--color-ink3)] uppercase tracking-wider mb-[6px]';

/** 감사용 상세 — 별도 카드/보더 박스로 키우지 않고 얇은 상단 구분선 안에 평문 행으로만. */
function DetailPanel({
  perms,
  filled,
  assumptions,
}: {
  perms: WorkflowExplanation['permissions'];
  filled: FilledNode[];
  assumptions: string[];
}) {
  return (
    <div className="mt-2 pt-3 border-t border-[var(--color-line-soft)] flex flex-col gap-[14px]">
      {/* 권한 매니페스트 */}
      {perms.length > 0 && (
        <div>
          <div className={_SUBHEAD}>이 워크플로우가 접근하는 것</div>
          <div className="flex flex-col gap-[5px]">
            {perms.map((perm) => (
              <div key={`${perm.connection}:${perm.node_name}`} className="flex items-center gap-[8px] text-[12px]">
                <RiskPill level={perm.risk_level} fill={_isStrong(perm.risk_level)} label={perm.connection} />
                <span className="text-[var(--color-ink3)] truncate">{perm.node_name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 실행 전 확인할 입력값 (filledParams) */}
      {filled.length > 0 && (
        <div>
          <div className={_SUBHEAD}>실행 전 확인할 입력값</div>
          <p className="text-[11px] text-[var(--color-ink3)] mb-[6px]">
            별도로 말씀하지 않은 항목은 AI가 자동으로 채웠어요. 다르면 편집에서 수정하세요.
          </p>
          <div className="flex flex-col gap-[6px]">
            {filled.map((node) => (
              <div key={node.nodeName}>
                <div className="text-[12px] font-semibold text-[var(--color-ink2)]">{node.nodeName}</div>
                <ul className="mt-[2px] flex flex-col gap-[2px]">
                  {node.fields.map((f) => (
                    <li key={f.name} className="flex items-baseline gap-[6px] text-[12px]">
                      <span className="font-mono text-[11px] text-[var(--color-ink3)] flex-shrink-0">{f.name}</span>
                      <span className="text-[var(--color-ink3)]">=</span>
                      <span className="font-mono text-[11px] text-[var(--color-ink2)] break-all min-w-0">{f.value}</span>
                      {f.tag === 'review' && (
                        <span className="ml-auto flex-shrink-0 text-[10px] font-bold text-[var(--color-danger)]">⚠ 확인 필요</span>
                      )}
                      {f.tag === 'default' && (
                        <span className="ml-auto flex-shrink-0 text-[10px] text-[var(--color-ink4)]">기본값</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 가정·기본값 */}
      {assumptions.length > 0 && (
        <div>
          <div className={_SUBHEAD}>가정한 항목 {assumptions.length}개</div>
          <ul className="flex flex-col gap-[3px] list-disc list-inside text-[12px] text-[var(--color-ink2)]">
            {assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
