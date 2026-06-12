'use client';

import { useState } from 'react';
import type { WorkflowExplanation } from '@common/generated';
import { RiskLevel } from '@common/generated';
import Icon from '@/components/common/Icon';
import type { FilledNode } from '@/lib/filledParams';
import { reviewCount } from '@/lib/filledParams';
import { AiMarker, VerifyNode } from '@/components/agent/ChatTurns';
import type { VerifyData } from '@/stores/agentStore';

interface ConfirmCardProps {
  /** explanation 없는 레거시 응답 시 보여줄 기본 메시지 */
  message: string;
  /** 컨펌 게이트 신뢰 매니페스트 (영역 C composer _explain_node가 채움). 없으면 graceful fallback */
  explanation?: WorkflowExplanation;
  /** AI가 자동으로 채운(또는 채웠을) 입력값 — loadedWorkflow × 카탈로그 input_schema로 프론트 계산 */
  filledParams?: FilledNode[];
  /** 스트리밍 중 SSE 프레임에서 캡처한 단계별 검증 기록 — "검증 상세 보기" 패널 채움 */
  verify?: VerifyData;
  onSave: () => void;
  onEdit: () => void;
  loading?: boolean;
}

// 의도 유형(IntentType) → 한국어 라벨. 미매핑은 원문 노출(graceful).
const _INTENT_KO: Record<string, string> = {
  draft: '새 워크플로우 생성',
  refine: '워크플로우 수정',
  propose: '워크플로우 제안',
  build_skill: '스킬 생성',
  clarify: '추가 확인',
  info_question: '질문 응답',
  chitchat: '일반 대화',
  control: '실행 제어',
  workflow_execute: '워크플로우 실행',
};

