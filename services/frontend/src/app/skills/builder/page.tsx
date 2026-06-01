'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import { createPersonalSkill, streamExtractSkillFromDocument } from '@/lib/api/skillApi';
import type { PersonalSkill, SkillLifecycleState, ExtractedSkillDraft } from '@/lib/api/skillApi';
import { listDocuments, type DocumentResponse } from '@/lib/api/documentApi';
import { DOCS_STORAGE_KEY } from '@/lib/storage/keys';

function fmtSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function loadDocs(): DocumentResponse[] {
  try {
    const raw = localStorage.getItem(DOCS_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as DocumentResponse[]) : [];
  } catch {
    return [];
  }
}

const LIFECYCLE_PILL: Record<SkillLifecycleState, [string, string, string]> = {
  draft: ['초안', '#F1ECE4', '#9C8B7B'],
  review: ['검토중', '#FBE9D8', '#C8860B'],
  approved: ['승인됨', '#E7F6EF', '#10B981'],
  published: ['게시됨', '#EAF1FB', '#3B73C4'],
  archived: ['보관됨', '#F1ECE4', '#A2917F'],
};

const STEPS = [
  { step: '1', label: '초안 작성', desc: 'DRAFT 상태로 생성됩니다.' },
  { step: '2', label: '검토 제출', desc: '마켓플레이스 → 검토 요청' },
  { step: '3', label: '승인 & 게시', desc: '관리자 승인 후 게시됩니다.' },
  { step: '4', label: '팀/전사 공유', desc: '승격 요청으로 범위 확장' },
];

const INPUT_CLASS =
  'w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-white text-xs font-bold text-ink';

