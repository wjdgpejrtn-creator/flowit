'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Icon from '@/components/common/Icon';
import { useSkillBuilderStore } from '@/stores/skillBuilderStore';
import { listSkillTemplates, type SkillTemplate } from '@/lib/api/skillApi';
import { listDocuments, type DocumentResponse } from '@/lib/api/documentApi';
import { DOCS_STORAGE_KEY } from '@/lib/storage/keys';

/**
 * 위저드 '재료 선택' 단계(문서 有無 분기 → 문서/템플릿 선택) UI.
 *
 * 위저드의 *선택* 파트로, 채팅에서는 좌측 인라인 카드, 문서 탭/빌더 페이지에서는
 * 본문에 그대로 놓인다. 진행 상태(branch/startBuild)는 skillBuilderStore가 공유하고,
 * 문서/템플릿 목록은 이 단계 전용이라 컴포넌트 로컬로 둔다.
 */

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

const KIND_LABEL: Record<SkillTemplate['kind'], string> = {
  industry: '업종',
  functional: '직무',
};

export default function SkillBuilderChooseCards() {
  const branch = useSkillBuilderStore((s) => s.branch);
  const setBranch = useSkillBuilderStore((s) => s.setBranch);
  const startBuild = useSkillBuilderStore((s) => s.startBuild);

  // 내 문서 선택(document 분기)
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [pickedDocId, setPickedDocId] = useState<string>('');

  // default 템플릿(template 분기)
  const [templates, setTemplates] = useState<SkillTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

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
  }, [templates.length, templatesLoading, setBranch]);

  const industryTemplates = templates.filter((t) => t.kind === 'industry');
  const functionalTemplates = templates.filter((t) => t.kind === 'functional');

  // ── 첫 화면: 문서 有無 분기 ──────────────────────────────────────────────
  if (branch === 'ask') {
    return (
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
    );
  }

  // ── document 분기: 내 문서 선택 ──────────────────────────────────────────
  if (branch === 'document') {
    return (
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
    );
  }

  // ── template 분기: 업종/직무 카드 그리드 ─────────────────────────────────
  return (
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
  );
}
