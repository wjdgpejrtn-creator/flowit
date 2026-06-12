'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Icon from '@/components/common/Icon';
import { useSkillBuilderStore } from '@/stores/skillBuilderStore';
import type { SkillLifecycleState } from '@/lib/api/skillApi';

/**
 * 스킬 상세 편집 캔버스 — 위저드 build 단계(재료에서 추출한 초안 검토·편집·게시).
 *
 * 위저드의 *편집* 파트로, 채팅에서는 우측 캔버스, 문서 탭/빌더 페이지에서는 본문 폼이
 * 된다. 진행 상태는 skillBuilderStore가 공유한다. 진입점마다 다른 내비게이션(스킬 보기/
 * 취소/새로 만들기)은 선택적 콜백으로 오버라이드한다 — 미지정 시 라우팅 기본값.
 */

const LIFECYCLE_PILL: Record<SkillLifecycleState, [string, string, string]> = {
  draft: ['초안', '#F1ECE4', '#9C8B7B'],
  review: ['검토중', '#FBE9D8', '#C8860B'],
  approved: ['승인됨', '#E7F6EF', '#10B981'],
  published: ['게시됨', '#EAF1FB', '#3B73C4'],
  archived: ['보관됨', '#F1ECE4', '#A2917F'],
};

const INPUT_CLASS =
  'w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-white text-xs font-bold text-ink';

export interface SkillDetailCanvasProps {
  // 생성/게시 완료 후 '스킬 보기'. 미지정 시 /skills/{id} 라우팅.
  onViewSkill?: (skillId: string) => void;
  // '취소'. 미지정 시 /marketplace 라우팅.
  onCancel?: () => void;
  // '새 스킬 만들기'(생성 성공 후). 미지정 시 위저드 초기화.
  onNewSkill?: () => void;
}