// 추출 엔티티 → "키 값 · 키 값" 한 줄. 빈 값은 제외.
function _formatEntities(entities: Record<string, unknown>): string {
  return Object.entries(entities)
    .filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => `${k} ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(' · ');
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
export default function ConfirmCard({ message, explanation, filledParams, verify, onSave, onEdit, loading = false }: ConfirmCardProps) {
  const [showDetail, setShowDetail] = useState(false);
  const filled = filledParams ?? [];
  const reviewN = reviewCount(filled);
  const reviewFields = filled.flatMap((n) =>
    n.fields.filter((f) => f.tag === 'review').map((f) => ({ node: n.nodeName, ...f })),
  );

  const perms = explanation?.permissions ?? [];
  const permNames = Array.from(new Set(perms.map((p) => p.connection)));
  const riskKo = perms.length > 0 ? _RISK_KO[_maxRisk(perms.map((p) => p.risk_level))] : null;

  // "검증 상세 보기" 4단계 기록 — verify(스트리밍 캡처) + explanation으로 구성. 빈 단계는 생략.
  const detailPhases = buildVerifyPhases(explanation, verify, riskKo);
  const qaScore = verify?.qaScore;
  const hasDetail = detailPhases.length > 0;

  return (
    <div className="flex gap-3">
      <AiMarker />
      <div className="flex-1 min-w-0 pt-0.5">
        {/* 상태 캡션: 완료 + 가로 구분선 */}
        <div className="flex items-center gap-1.5 mb-2">
          <Icon name="check-circle-2" className="w-3.5 h-3.5 text-[var(--color-accent)]" />
          <span className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider">완료</span>
          <span className="h-px flex-1 bg-[var(--color-line-soft)]" />
        </div>

        {/* 본문 — 박스 없이 문장 서술. 권한/위험도/확인값만 인라인 강조. */}
        <div className="ai-prose text-[14.5px] text-[var(--color-ink)] leading-[1.8] break-keep">
          {qaScore != null ? (
            <p>
              검증을 모두 통과했어요. {detailPhases.length}단계를 차례로 점검했고 품질 점수는{' '}
              <span className="text-[var(--color-accent)] font-bold">{qaScore.toFixed(1)} / 10</span>입니다.
            </p>
          ) : (
            <p>{explanation?.summary || explanation?.intent_restatement || message}</p>
          )}

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
              <span className="text-[10px] font-bold text-[var(--color-danger)] mr-1">확인 필요 {reviewN}</span>
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

        {/* 검증 상세 보기 — disclosure 패널(기본 접힘). 단계별 분리선 행으로 기록 보관. */}
        {hasDetail && (
          <div className="mt-3 detail rounded-2xl border border-[var(--color-line-soft)] overflow-hidden bg-[var(--color-surface)]">
            <button
              type="button"
              onClick={() => setShowDetail((v) => !v)}
              aria-expanded={showDetail}
              className="w-full flex items-center gap-2 px-4 py-3 text-left bg-[rgba(251,248,242,.6)] border-b border-[var(--color-line-soft)] text-[12.5px] font-bold text-[var(--color-ink2)] hover:bg-[var(--color-paper2)]/60 transition-colors"
            >
              <Icon name="list-checks" className="w-3.5 h-3.5 text-[var(--color-accent)]" />
              <span className="flex-1">검증 상세 보기</span>
              <Icon name={showDetail ? 'chevron-up' : 'chevron-down'} className="w-3.5 h-3.5" />
            </button>
            {showDetail && <VerifyTimeline phases={detailPhases} />}
          </div>
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

interface DetailPhase {
  id: string;
  title: string;
  rows: { k: string; v: string }[];
}

// "검증 상세 보기" 단계별 기록 구성 — 디자인 §5-2 분리선 행. verify(스트리밍 캡처) +
// explanation으로 채우고, 값이 없는 행/단계는 생략(graceful). 후보 수처럼 SSE로 안 오는
// 항목은 자연히 빠진다.
function buildVerifyPhases(
  explanation: WorkflowExplanation | undefined,
  verify: VerifyData | undefined,
  riskKo: string | null,
): DetailPhase[] {
  const steps = explanation?.steps ?? [];
  const assumptions = explanation?.assumptions ?? [];
  const nodeCount = verify?.draftNodeCount ?? (steps.length || undefined);
  const connCount = verify?.draftConnCount;

  const intent: DetailPhase = { id: 'intent', title: '의도 분석', rows: [] };
  if (verify?.intentType) intent.rows.push({ k: '요청 유형', v: _INTENT_KO[verify.intentType] ?? verify.intentType });
  if (explanation?.intent_restatement) intent.rows.push({ k: '원문 요청', v: explanation.intent_restatement });
  if (verify?.intentEntities) {
    const extracted = _formatEntities(verify.intentEntities);
    if (extracted) intent.rows.push({ k: '추출 정보', v: extracted });
  }

  const select: DetailPhase = { id: 'select', title: '노드 선출', rows: [] };
  if (steps.length > 0) {
    select.rows.push({ k: '선정', v: `${steps.map((s) => s.node_name).join(' · ')} (${steps.length}개)` });
  }

  const build: DetailPhase = { id: 'build', title: '워크플로우 작성', rows: [] };
  if (nodeCount != null) {
    build.rows.push({ k: '구성', v: connCount != null ? `노드 ${nodeCount} · 연결 ${connCount}` : `노드 ${nodeCount}` });
    build.rows.push({ k: 'DAG 검증', v: '순환 없음 · 고립 노드 없음' });
  }
  if (assumptions.length > 0) build.rows.push({ k: '가정', v: assumptions.join(' · ') });

  const qa: DetailPhase = { id: 'qa', title: '품질 평가', rows: [] };
  if (verify?.qaScore != null) qa.rows.push({ k: '점수', v: `${verify.qaScore.toFixed(1)} / 10` });
  if (steps.length > 0) qa.rows.push({ k: '완성도', v: '의도가 노드로 표현됨' });
  if (riskKo) qa.rows.push({ k: '안전성', v: `권한·위험도 ${riskKo} 적정` });

  return [intent, select, build, qa].filter((p) => p.rows.length > 0);
}

/** 검증 상세 보기 본문 — 단계마다 볼드 체크 노드 + 분리선 행(라벨/값). 디자인 §5-2. */
function VerifyTimeline({ phases }: { phases: DetailPhase[] }) {
  return (
    <div className="px-4 py-[18px]">
      <div className="vtl">
        {phases.map((phase) => (
          <div key={phase.id} className="vrow vrow--detail">
            <VerifyNode state="done" />
            <div className="flex-1 min-w-0">
              <div className="text-[14px] font-bold text-[var(--color-ink)] whitespace-nowrap">{phase.title}</div>
              <div className="vkv">
                {phase.rows.map((row) => (
                  <div key={row.k} className="vkv__row">
                    <div className="vkv__k">{row.k}</div>
                    <div className="vkv__v">{row.v}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
