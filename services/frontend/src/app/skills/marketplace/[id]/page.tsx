'use client';

import { Suspense, useEffect, useState, useCallback } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Skel from '@/components/common/Skel';
import ErrorBanner from '@/components/common/ErrorBanner';
import {
  getMarketplaceSkill,
  getMarketplaceSkillDocument,
  type MarketplaceSkill,
  type MarketplaceSkillDocument,
  type MarketplaceScope,
  type SkillLifecycleState,
} from '@/lib/api/skillApi';

/* ── Lifecycle pill (marketplace 목록과 동일) ── */

const LIFECYCLE_CONFIG: Record<SkillLifecycleState, { color: string; label: string }> = {
  draft:     { color: 'var(--color-ink4)',     label: '초안' },
  review:    { color: 'var(--color-risk-med)',  label: '검토 중' },
  approved:  { color: 'var(--color-risk-low)',  label: '승인됨' },
  published: { color: 'var(--color-accent)',    label: '게시됨' },
  archived:  { color: 'var(--color-ink4)',     label: '보관됨' },
};

function LifecyclePill({ state }: { state: SkillLifecycleState }) {
  const { color, label } = LIFECYCLE_CONFIG[state];
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px] whitespace-nowrap"
      style={{ borderColor: color, color }}
    >
      <span className="w-[6px] h-[6px] rounded-full flex-shrink-0" style={{ background: color }} />
      {label}
    </span>
  );
}

const SCOPE_LABEL: Record<MarketplaceScope, string> = { team: '팀', company: '전사' };

/* ── 에러 메시지 분류 ── */

function toErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : '';
  if (msg.startsWith('401')) return '로그인이 만료되었습니다.';
  if (msg.startsWith('404')) return '스킬을 찾을 수 없거나 아직 게시되지 않았습니다.';
  if (msg.startsWith('5')) return '서버 오류가 발생했습니다.';
  if (msg === 'Failed to fetch' || msg === 'Load failed') return '네트워크 연결을 확인해 주세요.';
  return '스킬 정보를 불러올 수 없습니다.';
}

/* ── 읽기 전용 필드 행 ── */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-[6px] border-b border-[var(--color-line-soft)]">
      <span className="text-[12px] text-[var(--color-ink3)] w-[100px] flex-shrink-0 pt-[2px]">{label}</span>
      <span className="text-[13px] text-[var(--color-ink)] flex-1">{children}</span>
    </div>
  );
}

function isMarketplaceScope(v: string | null): v is MarketplaceScope {
  return v === 'team' || v === 'company';
}

/* ── 콘텐츠 ── */

function MarketplaceSkillDetailContent() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const scopeParam = searchParams.get('scope');
  const scope = isMarketplaceScope(scopeParam) ? scopeParam : null;
  const backTab = scope ?? 'company';

  const [skill, setSkill] = useState<MarketplaceSkill | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 지침서(SKILL.md) — 메타와 별개로 lazy-load. 404는 "지침서 없음"(에러 아님)으로 구분.
  const [doc, setDoc] = useState<MarketplaceSkillDocument | null>(null);
  const [docLoading, setDocLoading] = useState(true);
  const [docMissing, setDocMissing] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);

  const fetchSkill = useCallback(() => {
    if (!scope) {
      setError('잘못된 스킬 범위입니다.');
      setLoading(false);
      setDocLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    getMarketplaceSkill(scope, id)
      .then(setSkill)
      .catch((err) => setError(toErrorMessage(err)))
      .finally(() => setLoading(false));

    setDocLoading(true);
    setDocMissing(false);
    setDocError(null);
    getMarketplaceSkillDocument(scope, id)
      .then(setDoc)
      .catch((err) => {
        const msg = err instanceof Error ? err.message : '';
        if (msg.startsWith('404')) setDocMissing(true);
        else setDocError(toErrorMessage(err));
      })
      .finally(() => setDocLoading(false));
  }, [scope, id]);

  useEffect(() => {
    fetchSkill();
  }, [fetchSkill]);

  return (
    <>
      {/* Header bar */}
      <div className="flex items-center gap-[10px] px-3 py-2 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)]">
        <Link
          href={`/marketplace?tab=${backTab}`}
          className="text-[13px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] no-underline"
        >
          &larr; 마켓플레이스
        </Link>
        <span className="text-[var(--color-ink4)]">|</span>
        {loading ? (
          <Skel className="w-40 h-4" />
        ) : skill ? (
          <>
            <span className="font-bold text-[14px]">{skill.name}</span>
            <LifecyclePill state={skill.lifecycle_state} />
          </>
        ) : null}
      </div>

      {error && (
        <div className="px-3 pt-3">
          <ErrorBanner>
            <span>{error}</span>
          </ErrorBanner>
        </div>
      )}

      {loading && (
        <div className="p-[14px] flex flex-col gap-3 max-w-[640px]">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skel key={i} className="h-[28px] w-full" />
          ))}
        </div>
      )}

      {!loading && !error && skill && (
        <div className="p-[14px] flex flex-col gap-3 max-w-[640px]">
          <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[14px] flex flex-col">
            <Field label="이름">{skill.name}</Field>
            <Field label="설명">
              <span className="whitespace-pre-wrap">{skill.description || '-'}</span>
            </Field>
            <Field label="범위">{SCOPE_LABEL[skill.scope]} 스킬</Field>
            <Field label="태그">
              {skill.tags.length > 0 ? (
                <span className="flex flex-wrap gap-1">
                  {skill.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[11px] border border-[var(--color-ink4)] rounded px-[6px] py-0 text-[var(--color-ink3)]"
                    >
                      {tag}
                    </span>
                  ))}
                </span>
              ) : (
                '-'
              )}
            </Field>
            <Field label="상태">
              <LifecyclePill state={skill.lifecycle_state} />
            </Field>
            <Field label="버전">v{skill.version}</Field>
            <Field label="생성일">{new Date(skill.created_at).toLocaleString('ko-KR')}</Field>
            <Field label="수정일">{new Date(skill.updated_at).toLocaleString('ko-KR')}</Field>
            {skill.node_definition_id && <Field label="노드 ID">{skill.node_definition_id}</Field>}
          </div>

          {/* 지침서(SKILL.md) 본문 */}
          <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[14px] flex flex-col gap-2">
            <div className="text-[13px] font-bold text-[var(--color-ink)]">지침서</div>
            {docLoading ? (
              <div className="flex flex-col gap-2">
                <Skel className="h-[14px] w-full" />
                <Skel className="h-[14px] w-[90%]" />
                <Skel className="h-[14px] w-[70%]" />
              </div>
            ) : docError ? (
              <span className="text-[13px] text-red-600">{docError}</span>
            ) : docMissing || !doc ? (
              <span className="text-[13px] text-[var(--color-ink3)]">등록된 지침서가 없습니다.</span>
            ) : (
              <pre className="text-[12px] text-[var(--color-ink)] whitespace-pre-wrap break-words font-mono leading-[1.5] bg-[var(--color-paper)] border border-[var(--color-line-soft)] rounded p-[10px] max-h-[480px] overflow-auto">
                {doc.instructions || '(빈 지침서)'}
              </pre>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default function MarketplaceSkillDetailPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />
      <Suspense
        fallback={
          <div className="p-[14px] flex flex-col gap-3 max-w-[640px]">
            <Skel className="h-[28px] w-full" />
          </div>
        }
      >
        <MarketplaceSkillDetailContent />
      </Suspense>
    </div>
  );
}
