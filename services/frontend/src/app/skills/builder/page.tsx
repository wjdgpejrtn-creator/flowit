'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import ErrorBanner from '@/components/common/ErrorBanner';
import { createPersonalSkill } from '@/lib/api/skillApi';
import type { PersonalSkill, SkillLifecycleState } from '@/lib/api/skillApi';
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

  // 문서→빌더 핸드오프: ?source_document_id=<id> 를 읽어 기반 문서로 표시·전송.
  // 백엔드 source_document_id association 와이어업 완료 — createPersonalSkill 페이로드에 포함한다.
  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get('source_document_id');
    if (param) {
      setSourceDocId(param);
      setFromHandoff(true);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : '스킬 생성 실패');
    } finally {
      setLoading(false);
    }
  };

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
            새 스킬을 만들어 마켓플레이스에 등록하세요.
          </p>
        </div>
      </div>

      <div className="flex-1 p-6 flex gap-6">
        {/* 좌: 폼 */}
        <div className="flex-1 max-w-[560px]">
          {error && (
            <div className="mb-4">
              <ErrorBanner><span>⚠ {error}</span></ErrorBanner>
            </div>
          )}

          {created ? (
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
                        <span key={t} className="text-[11px] border border-[var(--color-ink4)] rounded px-1">
                          {t}
                        </span>
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
                <Btn onClick={() => router.push(`/skills/${created.skill_id}`)}>
                  스킬 보기 →
                </Btn>
                <Btn ghost onClick={() => { setCreated(null); setName(''); setDescription(''); setInstructions(''); setTagsInput(''); }}>
                  새 스킬 만들기
                </Btn>
              </div>
            </div>
          ) : (
            // 입력 폼
            <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
              {/* 기반 문서 association (REQ-010). 문서→빌더 핸드오프(?source_document_id=)면
                  read-only 표시, 아니면 선택 가능한 select. 둘 다 sourceDocId 를 통해
                  createPersonalSkill 페이로드(source_document_id)로 전송된다. */}
              {fromHandoff ? (
                <div className="flex flex-col gap-1">
                  <label className="text-[12px] font-bold text-[var(--color-ink3)]">기반 문서</label>
                  <div className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] text-[13px] bg-[var(--color-surface)] flex items-center gap-2">
                    <span>📄</span>
                    <span className="font-bold truncate" title={sourceDoc?.file_name ?? sourceDocId ?? ''}>
                      {sourceDoc?.file_name ?? sourceDocId}
                    </span>
                    {sourceDoc && (
                      <span className="text-[11px] text-[var(--color-ink3)] flex-shrink-0">
                        {fmtSize(sourceDoc.file_size)}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-[var(--color-ink4)] flex items-center gap-1">
                    <span>ⓘ</span>
                    이 문서를 기반으로 스킬을 만듭니다. 생성 시 문서 연결이 함께 저장됩니다.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-1">
                  <label className="text-[12px] font-bold text-[var(--color-ink3)]">
                    기반 문서 <span className="text-[var(--color-ink4)] font-normal">(선택)</span>
                  </label>
                  <select
                    value={sourceDocId ?? ''}
                    onChange={(e) => setSourceDocId(e.target.value || null)}
                    disabled={docs.length === 0}
                    className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-3 py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] disabled:bg-[var(--color-paper2)] disabled:text-[var(--color-ink4)] disabled:cursor-not-allowed"
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
                  <p className="text-[11px] text-[var(--color-ink4)] flex items-center gap-1">
                    <span>ⓘ</span>
                    문서를 선택하면 스킬에 기반 문서로 연결됩니다.
                    {docs.length === 0 && (
                      <>
                        {' '}
                        <Link href="/documents" className="text-[var(--color-accent)] underline">
                          문서 탭에서 업로드
                        </Link>
                      </>
                    )}
                  </p>
                </div>
              )}

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
                      <span key={t} className="text-[11px] border border-[var(--color-ink4)] rounded px-1 bg-[var(--color-paper2)]">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex gap-2 mt-1">
                <Btn primary type="submit" disabled={loading || !name.trim() || !description.trim()}>
                  {loading ? '생성 중…' : '스킬 생성'}
                </Btn>
                <Btn ghost type="button" onClick={() => router.push('/marketplace')}>
                  취소
                </Btn>
              </div>
            </form>
          )}
        </div>

        {/* 우: 가이드 */}
        <aside className="w-[260px] flex-shrink-0 flex flex-col gap-3 text-[12px] text-[var(--color-ink3)]">
          <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] p-4 bg-[var(--color-surface)]">
            <div className="font-bold text-[13px] text-[var(--color-ink)] mb-2">스킬 생성 흐름</div>
            <div className="flex flex-col gap-2">
              {[
                { step: '1', label: '초안 작성', desc: 'DRAFT 상태로 생성됩니다.' },
                { step: '2', label: '검토 제출', desc: '마켓플레이스 → 검토 요청' },
                { step: '3', label: '승인 & 게시', desc: '관리자 승인 후 게시됩니다.' },
                { step: '4', label: '팀/전사 공유', desc: '승격 요청으로 범위 확장' },
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
              실행 지침은 AI 에이전트가 스킬을 실행할 때 참조합니다.
              구체적일수록 더 정확한 결과를 얻을 수 있어요.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
