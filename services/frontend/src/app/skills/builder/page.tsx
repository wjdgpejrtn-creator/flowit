'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import {
  createPersonalSkill,
  streamExtractSkill,
  listSkillTemplates,
} from '@/lib/api/skillApi';
import type {
  PersonalSkill,
  SkillLifecycleState,
  ExtractedSkillDraft,
  ExtractMaterial,
  SkillTemplate,
} from '@/lib/api/skillApi';
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

// 위저드 추출 재료 — 내 문서 또는 default 템플릿. label은 build 단계 상단 표시용.
type Material =
  | { kind: 'document'; id: string; label: string }
  | { kind: 'template'; code: string; label: string };

function toExtractBody(m: Material): ExtractMaterial {
  return m.kind === 'document' ? { source_document_id: m.id } : { template_code: m.code };
}

const STEP_LABELS: Record<string, string> = {
  'skills_builder.sop.parse_document': '문서 파싱 중…',
  'skills_builder.sop.llm_extract': 'AI가 스킬을 추출 중…',
};

const KIND_LABEL: Record<SkillTemplate['kind'], string> = {
  industry: '업종',
  functional: '직무',
};

const STEPS = [
  { step: '1', label: '재료 선택', desc: '문서 또는 업종/직무 템플릿' },
  { step: '2', label: '추출 & 검토', desc: 'AI 초안을 검토·편집' },
  { step: '3', label: '스킬 생성', desc: 'DRAFT 상태로 생성' },
  { step: '4', label: '검토 & 게시', desc: '승인 후 팀/전사 공유' },
];

const INPUT_CLASS =
  'w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-white text-xs font-bold text-ink';

