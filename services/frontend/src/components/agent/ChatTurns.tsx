'use client';

/**
 * AI 채팅(Composer) 메시지 렌더 컴포넌트 — "대화는 텍스트, 카드는 최소".
 *
 * 디자인 SSOT: docs/Flowit-채팅-레이아웃-구현-프롬프트.md (claude.ai/design 핸드오프).
 *   1. 유저 입력만 말풍선(오른쪽 갈색 pill) — 화면의 유일한 채팅 말풍선.
 *   2. AI 출력은 카드/테두리/배경 없이 작은 마커 + 본문 텍스트로 흐른다.
 *   3. 진행 중 단계는 dim 텍스트 + 스피너 한 줄.
 *   4. 선택지 카드는 (A) 스킬 선택 / (B) 최종 결과 선택, 두 순간에만.
 *
 * 순수 표시(presentational) — SSE/store/API 연동 없음. page.tsx가 상태를 주입한다.
 */

import type { ReactNode } from 'react';
import Icon from '@/components/common/Icon';

// ─── AI 마커 (28px 코랄 원 + sparkles) ───────────────────────────────────────
// blank=true면 같은 화자의 연속 블록에서 자리만 비워 정렬을 유지한다.

export function AiMarker({ blank = false }: { blank?: boolean }) {
  if (blank) return <span className="w-7 h-7 flex-shrink-0" aria-hidden />;
  return (
    <span className="w-7 h-7 rounded-full bg-[var(--color-coral-light)] border border-[var(--color-hl2)] flex items-center justify-center flex-shrink-0 mt-0.5">
      <Icon name="sparkles" className="w-3.5 h-3.5 text-[var(--color-accent-coral)]" />
    </span>
  );
}

// ─── 유저 입력 (유일한 말풍선) ───────────────────────────────────────────────

export function UserBubble({ children }: { children: ReactNode }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%] bg-[var(--color-accent)] text-[#FCF7EF] rounded-[20px] rounded-br-lg px-4 py-2.5 text-[14.5px] font-medium leading-relaxed break-keep shadow-[0_2px_8px_-2px_rgba(70,58,48,.3)]">
        {children}
      </div>
    </div>
  );
}

// ─── AI 출력 (카드 없음, 마커 + 본문 텍스트) ──────────────────────────────────
// 기본 응답 본문은 .ai-prose. blankMarker로 연속 블록 정렬.

export function AiTurn({
  children,
  blankMarker = false,
  prose = true,
}: {
  children: ReactNode;
  blankMarker?: boolean;
  prose?: boolean;
}) {
  return (
    <div className="flex gap-3">
      <AiMarker blank={blankMarker} />
      <div
        className={[
          'flex-1 min-w-0 pt-0.5',
          prose ? 'ai-prose text-[14.5px] text-[var(--color-ink)] leading-[1.75] break-keep' : '',
        ].join(' ')}
      >
        {children}
      </div>
    </div>
  );
}

// ─── 에이전트 작업과정 (채팅 인라인) — 완료 단계 dim 체크라인 + 진행 단계 스피너 ──
// 디자인 3-2: 우측 패널 대신 대화 흐름에 인라인으로. 판단근거(rationale)도 그 아래 평문.

export function AgentWorkProcess({
  labels,
  currentIndex,
  rationale,
}: {
  labels: string[];
  /** stepIndexFor 결과(1-base). 0이면 아직 단계 미진입 → 일반 분석 중. */
  currentIndex: number;
  rationale?: string;
}) {
  return (
    <div className="flex gap-3">
      <AiMarker />
      <div className="flex-1 min-w-0 pt-0.5">
        <div className="space-y-1.5 text-[12.5px] font-bold">
          {labels.map((label, i) => {
            const n = i + 1;
            if (n < currentIndex) {
              // 완료 단계 — 흐릿한 체크 줄
              return (
                <div key={i} className="flex items-center gap-2 text-[var(--color-ink3)]">
                  <Icon name="check" className="w-3.5 h-3.5 text-[var(--color-accent)] flex-shrink-0" />
                  <span>{label} 완료</span>
                </div>
              );
            }
            if (n === currentIndex) {
              // 진행 중 단계 — 스피너 한 줄
              return (
                <div key={i} className="flex items-center gap-2 text-[var(--color-ink4)]">
                  <span className="flowit-spinner" />
                  <span>{label}…</span>
                </div>
              );
            }
            return null;
          })}
          {currentIndex === 0 && (
            <div className="flex items-center gap-2 text-[var(--color-ink4)]">
              <span className="flowit-spinner" />
              <span>워크플로우를 분석 중…</span>
            </div>
          )}
        </div>
        {rationale && (
          <p className="mt-2 text-[13px] text-[var(--color-ink3)] leading-[1.7] break-keep">{rationale}</p>
        )}
      </div>
    </div>
  );
}

