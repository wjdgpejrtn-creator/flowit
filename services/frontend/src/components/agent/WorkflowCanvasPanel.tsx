'use client';

/**
 * 우측 접힘 캔버스 — "워크플로우 결과물"을 평소 얇은 핸들로 두고, 클릭 시 펼친다.
 *
 * 디자인 SSOT: Flowit-채팅-레이아웃-구현-프롬프트.md §4.
 *   - 접힘(기본) 52px: 세로 핸들(chevron + 세로 텍스트 + 작업 있음 코랄 점).
 *   - 펼침 320px: 상단 편집/실행 버튼 + 점격자 배경 노드 칩 세로 나열 + 하단 노드 수.
 *
 * 순수 표시 — 노드 데이터(loadedWorkflow × 카탈로그)는 page.tsx가 chips로 가공해 주입.
 * 편집/실행은 기존 모드 전환(setMode)에 연결(백엔드 흐름 무변경).
 */

import { RiskLevel } from '@common/generated';
import Icon from '@/components/common/Icon';

export interface CanvasNodeChip {
  key: string;
  name: string;
  nodeType: string;
  risk: RiskLevel;
  icon: string;
  color: string;
}

interface WorkflowCanvasPanelProps {
  open: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onRun: () => void;
  chips: CanvasNodeChip[];
  /** 결과물(초안)이 있으면 핸들에 코랄 점 + 하단 노드 수 표시 */
  hasWork: boolean;
}

export default function WorkflowCanvasPanel({ open, onToggle, onEdit, onRun, chips, hasWork }: WorkflowCanvasPanelProps) {
  return (
    <aside
      className="border-l border-[var(--color-line-soft)] bg-[var(--color-paper2)]/40 flex-shrink-0 relative overflow-hidden"
      style={{ width: open ? 320 : 52, transition: 'width .32s cubic-bezier(.4,0,.2,1)' }}
    >
      {/* 접힘 상태 — 얇은 핸들 */}
      {!open && (
        <button
          type="button"
          onClick={onToggle}
          aria-label="워크플로우 캔버스 열기"
          className="absolute inset-0 w-full flex flex-col items-center justify-center gap-3 hover:bg-[var(--color-paper2)]/70 transition-all group"
        >
          <Icon name="chevron-left" className="w-4 h-4 text-[var(--color-ink3)] group-hover:text-[var(--color-accent)]" />
          <span className="text-[11px] font-bold text-[var(--color-ink2)] tracking-widest" style={{ writingMode: 'vertical-rl' }}>
            워크플로우 캔버스
          </span>
          {hasWork && <span className="w-2 h-2 rounded-full bg-[var(--color-accent-coral)] animate-pulse" />}
        </button>
      )}

      {/* 펼침 상태 — 패널 본문 */}
      {open && (
        <div className="h-full flex flex-col" style={{ width: 320 }}>
          {/* 상단 바: 접기 + 제목 + 편집/실행 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-line-soft)] flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <button
                type="button"
                onClick={onToggle}
                aria-label="워크플로우 캔버스 접기"
                className="p-1.5 rounded-lg text-[var(--color-ink3)] hover:bg-white transition-all"
              >
                <Icon name="chevron-right" className="w-4 h-4" />
              </button>
              <span className="text-[12px] font-bold text-[var(--color-ink)] truncate">워크플로우 결과물</span>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <button
                type="button"
                onClick={onEdit}
                className="px-2.5 py-1.5 rounded-lg border border-[var(--color-line-soft)] bg-white hover:bg-[var(--color-paper)] text-[var(--color-ink2)] text-[11px] font-bold flex items-center gap-1 transition-all"
              >
                <Icon name="edit-3" className="w-3 h-3" /> 편집
              </button>
              <button
                type="button"
                onClick={onRun}
                className="px-2.5 py-1.5 rounded-lg bg-[var(--color-accent)] hover:bg-[var(--color-accent3)] text-white text-[11px] font-bold flex items-center gap-1 shadow-sm transition-all"
              >
                <Icon name="play" className="w-3 h-3" /> 실행
              </button>
            </div>
          </div>

          {/* 본문: 점격자 + 노드 칩 세로 나열 */}
          <div
            className="flex-1 overflow-y-auto relative"
            style={{ backgroundImage: 'radial-gradient(#D8CBB8 1.2px, transparent 1.2px)', backgroundSize: '18px 18px' }}
          >
            {chips.length === 0 ? (
              <div className="h-full flex items-center justify-center px-6 text-center">
                <p className="text-[12px] text-[var(--color-ink4)] leading-relaxed">
                  아직 결과물이 없어요.<br />대화로 워크플로우를 만들어 보세요.
                </p>
              </div>
            ) : (
              <div className="p-5 space-y-3">
                {chips.map((chip, i) => (
                  <div key={chip.key}>
                    <div className="flowit-card rounded-xl p-3 flex items-center gap-2.5 shadow-sm relative">
                      <span className="w-8 h-8 rounded-lg bg-[#F7F1E8] border border-[var(--color-line-soft)] flex items-center justify-center flex-shrink-0">
                        <Icon name={chip.icon} className="w-4 h-4" style={{ color: chip.color }} />
                      </span>
                      <div className="leading-tight min-w-0">
                        <p className="text-[12.5px] font-bold text-[var(--color-ink)] truncate">{chip.name}</p>
                        <p className="text-[10px] text-[var(--color-ink4)] font-bold font-mono truncate">{chip.nodeType}</p>
                      </div>
                      {(chip.risk === RiskLevel.HIGH || chip.risk === RiskLevel.RESTRICTED) && (
                        <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-orange-500" title="High" />
                      )}
                    </div>
                    {i < chips.length - 1 && (
                      <div className="flex justify-center pt-3">
                        <Icon name="arrow-down" className="w-4 h-4 text-[var(--color-ink4)]" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 하단 바 */}
          <div className="px-4 py-2.5 border-t border-[var(--color-line-soft)] text-[10px] text-[var(--color-ink4)] font-bold flex items-center gap-1.5 flex-shrink-0">
            <Icon name="git-branch" className="w-3 h-3" />
            {hasWork ? `${chips.length}개 노드 · 초안 저장됨` : '결과물 없음'}
          </div>
        </div>
      )}
    </aside>
  );
}