export default function SkillBuilderPage() {
  const router = useRouter();

  // 위저드 단계 — 'choose'(재료 선택) → 'build'(추출·검토·생성).
  const [phase, setPhase] = useState<'choose' | 'build'>('choose');
  // 'choose' 내 분기 — 'ask'(문서 有無 질문) → 'document'(내 문서 선택) | 'template'(업종/직무 선택).
  const [branch, setBranch] = useState<'ask' | 'document' | 'template'>('ask');
  const [material, setMaterial] = useState<Material | null>(null);

  // 폼 상태
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<PersonalSkill | null>(null);

  // 마켓 '수정' → 편집 모드: ?edit=1&name=&desc=&tags= 로 위저드를 건너뛰고 폼 prefill.
  const [isEdit, setIsEdit] = useState(false);
  const [editLabel, setEditLabel] = useState('');
  const [showTip, setShowTip] = useState(false);

  // 내 문서 선택(document 분기)
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [pickedDocId, setPickedDocId] = useState<string>('');

  // default 템플릿(template 분기)
  const [templates, setTemplates] = useState<SkillTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  // 추출(위저드 1단계) 상태
  const [extracting, setExtracting] = useState(false);
  const [extractStep, setExtractStep] = useState<string | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [extractedSkills, setExtractedSkills] = useState<ExtractedSkillDraft[]>([]);
  const [selectedDraftIdx, setSelectedDraftIdx] = useState<number | null>(null);
  const extractAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => extractAbortRef.current?.abort(), []);

  // 추출된 초안 1건을 폼에 채운다(검토·수정용). 선택 강조용 인덱스 기록.
  const applyDraft = useCallback((draft: ExtractedSkillDraft, idx: number) => {
    setName(draft.name);
    setDescription(draft.description);
    setInstructions(draft.instructions);
    setSelectedDraftIdx(idx);
  }, []);

  // 위저드 1단계 — 재료(문서/템플릿)에서 SkillNode 초안 추출(SSE). 결과를 목록으로 보여주고
  // 사용자가 1건 선택하면 폼에 prefill(단일이면 자동). 저장은 폼 제출(handleSubmit)에서 수행.
  const runExtract = useCallback(
    async (m: Material) => {
      extractAbortRef.current?.abort();
      const controller = new AbortController();
      extractAbortRef.current = controller;

      setExtracting(true);
      setExtractError(null);
      setExtractStep(null);
      setExtractedSkills([]);
      setSelectedDraftIdx(null);

      try {
        await streamExtractSkill(
          toExtractBody(m),
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
    },
    [applyDraft],
  );

  // build 단계 진입 + 추출 시작. 재료를 인자로 직접 받아 stale closure 회피.
  const startBuild = useCallback(
    (m: Material) => {
      setMaterial(m);
      setPhase('build');
      setName('');
      setDescription('');
      setInstructions('');
      setExtractedSkills([]);
      setSelectedDraftIdx(null);
      void runExtract(m);
    },
    [runExtract],
  );

  // 첫 진입 1회: 문서→빌더 핸드오프(?source_document_id=) 또는 마켓 수정(?edit=1).
  const initHandled = useRef(false);
  useEffect(() => {
    if (initHandled.current) return;
    const sp = new URLSearchParams(window.location.search);
    const src = sp.get('source_document_id');
    if (src) {
      initHandled.current = true;
      setBranch('document');
      startBuild({ kind: 'document', id: src, label: src });
      return;
    }
    if (sp.get('edit') === '1') {
      initHandled.current = true;
      const n = sp.get('name') ?? '';
      setIsEdit(true);
      setEditLabel(n);
      setName(n);
      setDescription(sp.get('desc') ?? '');
      setTagsInput(sp.get('tags') ?? '');
      setPhase('build');
    }
  }, [startBuild]);

  // 문서 목록: 서버 SSOT, 실패 시 localStorage 캐시 폴백 (#219). document 분기에서 사용.
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

  // template 분기 진입 시 default 템플릿 목록 로드(1회).
  const loadTemplates = useCallback(async () => {
    setBranch('template');
    if (templates.length > 0 || templatesLoading) return;
    setTemplatesLoading(true);
    setTemplatesError(null);
    try {
      setTemplates(await listSkillTemplates());
    } catch (err) {
      setTemplatesError(err instanceof Error ? err.message : '템플릿 목록을 불러오지 못했습니다.');
    } finally {
      setTemplatesLoading(false);
    }
  }, [templates.length, templatesLoading]);

  const tags = tagsInput.split(',').map((t) => t.trim()).filter(Boolean);

  const resetToChoose = () => {
    extractAbortRef.current?.abort();
    setPhase('choose');
    setBranch('ask');
    setMaterial(null);
    setExtractedSkills([]);
    setExtractError(null);
    setSelectedDraftIdx(null);
  };

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
        // 템플릿 기반 생성은 source_document_id 없음(전역 seed). 문서 기반만 association.
        source_document_id: material?.kind === 'document' ? material.id : undefined,
      });
      setCreated(skill);
      showToast(isEdit ? '변경 사항을 저장했습니다.' : `'${skill.name}' 스킬을 DRAFT로 등록했습니다.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '스킬 생성 실패');
    } finally {
      setLoading(false);
    }
  };

  const industryTemplates = templates.filter((t) => t.kind === 'industry');
  const functionalTemplates = templates.filter((t) => t.kind === 'functional');

  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />

      <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-4">
        <div>
          <h2 className="text-lg font-bold text-ink">{isEdit ? '스킬 수정' : '스킬빌더'}</h2>
          <p className="text-xs text-ink3 font-bold">
            {isEdit
              ? `'${editLabel}' 스킬의 내용을 수정합니다.`
              : '문서가 있으면 문서로, 없으면 업종/직무 템플릿으로 — 검토·편집만으로 나만의 스킬을 만드세요.'}
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* 좌: 위저드/폼 */}
          <div className="lg:col-span-9">
            {error && (
              <div className="mb-4 px-4 py-3 rounded-xl bg-danger-soft border border-danger/30 text-xs font-bold text-danger flex items-center gap-2">
                <Icon name="alert-triangle" className="w-4 h-4" />
                {error}
              </div>
            )}

            {/* ── 1단계: 재료 선택(첫 화면 분기) ───────────────────────────────── */}
            {phase === 'choose' && branch === 'ask' && (
              <div className="bg-white rounded-2xl p-7 shadow-sm border border-line-soft flex flex-col gap-4">
                <div className="text-base font-bold text-ink">업무 관련 문서가 있으신가요?</div>
                <p className="text-xs text-ink3 font-bold leading-relaxed">
                  업무 매뉴얼·SOP 같은 문서가 있으면 그 문서로, 없으면 우리가 준비한 업종/직무 템플릿으로
                  시작할 수 있어요. 어느 쪽이든 AI가 초안을 만들어주고 검토·편집만 하면 됩니다.
                </p>
                <div className="flex flex-col gap-3 mt-1">
                  <button
                    type="button"
                    onClick={() => setBranch('document')}
                    className="text-left rounded-2xl border border-line-soft bg-white p-4 hover:border-accent-coral hover:bg-hl transition-all shadow-sm flex items-start gap-3"
                  >
                    <Icon name="file-text" className="w-5 h-5 text-accent mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="font-bold text-sm text-ink">네, 문서가 있어요</div>
                      <div className="text-xs text-ink3 font-bold mt-1">
                        내가 올린 문서를 골라 그 내용으로 스킬을 추출합니다.
                      </div>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => void loadTemplates()}
                    className="text-left rounded-2xl border border-line-soft bg-white p-4 hover:border-accent-coral hover:bg-hl transition-all shadow-sm flex items-start gap-3"
                  >
                    <Icon name="sparkles" className="w-5 h-5 text-accent-coral mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="font-bold text-sm text-ink">아니요, 직접 만들게요</div>
                      <div className="text-xs text-ink3 font-bold mt-1">
                        업종이나 직무를 고르면 표준 템플릿을 바탕으로 스킬을 만들어드려요.
                      </div>
                    </div>
                  </button>
                </div>
              </div>
            )}

            {/* 1단계 — document 분기: 내 문서 선택 */}
            {phase === 'choose' && branch === 'document' && (
              <div className="bg-white rounded-2xl p-7 shadow-sm border border-line-soft flex flex-col gap-4">
                <button
                  type="button"
                  onClick={() => setBranch('ask')}
                  className="text-xs text-ink3 font-bold hover:text-ink self-start flex items-center gap-1"
                >
                  <Icon name="arrow-left" className="w-3.5 h-3.5" />
                  뒤로
                </button>
                <div className="text-base font-bold text-ink">어떤 문서로 만들까요?</div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-ink">기반 문서</label>
                  <select
                    value={pickedDocId}
                    onChange={(e) => setPickedDocId(e.target.value)}
                    disabled={docs.length === 0}
                    className="w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-paper/30 text-xs font-bold text-ink disabled:text-ink4 disabled:cursor-not-allowed"
                  >
                    <option value="">
                      {docs.length === 0 ? '업로드된 문서가 없습니다' : '문서를 선택하세요'}
                    </option>
                    {docs.map((doc) => (
                      <option key={doc.document_id} value={doc.document_id}>
                        {doc.file_name} · {fmtSize(doc.file_size)}
                      </option>
                    ))}
                  </select>
                  {docs.length === 0 && (
                    <p className="text-[10px] text-ink4 font-bold">
                      <Link href="/documents" className="text-accent underline">
                        문서 탭에서 업로드
                      </Link>
                      하거나, 뒤로 가서 템플릿으로 시작하세요.
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  disabled={!pickedDocId}
                  onClick={() => {
                    const doc = docs.find((d) => d.document_id === pickedDocId);
                    startBuild({ kind: 'document', id: pickedDocId, label: doc?.file_name ?? pickedDocId });
                  }}
                  className="self-start px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  이 문서로 시작 →
                </button>
              </div>
            )}

            {/* 1단계 — template 분기: 업종/직무 카드 그리드 */}
            {phase === 'choose' && branch === 'template' && (
              <div className="bg-white rounded-2xl p-7 shadow-sm border border-line-soft flex flex-col gap-4">
                <button
                  type="button"
                  onClick={() => setBranch('ask')}
                  className="text-xs text-ink3 font-bold hover:text-ink self-start flex items-center gap-1"
                >
                  <Icon name="arrow-left" className="w-3.5 h-3.5" />
                  뒤로
                </button>
                <div className="text-base font-bold text-ink">업종 또는 직무를 골라주세요</div>
                {templatesError && <div className="text-xs font-bold text-danger">⚠ {templatesError}</div>}
                {templatesLoading ? (
                  <div className="text-xs text-ink3 font-bold">템플릿을 불러오는 중…</div>
                ) : templates.length === 0 && !templatesError ? (
                  <div className="text-xs text-ink3 font-bold">
                    준비된 템플릿이 없습니다. 뒤로 가서 문서로 시작해보세요.
                  </div>
                ) : (
                  <div className="flex flex-col gap-4">
                    {([['업종', industryTemplates], ['직무', functionalTemplates]] as const).map(
                      ([groupLabel, items]) =>
                        items.length > 0 && (
                          <div key={groupLabel} className="flex flex-col gap-2">
                            <div className="text-[10px] font-bold text-ink4 uppercase tracking-wide">{groupLabel}</div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {items.map((t) => (
                                <button
                                  key={t.code}
                                  type="button"
                                  onClick={() =>
                                    startBuild({
                                      kind: 'template',
                                      code: t.code,
                                      label: `${KIND_LABEL[t.kind]} · ${t.name}`,
                                    })
                                  }
                                  className="text-left rounded-xl border border-line-soft bg-white p-3 hover:border-accent-coral hover:bg-hl transition-all shadow-sm"
                                >
                                  <div className="font-bold text-xs text-ink">{t.name}</div>
                                  <div className="text-[11px] text-ink3 font-bold mt-0.5 line-clamp-2">
                                    {t.description}
                                  </div>
                                </button>
                              ))}
                            </div>
                          </div>
                        ),
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── 2단계: 추출·검토·생성 ─────────────────────────────────────────── */}
            {phase === 'build' &&
              (created ? (
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
                        resetToChoose();
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

                  <div className="flex items-center gap-2">
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
              ))}
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