// ─── 선택지 카드 — 스킬 선택(A) ───────────────────────────────────────────────
// 채팅에서 유저 말풍선 외 등장하는 유일한 카드(상호작용 surface).
// 노드 파라미터 입력용 카드는 만들지 않는다 (디자인 0번 규칙).

export interface SkillOption {
  skill_id: string;
  name: string;
  description?: string;
}

export function SkillSelectionCard({
  prompt,
  options,
  allowSkip,
  onPick,
  onSkip,
  disabled = false,
}: {
  prompt: string;
  options: SkillOption[];
  allowSkip: boolean;
  onPick: (skillId: string) => void;
  onSkip: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex gap-3">
      <AiMarker blank />
      <div className="flex-1 min-w-0">
        <div className="bg-[var(--color-surface)] border border-[rgba(70,58,48,.15)] rounded-2xl p-3 shadow-[0_4px_16px_-8px_rgba(70,58,48,.25)]">
          <div className="flex items-center gap-1.5 px-1 pb-2.5 mb-0.5">
            <Icon name="mouse-pointer-click" className="w-3.5 h-3.5 text-[var(--color-accent-coral)]" />
            <span className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider">
              {prompt}
            </span>
          </div>
          <div className="grid gap-1.5">
            {options.map((opt) => (
              <button
                key={opt.skill_id}
                type="button"
                disabled={disabled}
                onClick={() => onPick(opt.skill_id)}
                className="choice-opt flex items-start justify-between gap-2.5 text-left border border-[var(--color-line-soft)] rounded-xl px-3.5 py-3 bg-white disabled:opacity-50"
              >
                <span className="flex items-start gap-2.5 min-w-0 flex-1">
                  <span className="w-7 h-7 rounded-lg bg-[var(--color-coral-light)] border border-[var(--color-hl2)] flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Icon name="sparkles" className="w-3.5 h-3.5 text-[var(--color-accent-coral)]" />
                  </span>
                  <span className="min-w-0 flex-1 break-keep">
                    <span className="block text-[13.5px] font-bold text-[var(--color-ink)] leading-snug">{opt.name}</span>
                    {opt.description &&
                      opt.description
                        .split("\n")
                        .map((para) => para.trim())
                        .filter(Boolean)
                        .map((para, i) => (
                          <span
                            key={i}
                            className="block text-[11.5px] text-[var(--color-ink3)] font-medium leading-[1.6] mt-1"
                          >
                            {para}
                          </span>
                        ))}
                  </span>
                </span>
                <Icon name="chevron-right" className="w-4 h-4 text-[var(--color-ink4)] flex-shrink-0 mt-0.5" />
              </button>
            ))}
            {allowSkip && (
              <button
                type="button"
                disabled={disabled}
                onClick={onSkip}
                className="choice-opt flex items-center gap-2.5 text-left border border-dashed border-[var(--color-line-soft)] rounded-xl px-3.5 py-2.5 bg-[var(--color-paper)]/40 disabled:opacity-50"
              >
                <span className="w-7 h-7 rounded-lg bg-[var(--color-paper2)] flex items-center justify-center flex-shrink-0">
                  <Icon name="plus" className="w-3.5 h-3.5 text-[var(--color-ink3)]" />
                </span>
                <span className="text-[13px] font-bold text-[var(--color-ink3)]">스킬 없이 진행</span>
              </button>
            )}
          </div>
        </div>
        <p className="text-[10.5px] text-[var(--color-ink4)] font-bold mt-1.5 pl-1 flex items-center gap-1">
          <Icon name="info" className="w-3 h-3" /> 카드는 선택이 필요한 분기에서만 등장합니다.
        </p>
      </div>
    </div>
  );
}