export default function SkillDetailCanvas({ onViewSkill, onCancel, onNewSkill }: SkillDetailCanvasProps) {
  const router = useRouter();
  const [showTip, setShowTip] = useState(false);

  const {
    material,
    name,
    description,
    instructions,
    tagsInput,
    loading,
    error,
    created,
    isEdit,
    extracting,
    extractStep,
    extractError,
    extractedSkills,
    selectedDraftIdx,
    detailLoadingIdx,
    selectedStaging,
    setName,
    setDescription,
    setInstructions,
    setTagsInput,
    runExtract,
    selectDraft,
    handleCreate,
    resetToChoose,
  } = useSkillBuilderStore();

  const tags = tagsInput.split(',').map((t) => t.trim()).filter(Boolean);

  // 추출 초안을 선택했으나 상세(instructions/staging)가 아직 안 온 상태 — 저장 차단(빈 지침서 버그 방지).
  const detailPending = selectedDraftIdx !== null && selectedStaging === undefined;
  const submitDisabled = loading || !name.trim() || !description.trim() || detailPending;

  const viewSkill = (skillId: string) => (onViewSkill ? onViewSkill(skillId) : router.push(`/skills/${skillId}`));
  const cancel = () => (onCancel ? onCancel() : router.push('/marketplace'));
  const newSkill = () => {
    if (onNewSkill) return onNewSkill();
    resetToChoose();
    setTagsInput('');
    useSkillBuilderStore.setState({ created: null });
  };

  // ── 생성 성공 ────────────────────────────────────────────────────────────
  if (created) {
    return (
      <div className="bg-white rounded-2xl p-7 shadow-sm border border-line-soft flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Icon name="check-circle-2" className="w-6 h-6 text-accent" />
          <span className="font-bold text-base text-ink">
            {created.lifecycle_state === 'published'
              ? '스킬이 게시됐습니다!'
              : isEdit
                ? '변경 사항이 저장됐습니다!'
                : '스킬이 생성됐습니다!'}
          </span>
          {(() => {
            const [label, bg, fg] = LIFECYCLE_PILL[created.lifecycle_state];
            return (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
                style={{ background: bg, color: fg }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: fg }} />
                {label}
              </span>
            );
          })()}
        </div>

        <div className="flex flex-col gap-2 text-xs font-bold">
          <div className="flex gap-2">
            <span className="text-ink3 w-16 flex-shrink-0">이름</span>
            <span className="text-ink">{created.name}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-ink3 w-16 flex-shrink-0">설명</span>
            <span className="text-ink2">{created.description}</span>
          </div>
          {created.tags.length > 0 && (
            <div className="flex gap-2">
              <span className="text-ink3 w-16 flex-shrink-0">태그</span>
              <div className="flex gap-1 flex-wrap">
                {created.tags.map((t) => (
                  <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-paper2 text-ink3">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => viewSkill(created.skill_id)}
            className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3"
          >
            스킬 보기
          </button>
          <button
            type="button"
            onClick={newSkill}
            className="px-5 py-2.5 rounded-xl border border-line-soft text-xs font-bold text-ink3 hover:bg-paper"
          >
            새 스킬 만들기
          </button>
        </div>
      </div>
    );
  }

  // ── 추출·검토·생성 폼 ─────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div className="px-4 py-3 rounded-xl bg-danger-soft border border-danger/30 text-xs font-bold text-danger flex items-center gap-2">
          <Icon name="alert-triangle" className="w-4 h-4" />
          {error}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleCreate(isEdit ? false : true);
        }}
        className="bg-white rounded-2xl p-7 shadow-sm border border-line-soft flex flex-col gap-5"
      >
        {/* 선택한 재료 표시 + 다시 선택 (편집 모드에서는 숨김) */}
        {!isEdit && material && (
          <>
            <div className="flex items-center justify-between gap-2 rounded-xl border border-line-soft px-3 py-2.5 bg-paper/30">
              <div className="flex items-center gap-2 text-xs font-bold min-w-0">
                <Icon
                  name={material.kind === 'document' ? 'file-text' : 'sparkles'}
                  className="w-4 h-4 text-accent flex-shrink-0"
                />
                <span className="truncate text-ink" title={material.label}>
                  {material.label}
                </span>
              </div>
              <button
                type="button"
                onClick={resetToChoose}
                className="text-[11px] text-accent font-bold underline flex-shrink-0"
              >
                재료 다시 선택
              </button>
            </div>

            {/* 자동 추출 패널 — 진행/오류/초안 목록 */}
            <div className="flex flex-col gap-2 border border-accent-coral/30 rounded-2xl bg-coral-light p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                  <Icon name="wand-2" className="w-4 h-4 text-accent-coral" />
                  {material.kind === 'template' ? '템플릿' : '문서'}에서 자동 추출 (AI)
                </span>
                {!extracting && (
                  <button
                    type="button"
                    onClick={() => material && void runExtract(material)}
                    className="text-[11px] text-accent font-bold underline"
                  >
                    다시 추출
                  </button>
                )}
              </div>

              {extractError && <div className="text-[11px] font-bold text-danger">⚠ {extractError}</div>}

              {extracting ? (
                <p className="text-[11px] text-ink3 font-bold">{extractStep ?? '추출 중…'}</p>
              ) : extractedSkills.length === 0 ? (
                <p className="text-[11px] text-ink3 font-bold leading-relaxed">
                  {extractError
                    ? '다시 추출을 눌러 재시도하세요.'
                    : '추출된 초안이 없습니다. 다시 추출을 눌러보세요.'}
                </p>
              ) : (
                <div className="flex flex-col gap-2">
                  <p className="text-[11px] text-ink3 font-bold">
                    {extractedSkills.length}개의 초안이 추출됐습니다. 하나를 선택하면 아래 폼에 채워집니다.
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {extractedSkills.map((s, idx) => (
                      <button
                        key={`${s.node_type}-${idx}`}
                        type="button"
                        onClick={() => void selectDraft(s, idx, material)}
                        disabled={detailLoadingIdx !== null}
                        className={[
                          'text-left rounded-xl px-3 py-2 transition-colors bg-white border disabled:opacity-60',
                          selectedDraftIdx === idx ? 'border-accent' : 'border-line-soft hover:border-accent',
                        ].join(' ')}
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs text-ink">{s.name}</span>
                          {detailLoadingIdx === idx ? (
                            <span className="text-[10px] text-ink3 font-bold">상세 불러오는 중…</span>
                          ) : (
                            selectedDraftIdx === idx && (
                              <span className="text-[10px] text-accent font-bold">✓ 선택됨</span>
                            )
                          )}
                        </div>
                        <div className="text-[11px] text-ink3 font-bold mt-0.5">{s.description}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* 스킬 이름 */}
        <div className="space-y-1">
          <label className="text-xs font-bold text-ink">
            스킬 이름 <span className="text-accent-coral">*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="예: 주간 리포트 자동화"
            required
            className={INPUT_CLASS}
          />
        </div>

        {/* 설명 */}
        <div className="space-y-1">
          <label className="text-xs font-bold text-ink">
            설명 <span className="text-accent-coral">*</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="이 스킬이 어떤 작업을 자동화하는지 설명해주세요."
            required
            rows={3}
            className={`${INPUT_CLASS} resize-none`}
          />
        </div>

        {/* 실행 지침 + 툴팁 */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold text-ink">
              실행 지침 <span className="text-ink4 font-bold">(선택)</span>
            </label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowTip((v) => !v)}
                aria-label="실행 지침 도움말"
                className="text-accent hover:text-accent-coral transition-all flex items-center justify-center"
              >
                <Icon name="info" className="w-[18px] h-[18px]" />
              </button>
              {showTip && (
                <div className="absolute right-0 bottom-full mb-2.5 w-max whitespace-nowrap bg-coral-light border border-accent-coral/30 rounded-2xl p-4 shadow-lg z-30 animate-fade-in text-left">
                  <p className="text-sm font-bold text-accent mb-2">💡 Tip</p>
                  <p className="text-[11px] text-ink2 font-bold leading-relaxed">
                    실행 지침은 AI 에이전트가 스킬을 실행할 때 참조합니다.
                  </p>
                  <p className="text-[11px] text-ink2 font-bold leading-relaxed mt-1.5">
                    구체적일수록 더 정확한 결과를 얻을 수 있어요.
                  </p>
                </div>
              )}
            </div>
          </div>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="이 스킬을 실행할 때 AI가 따라야 할 상세 지침을 작성하세요."
            rows={5}
            className={`${INPUT_CLASS} resize-none font-mono`}
          />
        </div>

        {/* 태그 */}
        <div className="space-y-1">
          <label className="text-xs font-bold text-ink">
            태그 <span className="text-ink4 font-bold">(쉼표로 구분)</span>
          </label>
          <input
            type="text"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="예: 리포트, Slack, 자동화"
            className={INPUT_CLASS}
          />
          {tags.length > 0 && (
            <div className="flex gap-1 flex-wrap mt-1">
              {tags.map((t) => (
                <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-paper2 text-ink3 font-bold">
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 버튼 — 편집모드: 변경 저장 / 신규: 검토&게시 + 초안 저장 */}
        {isEdit ? (
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={submitDisabled}
              className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? '처리 중…' : '변경 사항 저장'}
            </button>
            <button
              type="button"
              onClick={cancel}
              className="px-5 py-2.5 rounded-xl border border-line-soft text-xs font-bold text-ink3 hover:bg-paper"
            >
              취소
            </button>
          </div>
        ) : (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={submitDisabled}
                className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {loading ? '처리 중…' : '검토 & 게시'}
              </button>
              <button
                type="button"
                disabled={submitDisabled}
                onClick={() => void handleCreate(false)}
                className="px-5 py-2.5 rounded-xl border border-line-soft text-xs font-bold text-ink hover:bg-paper disabled:opacity-60 disabled:cursor-not-allowed"
              >
                초안 저장
              </button>
              <button
                type="button"
                onClick={cancel}
                className="px-5 py-2.5 rounded-xl border border-line-soft text-xs font-bold text-ink3 hover:bg-paper"
              >
                취소
              </button>
            </div>
            {detailPending ? (
              detailLoadingIdx !== null ? (
                <p className="text-[10px] text-amber-600 font-bold flex items-center gap-1">
                  <Icon name="info" className="w-3 h-3" />
                  상세(지침서·입출력)를 추출하는 중이에요. 완료된 뒤 저장하면 지침서가 함께 저장됩니다.
                </p>
              ) : (
                <p className="text-[10px] text-red-600 font-bold flex items-center gap-1">
                  <Icon name="info" className="w-3 h-3" />
                  상세 추출에 실패했어요. 위 카드를 다시 선택하거나 ‘재료 다시 선택’으로 재시도해 주세요.
                </p>
              )
            ) : (
              <p className="text-[10px] text-ink4 font-bold flex items-center gap-1">
                <Icon name="info" className="w-3 h-3" />
                검토 & 게시하면 바로 워크플로우에서 사용할 수 있어요. 초안 저장은 나중에 마켓플레이스에서 게시할 수 있어요.
              </p>
            )}
          </div>
        )}
      </form>
    </div>
  );
}
