'use client';

import { useCallback, useEffect, useState } from 'react';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import {
  listReviewQueue,
  approveSkill,
  publishSkill,
  type ReviewQueueItem,
  type SkillScope,
} from '@/lib/api/skillApi';

const SCOPE_LABEL: Record<SkillScope, string> = {
  personal: '개인',
  team: '팀',
  company: '전사',
};

const SCOPE_BADGE: Record<SkillScope, string> = {
  personal: 'bg-paper2 text-ink3',
  team: 'bg-[#EAF1FB] text-[#3B73C4]',
  company: 'bg-[#FBE9D8] text-[#C8860B]',
};

// 리뷰 큐는 3 scope를 합쳐 보여준다 — personal은 owner의 리뷰 요청, team/company는 승격 요청.
const SCOPES: SkillScope[] = ['personal', 'team', 'company'];

function toErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : '';
  if (msg.startsWith('401')) return '로그인이 만료되었습니다.';
  if (msg.startsWith('403') || msg.includes('E-PERM')) return '관리자 권한이 필요합니다.';
  if (msg.startsWith('5')) return '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
  if (msg === 'Failed to fetch' || msg === 'Load failed') return '네트워크 연결을 확인해 주세요.';
  return '리뷰 큐를 불러올 수 없습니다.';
}

export default function AdminApprovalsPage() {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // 3 scope를 병렬 조회해 REVIEW 항목을 한 큐로 합친다(최신순). allSettled로 부분 성공 허용 —
    // 한 scope만 5xx여도 나머지 정상 항목은 보이고, 전부 실패(주로 403)일 때만 에러 화면.
    Promise.allSettled(SCOPES.map((s) => listReviewQueue(s)))
      .then((results) => {
        if (cancelled) return;
        const ok = results
          .filter((r): r is PromiseFulfilledResult<ReviewQueueItem[]> => r.status === 'fulfilled')
          .flatMap((r) => r.value);
        const failed = results.filter((r) => r.status === 'rejected');
        if (ok.length === 0 && failed.length > 0) {
          // 전부 실패 — 동일 Admin 게이트라 권한 실패는 동시발생. 첫 사유로 에러 표시.
          setError(toErrorMessage((failed[0] as PromiseRejectedResult).reason));
          return;
        }
        if (failed.length > 0) showToast('일부 범위를 불러오지 못했습니다. 나머지만 표시합니다.');
        setItems(ok.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fetchKey]);

  // 전이 공통 래퍼 — busy 잠금 → 성공 시 updater + 토스트, 실패 시 토스트.
  const runAction = useCallback(
    async (id: string, fn: () => Promise<void>, apply: () => void, toast: string) => {
      setBusyId(id);
      try {
        await fn();
        apply();
        showToast(toast);
      } catch (err) {
        showToast(toErrorMessage(err));
      } finally {
        setBusyId(null);
      }
    },
    [],
  );

  const setLifecycle = (id: string, lifecycle_state: ReviewQueueItem['lifecycle_state']) =>
    setItems((prev) => prev.map((s) => (s.skill_id === id ? { ...s, lifecycle_state } : s)));

  const remove = (id: string) => setItems((prev) => prev.filter((s) => s.skill_id !== id));

  const onApprove = (item: ReviewQueueItem) =>
    void runAction(
      item.skill_id,
      () => approveSkill(item.skill_id, item.scope, true),
      () => setLifecycle(item.skill_id, 'approved'),
      '승인했습니다. 이제 게시할 수 있습니다.',
    );

  const onReject = (item: ReviewQueueItem) =>
    void runAction(
      item.skill_id,
      () => approveSkill(item.skill_id, item.scope, false),
      () => remove(item.skill_id),
      '반려했습니다. 작성자에게 초안으로 돌아갑니다.',
    );

  const onPublish = (item: ReviewQueueItem) =>
    void runAction(
      item.skill_id,
      () => publishSkill(item.skill_id, item.scope),
      () => remove(item.skill_id),
      '게시했습니다. 마켓플레이스에 공개됩니다.',
    );

  return (
    <div className="max-w-[860px]">
      <div className="border-b border-[var(--color-line-soft)] pb-3 mb-4">
        <h1 className="text-lg font-bold text-[var(--color-ink)]">승인 큐</h1>
        <p className="text-xs text-[var(--color-ink3)] mt-0.5">
          리뷰 요청·승격 요청된 스킬을 승인하고 게시합니다 (개인·팀·전사)
        </p>
      </div>

      {loading ? (
        <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm py-16 flex items-center justify-center">
          <span className="text-sm text-[var(--color-ink4)] font-bold">불러오는 중…</span>
        </div>
      ) : error ? (
        <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm py-12 flex flex-col items-center justify-center gap-3">
          <span className="text-sm font-bold text-[var(--color-danger)]">{error}</span>
          <button
            type="button"
            onClick={() => setFetchKey((k) => k + 1)}
            className="text-xs px-3 py-1.5 rounded-lg border border-[var(--color-line-soft)] bg-white font-bold hover:bg-[var(--color-paper)]"
          >
            다시 시도
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm py-16 flex items-center justify-center">
          <span className="text-sm text-[var(--color-ink4)] font-bold">대기 중인 승인 요청이 없습니다.</span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item) => {
            const busy = busyId === item.skill_id;
            const approved = item.lifecycle_state === 'approved';
            return (
              <div
                key={`${item.scope}:${item.skill_id}`}
                className={[
                  'border border-[var(--color-line-soft)] rounded-2xl shadow-sm bg-white p-4 flex items-center gap-3',
                  approved ? 'ring-1 ring-[var(--color-accent-coral)]/30' : '',
                ].join(' ')}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${SCOPE_BADGE[item.scope]}`}>
                      {SCOPE_LABEL[item.scope]}
                    </span>
                    <span className="font-bold text-[13px] text-[var(--color-ink)] truncate">{item.name}</span>
                    {approved && (
                      <span className="text-[10px] font-bold text-[var(--color-accent)] flex items-center gap-0.5">
                        <Icon name="check" className="w-3 h-3" />
                        승인됨
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-[var(--color-ink3)] truncate mt-0.5">{item.description}</div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {!approved && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onReject(item)}
                      className="px-3 py-1.5 rounded-lg border border-[var(--color-line-soft)] bg-white text-[var(--color-risk-high)] text-[11px] font-bold hover:bg-[var(--color-paper2)] disabled:opacity-60"
                    >
                      반려
                    </button>
                  )}
                  {!approved ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onApprove(item)}
                      className="px-3 py-1.5 rounded-lg border border-[var(--color-line-soft)] bg-white text-[var(--color-accent)] text-[11px] font-bold hover:bg-[var(--color-hl)] disabled:opacity-60 flex items-center gap-1"
                    >
                      <Icon name="check-circle-2" className="w-3.5 h-3.5" />
                      승인
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onPublish(item)}
                      className="px-3.5 py-1.5 rounded-lg bg-[var(--color-accent)] text-white text-[11px] font-bold shadow-sm hover:opacity-90 disabled:opacity-60 flex items-center gap-1"
                    >
                      <Icon name="store" className="w-3.5 h-3.5" />
                      게시
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
