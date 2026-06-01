'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import ErrorBanner from '@/components/common/ErrorBanner';
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

const LIFECYCLE_COLOR: Record<SkillLifecycleState, string> = {
  draft:     'var(--color-ink4)',
  review:    'var(--color-risk-med)',
  approved:  'var(--color-risk-low)',
  published: 'var(--color-accent)',
  archived:  'var(--color-ink4)',
};
const LIFECYCLE_LABEL: Record<SkillLifecycleState, string> = {
  draft: '초안', review: '검토 중', approved: '승인됨', published: '게시됨', archived: '보관됨',
};

// 위저드 추출 재료 — 내 문서 또는 default 템플릿. label은 build 단계 상단 표시용.
type Material =
  | { kind: 'document'; id: string; label: string }
  | { kind: 'template'; code: string; label: string };

function toExtractBody(m: Material): ExtractMaterial {
  return m.kind === 'document'
    ? { source_document_id: m.id }
    : { template_code: m.code };
}

const STEP_LABELS: Record<string, string> = {
  'skills_builder.sop.parse_document': '문서 파싱 중…',
  'skills_builder.sop.llm_extract': 'AI가 스킬을 추출 중…',
};

const KIND_LABEL: Record<SkillTemplate['kind'], string> = {
  industry: '업종',
  functional: '직무',
};

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
  const runExtract = useCallback(async (m: Material) => {
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
  }, [applyDraft]);

  // build 단계 진입 + 추출 시작. 재료를 인자로 직접 받아 stale closure 회피.
  const startBuild = useCallback((m: Material) => {
    setMaterial(m);
    setPhase('build');
    setName('');
    setDescription('');
    setInstructions('');
    setExtractedSkills([]);
    setSelectedDraftIdx(null);
    void runExtract(m);
  }, [runExtract]);

  // 문서→빌더 핸드오프: ?source_document_id=<id> 면 첫 화면을 건너뛰고 바로 문서 위저드로.
  const handoffHandled = useRef(false);
  useEffect(() => {
    if (handoffHandled.current) return;
    const param = new URLSearchParams(window.location.search).get('source_document_id');
    if (param) {
      handoffHandled.current = true;
      setBranch('document');
      startBuild({ kind: 'document', id: param, label: param });
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
    } catch (err) {
      setError(err instanceof Error ? err.message : '스킬 생성 실패');
    } finally {
      setLoading(false);
    }
  };

  const industryTemplates = templates.filter((t) => t.kind === 'industry');
  const functionalTemplates = templates.filter((t) => t.kind === 'functional');

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* 헤더 */}
      <div className="px-6 pt-5 pb-3 border-b-[1.5px] border-[var(--color-ink3)] bg-[var(--color-paper2)] flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-[14px]">스킬빌더</span>
          </div>
          <p className="text-[12px] text-[var(--color-ink3)] mt-1">
            문서가 있으면 문서로, 없으면 업종/직무 템플릿으로 — 검토·편집만으로 나만의 스킬을 만드세요.
          </p>
        </div>
      </div>

      <div className="flex-1 p-6 flex gap-6">
        <div className="flex-1 max-w-[560px]">
          {error && (
            <div className="mb-4">
              <ErrorBanner><span>⚠ {error}</span></ErrorBanner>
            </div>
          )}

          {/* ── 1단계: 재료 선택(첫 화면 분기) ───────────────────────────────── */}
          {phase === 'choose' && branch === 'ask' && (
            <div className="flex flex-col gap-4">
              <div className="text-[15px] font-bold text-[var(--color-ink)]">
                업무 관련 문서가 있으신가요?
              </div>
              <p className="text-[12px] text-[var(--color-ink3)] leading-relaxed">
                업무 매뉴얼·SOP 같은 문서가 있으면 그 문서로, 없으면 우리가 준비한 업종/직무
                템플릿으로 시작할 수 있어요. 어느 쪽이든 AI가 초안을 만들어주고 검토·편집만 하면 됩니다.
              </p>
              <div className="flex flex-col gap-3 mt-1">
                <button
                  type="button"
                  onClick={() => setBranch('document')}
                  className="text-left border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-4 hover:border-[var(--color-accent)] transition-colors"
                >
                  <div className="font-bold text-[14px] text-[var(--color-ink)]">📄 네, 문서가 있어요</div>
                  <div className="text-[12px] text-[var(--color-ink3)] mt-1">
                    내가 올린 문서를 골라 그 내용으로 스킬을 추출합니다.
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => void loadTemplates()}
                  className="text-left border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-4 hover:border-[var(--color-accent)] transition-colors"
                >
                  <div className="font-bold text-[14px] text-[var(--color-ink)]">✨ 아니요, 직접 만들게요</div>
                  <div className="text-[12px] text-[var(--color-ink3)] mt-1">
                    업종이나 직무를 고르면 표준 템플릿을 바탕으로 스킬을 만들어드려요.
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* 1단계 — document 분기: 내 문서 선택 */}
          {phase === 'choose' && branch === 'document' && (
            <div className="flex flex-col gap-4">
              <button type="button" onClick={() => setBranch('ask')} className="text-[12px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] self-start">
                ← 뒤로
              </button>
              <div className="text-[15px] font-bold text-[var(--color-ink)]">어떤 문서로 만들까요?</div>
              <div className="flex flex-col gap-1">
                <label className="text-[12px] font-bold text-[var(--color-ink3)]">기반 문서</label>
                <select
                  value={pickedDocId}
                  onChange={(e) => setPickedDocId(e.target.value)}
                  disabled={docs.length === 0}
                  className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] disabled:bg-[var(--color-paper2)] disabled:text-[var(--color-ink4)] disabled:cursor-not-allowed"
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
                  <p className="text-[11px] text-[var(--color-ink4)] flex items-center gap-1">
                    <span>ⓘ</span>
                    <Link href="/documents" className="text-[var(--color-accent)] underline">문서 탭에서 업로드</Link>
                    하거나, 뒤로 가서 템플릿으로 시작하세요.
                  </p>
                )}
              </div>
              <Btn
                primary
                type="button"
                disabled={!pickedDocId}
                onClick={() => {
                  const doc = docs.find((d) => d.document_id === pickedDocId);
                  startBuild({ kind: 'document', id: pickedDocId, label: doc?.file_name ?? pickedDocId });
                }}
              >
                이 문서로 시작 →
              </Btn>
            </div>
          )}

          {/* 1단계 — template 분기: 업종/직무 카드 그리드 */}
          {phase === 'choose' && branch === 'template' && (
            <div className="flex flex-col gap-4">
              <button type="button" onClick={() => setBranch('ask')} className="text-[12px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] self-start">
                ← 뒤로
              </button>
              <div className="text-[15px] font-bold text-[var(--color-ink)]">업종 또는 직무를 골라주세요</div>
              {templatesError && <div className="text-[12px] text-[var(--color-risk-high)]">⚠ {templatesError}</div>}
              {templatesLoading ? (
                <div className="text-[12px] text-[var(--color-ink3)]">템플릿을 불러오는 중…</div>
              ) : templates.length === 0 && !templatesError ? (
                <div className="text-[12px] text-[var(--color-ink3)]">
                  준비된 템플릿이 없습니다. 뒤로 가서 문서로 시작해보세요.
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  {([['업종', industryTemplates], ['직무', functionalTemplates]] as const).map(
                    ([groupLabel, items]) =>
                      items.length > 0 && (
                        <div key={groupLabel} className="flex flex-col gap-2">
                          <div className="text-[11px] font-bold text-[var(--color-ink4)] uppercase">{groupLabel}</div>
                          <div className="grid grid-cols-2 gap-2">
                            {items.map((t) => (
                              <button
                                key={t.code}
                                type="button"
                                onClick={() => startBuild({ kind: 'template', code: t.code, label: `${KIND_LABEL[t.kind]} · ${t.name}` })}
                                className="text-left border-[1.5px] border-[var(--color-ink4)] rounded-[4px_8px_4px_8px] bg-[var(--color-surface)] p-3 hover:border-[var(--color-accent)] transition-colors"
                              >
                                <div className="font-bold text-[13px] text-[var(--color-ink)]">{t.name}</div>
                                <div className="text-[11px] text-[var(--color-ink3)] mt-[2px] line-clamp-2">{t.description}</div>
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
          {phase === 'build' && (
            created ? (
              // 생성 완료 상태
              <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-6 flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-[20px]">✓</span>
                  <span className="font-bold text-[15px]">스킬이 생성됐습니다!</span>
                  <span
                    className="text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px]"
                    style={{ color: LIFECYCLE_COLOR[created.lifecycle_state], borderColor: LIFECYCLE_COLOR[created.lifecycle_state] }}
                  >
                    {LIFECYCLE_LABEL[created.lifecycle_state]}
                  </span>
                </div>

                <div className="flex flex-col gap-2 text-[13px]">
                  <div className="flex gap-2">
                    <span className="text-[var(--color-ink3)] w-20 flex-shrink-0">이름</span>
                    <span className="font-bold">{created.name}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-[var(--color-ink3)] w-20 flex-shrink-0">설명</span>
                    <span>{created.description}</span>
                  </div>
                  {created.tags.length > 0 && (
                    <div className="flex gap-2">
                      <span className="text-[var(--color-ink3)] w-20 flex-shrink-0">태그</span>
                      <div className="flex gap-1 flex-wrap">
                        {created.tags.map((t) => (
                          <span key={t} className="text-[11px] border border-[var(--color-ink4)] rounded px-1">{t}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="flex gap-2">
                    <span className="text-[var(--color-ink3)] w-20 flex-shrink-0">ID</span>
                    <span className="font-mono text-[11px] text-[var(--color-ink3)]">{created.skill_id}</span>
                  </div>
                </div>

                <div className="flex gap-2">
                  <Btn onClick={() => router.push(`/skills/${created.skill_id}`)}>스킬 보기 →</Btn>
                  <Btn ghost onClick={() => { setCreated(null); resetToChoose(); setTagsInput(''); }}>
                    새 스킬 만들기
                  </Btn>
                </div>
              </div>
            ) : (
              <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
                {/* 선택한 재료 표시 + 다시 선택 */}
                <div className="flex items-center justify-between gap-2 border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] bg-[var(--color-surface)]">
                  <div className="flex items-center gap-2 text-[13px] min-w-0">
                    <span>{material?.kind === 'document' ? '📄' : '✨'}</span>
                    <span className="font-bold truncate" title={material?.label}>{material?.label}</span>
                  </div>
                  <button type="button" onClick={resetToChoose} className="text-[11px] text-[var(--color-accent)] underline flex-shrink-0">
                    재료 다시 선택
                  </button>
                </div>

                {/* 자동 추출 패널 — 진행/오류/초안 목록 */}
                <div className="flex flex-col gap-2 border-[1.5px] border-[var(--color-accent)] rounded-[5px_11px_6px_10px] bg-[var(--color-hl)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] font-bold text-[var(--color-ink)]">
                      🪄 {material?.kind === 'template' ? '템플릿' : '문서'}에서 자동 추출 (AI)
                    </span>
                    {!extracting && (
                      <button
                        type="button"
                        onClick={() => material && void runExtract(material)}
                        className="text-[11px] text-[var(--color-accent)] underline"
                      >
                        다시 추출
                      </button>
                    )}
                  </div>

                  {extractError && <div className="text-[11px] text-[var(--color-risk-high)]">⚠ {extractError}</div>}

                  {extracting ? (
                    <p className="text-[11px] text-[var(--color-ink3)]">{extractStep ?? '추출 중…'}</p>
                  ) : extractedSkills.length === 0 ? (
                    <p className="text-[11px] text-[var(--color-ink3)] leading-relaxed">
                      {extractError ? '다시 추출을 눌러 재시도하세요.' : '추출된 초안이 없습니다. 다시 추출을 눌러보세요.'}
                    </p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      <p className="text-[11px] text-[var(--color-ink3)]">
                        {extractedSkills.length}개의 초안이 추출됐습니다. 하나를 선택하면 아래 폼에 채워집니다.
                      </p>
                      <div className="flex flex-col gap-[6px]">
                        {extractedSkills.map((s, idx) => (
                          <button
                            key={`${s.node_type}-${idx}`}
                            type="button"
                            onClick={() => applyDraft(s, idx)}
                            className={[
                              'text-left border-[1.5px] rounded-[4px_8px_4px_8px] px-3 py-2 transition-colors bg-[var(--color-surface)]',
                              selectedDraftIdx === idx
                                ? 'border-[var(--color-accent)]'
                                : 'border-[var(--color-ink4)] hover:border-[var(--color-ink)]',
                            ].join(' ')}
                          >
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-[13px] text-[var(--color-ink)]">{s.name}</span>
                              {selectedDraftIdx === idx && (
                                <span className="text-[10px] text-[var(--color-accent)] font-bold">✓ 선택됨</span>
                              )}
                            </div>
                            <div className="text-[11px] text-[var(--color-ink3)] mt-[2px]">{s.description}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-[12px] font-bold text-[var(--color-ink3)]">
                    스킬 이름 <span className="text-[var(--color-risk-restricted)]">*</span>
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="예: 주간 리포트 자동화"
                    required
                    className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)]"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-[12px] font-bold text-[var(--color-ink3)]">
                    설명 <span className="text-[var(--color-risk-restricted)]">*</span>
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="이 스킬이 어떤 작업을 자동화하는지 설명해주세요."
                    required
                    rows={3}
                    className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] resize-none"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-[12px] font-bold text-[var(--color-ink3)]">
                    실행 지침 <span className="text-[var(--color-ink4)] font-normal">(선택)</span>
                  </label>
                  <textarea
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    placeholder="이 스킬을 실행할 때 AI가 따라야 할 상세 지침을 작성하세요."
                    rows={5}
                    className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] resize-none font-mono"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-[12px] font-bold text-[var(--color-ink3)]">
                    태그 <span className="text-[var(--color-ink4)] font-normal">(쉼표로 구분)</span>
                  </label>
                  <input
                    type="text"
                    value={tagsInput}
                    onChange={(e) => setTagsInput(e.target.value)}
                    placeholder="예: 리포트, Slack, 자동화"
                    className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)]"
                  />
                  {tags.length > 0 && (
                    <div className="flex gap-1 flex-wrap mt-1">
                      {tags.map((t) => (
                        <span key={t} className="text-[11px] border border-[var(--color-ink4)] rounded px-1 bg-[var(--color-paper2)]">{t}</span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex gap-2 mt-1">
                  <Btn primary type="submit" disabled={loading || !name.trim() || !description.trim()}>
                    {loading ? '생성 중…' : '스킬 생성'}
                  </Btn>
                  <Btn ghost type="button" onClick={() => router.push('/marketplace')}>취소</Btn>
                </div>
              </form>
            )
          )}
        </div>

        {/* 우: 가이드 */}
        <aside className="w-[260px] flex-shrink-0 flex flex-col gap-3 text-[12px] text-[var(--color-ink3)]">
          <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] p-4 bg-[var(--color-surface)]">
            <div className="font-bold text-[13px] text-[var(--color-ink)] mb-2">스킬 생성 흐름</div>
            <div className="flex flex-col gap-2">
              {[
                { step: '1', label: '재료 선택', desc: '문서 또는 업종/직무 템플릿' },
                { step: '2', label: '추출 & 검토', desc: 'AI 초안을 검토·편집' },
                { step: '3', label: '스킬 생성', desc: 'DRAFT 상태로 생성' },
                { step: '4', label: '검토 & 게시', desc: '승인 후 팀/전사 공유' },
              ].map(({ step, label, desc }) => (
                <div key={step} className="flex items-start gap-2">
                  <span className="w-[18px] h-[18px] rounded-full border-[1.5px] border-[var(--color-ink)] flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-[1px]">
                    {step}
                  </span>
                  <div>
                    <div className="font-bold text-[var(--color-ink)]">{label}</div>
                    <div>{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="border-[1.5px] border-[var(--color-line-soft)] rounded-[5px_11px_6px_10px] p-3 bg-[var(--color-paper2)]">
            <div className="font-bold text-[12px] text-[var(--color-ink)] mb-1">💡 팁</div>
            <p className="leading-relaxed">
              문서가 없어도 괜찮아요. 업종/직무 템플릿을 고르면 표준 업무를 바탕으로
              AI가 초안을 만들어줍니다. 검토·편집만 하면 끝이에요.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