export default function SkillBuilderPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<PersonalSkill | null>(null);
  const [sourceDocId, setSourceDocId] = useState<string | null>(null);
  const [fromHandoff, setFromHandoff] = useState(false);

  // 마켓 '수정' → 편집 모드: ?edit=1&name=&desc=&tags= 로 폼 prefill.
  const [isEdit, setIsEdit] = useState(false);
  const [editLabel, setEditLabel] = useState('');
  const [showTip, setShowTip] = useState(false);

  // 문서→스킬 자동 추출(위저드 1단계) 상태.
  const [extracting, setExtracting] = useState(false);
  const [extractStep, setExtractStep] = useState<string | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [extractedSkills, setExtractedSkills] = useState<ExtractedSkillDraft[]>([]);
  const [selectedDraftIdx, setSelectedDraftIdx] = useState<number | null>(null);
  const extractAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => extractAbortRef.current?.abort(), []);

  // 쿼리 파싱: source_document_id(핸드오프) / edit(마켓 수정).
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const src = sp.get('source_document_id');
    if (src) {
      setSourceDocId(src);
      setFromHandoff(true);
    }
    if (sp.get('edit') === '1') {
      setIsEdit(true);
      const n = sp.get('name') ?? '';
      setName(n);
      setDescription(sp.get('desc') ?? '');
      setTagsInput(sp.get('tags') ?? '');
      setEditLabel(n);
    }
  }, []);

  // 문서 목록: 서버 SSOT, 실패 시 localStorage 캐시 폴백 (#219)
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const serverDocs = await listDocuments();
        if (!cancelled) setDocs(serverDocs);
      } catch {
        if (!cancelled) setDocs(loadDocs());
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const tags = tagsInput.split(',').map((t) => t.trim()).filter(Boolean);
  const sourceDoc = sourceDocId ? docs.find((d) => d.document_id === sourceDocId) ?? null : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !description.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const skill = await createPersonalSkill({
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim() || undefined,
        tags,
        source_document_id: sourceDocId ?? undefined,
      });
      setCreated(skill);
      showToast(isEdit ? '변경 사항을 저장했습니다.' : `'${skill.name}' 스킬을 DRAFT로 등록했습니다.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '스킬 생성 실패');
    } finally {
      setLoading(false);
    }
  };

  const applyDraft = (draft: ExtractedSkillDraft, idx: number) => {
    setName(draft.name);
    setDescription(draft.description);
    setInstructions(draft.instructions);
    setSelectedDraftIdx(idx);
  };

  const handleExtract = async () => {
    if (!sourceDocId || extracting) return;
    extractAbortRef.current?.abort();
    const controller = new AbortController();
    extractAbortRef.current = controller;

    setExtracting(true);
    setExtractError(null);
    setExtractStep(null);
    setExtractedSkills([]);
    setSelectedDraftIdx(null);

    const STEP_LABELS: Record<string, string> = {
      'skills_builder.sop.parse_document': '문서 파싱 중…',
      'skills_builder.sop.llm_extract': 'AI가 스킬을 추출 중…',
    };

    try {
      await streamExtractSkillFromDocument(
        sourceDocId,
        (frame) => {
          switch (frame.frame_type) {
            case 'agent_node': {
              const node = frame.agent_node_name as string;
              setExtractStep(STEP_LABELS[node] ?? '처리 중…');
              break;
            }
            case 'result': {
              const payload = frame.payload as { skills?: ExtractedSkillDraft[] } | undefined;
              const skills = payload?.skills ?? [];
              setExtractedSkills(skills);
              if (skills.length === 1) applyDraft(skills[0], 0);
              break;
            }
            case 'error':
              setExtractError((frame.message as string) ?? '추출 중 오류가 발생했습니다.');
              break;
          }
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setExtractError(err instanceof Error ? err.message : '추출 요청 실패');
    } finally {
      setExtracting(false);
      setExtractStep(null);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />

      <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-4">
        <div>
          <h2 className="text-lg font-bold text-ink">{isEdit ? '스킬 수정' : '스킬빌더'}</h2>
          <p className="text-xs text-ink3 font-bold">
            {isEdit
              ? `'${editLabel}' 스킬의 내용을 수정합니다.`
              : '새 스킬을 만들어 마켓플레이스에 등록하거나 조직 내에 배포하세요.'}
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* 좌: 폼 */}
          <div className="lg:col-span-9">
            {error && (
              <div className="mb-4 px-4 py-3 rounded-xl bg-danger-soft border border-danger/30 text-xs font-bold text-danger flex items-center gap-2">
                <Icon name="alert-triangle" className="w-4 h-4" />
                {error}
              </div>
            )}

            {created ? (
              <div className="bg-white rounded-2xl p-7 shadow-sm border border-line-soft flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <Icon name="check-circle-2" className="w-6 h-6 text-accent" />
                  <span className="font-bold text-base text-ink">
                    {isEdit ? '변경 사항이 저장됐습니다!' : '스킬이 생성됐습니다!'}
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
                    onClick={() => router.push(`/skills/${created.skill_id}`)}
                    className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3"
                  >
                    스킬 보기
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setCreated(null);
                      setName('');
                      setDescription('');
                      setInstructions('');
                      setTagsInput('');
                    }}
                    className="px-5 py-2.5 rounded-xl border border-line-soft text-xs font-bold text-ink3 hover:bg-paper"
                  >
                    새 스킬 만들기
                  </button>
                </div>
              </div>
            ) : (
              <form
                onSubmit={(e) => void handleSubmit(e)}
                className="bg-white rounded-2xl p-7 shadow-sm border border-line-soft grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-5"
              >
                {/* 기반 문서 */}
                {fromHandoff ? (
                  <div className="space-y-1 md:col-span-2">
                    <label className="text-xs font-bold text-ink">기반 문서</label>
                    <div className="flex items-center gap-2 p-2.5 rounded-xl border border-line-soft bg-white">
                      <Icon name="file-text" className="w-4 h-4 text-accent flex-shrink-0" />
                      <span className="text-xs font-bold text-ink truncate" title={sourceDoc?.file_name ?? sourceDocId ?? ''}>
                        {sourceDoc?.file_name ?? sourceDocId}
                      </span>
                      {sourceDoc && (
                        <span className="text-[10px] text-ink3 font-bold flex-shrink-0">
                          {fmtSize(sourceDoc.file_size)}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-ink4 font-bold">
                      이 문서를 기반으로 스킬을 만듭니다. 생성 시 문서 연결이 함께 저장됩니다.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-ink">
                      기반 문서 <span className="text-ink4 font-bold">(선택)</span>
                    </label>
                    <select
                      value={sourceDocId ?? ''}
                      onChange={(e) => setSourceDocId(e.target.value || null)}
                      disabled={docs.length === 0}
                      className="w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-paper/30 text-xs font-bold text-ink disabled:text-ink4 disabled:cursor-not-allowed"
                    >
                      <option value="">
                        {docs.length === 0 ? '업로드된 문서가 없습니다' : '문서를 선택하세요 (선택)'}
                      </option>
                      {docs.map((doc) => (
                        <option key={doc.document_id} value={doc.document_id}>
                          {doc.file_name} · {fmtSize(doc.file_size)}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-ink4 font-bold">
                      문서를 선택하면 스킬에 기반 문서로 연결됩니다.
                      {docs.length === 0 && (
                        <>
                          {' '}
                          <Link href="/documents" className="text-accent underline">
                            문서 탭에서 업로드
                          </Link>
                        </>
                      )}
                    </p>
                  </div>
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

                {/* 문서→스킬 자동 추출 (핸드오프 시에만) */}
                {fromHandoff && (
                  <div className="md:col-span-2 flex flex-col gap-2 border border-accent-coral/30 rounded-2xl bg-coral-light p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                        <Icon name="wand-2" className="w-4 h-4 text-accent-coral" />
                        문서에서 자동 추출 (AI)
                      </span>
                      {extractedSkills.length > 0 && (
                        <button
                          type="button"
                          onClick={() => void handleExtract()}
                          disabled={extracting}
                          className="text-[11px] text-accent font-bold underline disabled:opacity-50"
                        >
                          다시 추출
                        </button>
                      )}
                    </div>

                    {extractError && <div className="text-[11px] font-bold text-danger">⚠ {extractError}</div>}

                    {extractedSkills.length === 0 ? (
                      <>
                        <p className="text-[11px] text-ink3 font-bold leading-relaxed">
                          기반 문서를 분석해 스킬 초안(이름·설명·실행 지침)을 자동으로 채워줍니다.
                        </p>
                        <button
                          type="button"
                          onClick={() => void handleExtract()}
                          disabled={extracting}
                          className="px-4 py-2 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 disabled:opacity-60 self-start flex items-center gap-1.5"
                        >
                          <Icon name="wand-2" className="w-3.5 h-3.5" />
                          {extracting ? `추출 중… ${extractStep ?? ''}` : '이 문서에서 스킬 추출'}
                        </button>
                      </>
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
                              onClick={() => applyDraft(s, idx)}
                              className={[
                                'text-left rounded-xl px-3 py-2 transition-colors bg-white border',
                                selectedDraftIdx === idx
                                  ? 'border-accent'
                                  : 'border-line-soft hover:border-accent',
                              ].join(' ')}
                            >
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-xs text-ink">{s.name}</span>
                                {selectedDraftIdx === idx && (
                                  <span className="text-[10px] text-accent font-bold">✓ 선택됨</span>
                                )}
                              </div>
                              <div className="text-[11px] text-ink3 font-bold mt-0.5">{s.description}</div>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 설명 */}
                <div className="space-y-1 md:col-span-2">
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
                <div className="space-y-1 md:col-span-2">
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
                    rows={4}
                    className={`${INPUT_CLASS} resize-none font-mono`}
                  />
                </div>

                {/* 태그 */}
                <div className="space-y-1 md:col-span-2">
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

                {/* 버튼 */}
                <div className="flex items-center space-x-2 pt-1 md:col-span-2">
                  <button
                    type="submit"
                    disabled={loading || !name.trim() || !description.trim()}
                    className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {loading ? '생성 중…' : isEdit ? '변경 사항 저장' : '스킬 생성'}
                  </button>
                  <button
                    type="button"
                    onClick={() => router.push('/marketplace')}
                    className="px-5 py-2.5 rounded-xl border border-line-soft text-xs font-bold text-ink3 hover:bg-paper"
                  >
                    취소
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* 우: 가이드 */}
          <aside className="lg:col-span-3 self-start">
            <h4 className="text-sm font-bold text-ink uppercase tracking-wider mb-5">스킬 생성 흐름</h4>
            <div className="space-y-6 text-sm">
              {STEPS.map(({ step, label, desc }) => (
                <div key={step} className="flex items-start gap-2.5">
                  <span className="w-7 h-7 rounded-full bg-accent text-white flex items-center justify-center text-xs font-black flex-shrink-0">
                    {step}
                  </span>
                  <div>
                    <p className="font-bold text-ink">{label}</p>
                    <p className="text-ink3 font-bold text-xs leading-relaxed mt-0.5">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
