'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import ScopePill from '@/components/common/ScopePill';
import Skel from '@/components/common/Skel';
import { listWorkflows } from '@/lib/api/workflowApi';
import { useAuthStore } from '@/stores/authStore';
import type { WorkflowSchema } from '@common/generated';

const TABLE_HEAD = ['이름', 'SCOPE', '노드', '상태'];
const ALL_TABS = [
  { label: 'My', key: 'my' },
  { label: 'Team', key: 'team' },
  { label: 'Public', key: 'public' },
] as const;

type TabKey = (typeof ALL_TABS)[number]['key'];

function visibleTabs(role: string): typeof ALL_TABS[number][] {
  if (role === 'company_manager' || role === 'Admin') return [...ALL_TABS];
  if (role === 'team_manager') return ALL_TABS.slice(0, 2);
  return ALL_TABS.slice(0, 1);
}

function toErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : '';
  if (msg.startsWith('401')) return '로그인이 만료되었습니다.';
  if (msg.startsWith('5')) return '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
  if (msg === 'Failed to fetch' || msg === 'Load failed') return '네트워크 연결을 확인해 주세요.';
  return '워크플로우 목록을 불러올 수 없습니다.';
}

function WorkflowListContent() {
  const searchParams = useSearchParams();
  const { role } = useAuthStore();
  const tabs = visibleTabs(role);
  const activeTab = (searchParams.get('tab') as TabKey) ?? 'my';

  const [workflows, setWorkflows] = useState<WorkflowSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listWorkflows()
      .then(setWorkflows)
      .catch((err) => setError(toErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [fetchKey]);

  const filtered =
    activeTab === 'my'
      ? workflows
      : workflows.filter((w) => w.scope === activeTab);

  return (
    <div className="flex-1 flex flex-col gap-[10px] p-[14px]">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        {/* Tabs */}
        <div className="flex gap-2">
          {tabs.map(({ label, key }) => (
            <Link
              key={key}
              href={`/workflows?tab=${key}`}
              className={[
                'text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-2 py-[3px] no-underline',
                key === activeTab
                  ? 'bg-[var(--color-ink)] text-[var(--color-paper)]'
                  : 'bg-[var(--color-surface)] text-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
              ].join(' ')}
            >
              {label}{' '}
              <span className="font-mono text-[11px] opacity-70">
                {key === 'my' ? workflows.length : filtered.length}
              </span>
            </Link>
          ))}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <div className="text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[8px] py-[2px] bg-[var(--color-surface)] text-[var(--color-ink3)]">
            🔍 검색…
          </div>
          <Link href="/agent?mode=edit">
            <Btn primary>＋ 빈 캔버스</Btn>
          </Link>
          <Link href="/agent">
            <Btn>🤖 AI에게 요청</Btn>
          </Link>
        </div>
      </div>

      {/* Table */}
      <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] overflow-hidden">
        {/* Header */}
        <div
          className="flex items-center font-mono text-[11px] text-[var(--color-ink4)] px-[10px] py-[6px] border-b border-[var(--color-ink4)]"
          style={{ background: 'var(--color-paper2)' }}
        >
          <span style={{ flex: 2 }}>{TABLE_HEAD[0]}</span>
          <span style={{ flex: 1 }}>{TABLE_HEAD[1]}</span>
          <span style={{ flex: 0.7 }}>{TABLE_HEAD[2]}</span>
          <span style={{ flex: 0.7 }}>{TABLE_HEAD[3]}</span>
        </div>

        {/* Error */}
        {error && (
          <div className="px-[10px] py-[24px] text-center text-[13px] text-red-600 flex flex-col items-center gap-2">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => setFetchKey((k) => k + 1)}
              className="text-[12px] px-3 py-1 border border-red-300 rounded bg-white text-red-600 hover:bg-red-50 cursor-pointer"
            >
              다시 시도
            </button>
          </div>
        )}

        {/* Skeleton */}
        {loading && !error && (
          <div className="flex flex-col gap-[6px] p-[10px]">
            {[1, 2, 3].map((i) => (
              <Skel key={i} className="h-[32px] w-full" />
            ))}
          </div>
        )}

        {/* Empty */}
        {!loading && !error && filtered.length === 0 && (
          <div className="px-[10px] py-[24px] text-center text-[13px] text-[var(--color-ink3)]">
            워크플로우가 없습니다.
          </div>
        )}

        {/* Rows */}
        {!loading && !error &&
          filtered.map((item, i) => (
            <Link
              key={item.workflow_id}
              href={`/workflows/${item.workflow_id}`}
              className={[
                'flex items-center px-[10px] py-[8px] no-underline text-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
                i < filtered.length - 1 ? 'border-b border-[var(--color-ink4)]' : '',
              ].join(' ')}
            >
              <span className="font-bold" style={{ flex: 2 }}>
                {item.name}
              </span>
              <span style={{ flex: 1 }}>
                <ScopePill scope={item.scope} />
              </span>
              <span className="font-mono text-[11px]" style={{ flex: 0.7 }}>
                {item.nodes.length}개
              </span>
              <span className="text-[11px] text-[var(--color-ink3)]" style={{ flex: 0.7 }}>
                {item.is_draft ? '초안' : '활성'}
              </span>
            </Link>
          ))}
      </div>
    </div>
  );
}

export default function WorkflowListPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />
      <Suspense
        fallback={
          <div className="flex-1 flex flex-col gap-[10px] p-[14px]">
            <Skel className="h-[32px] w-[200px]" />
            <Skel className="h-[200px] w-full" />
          </div>
        }
      >
        <WorkflowListContent />
      </Suspense>
    </div>
  );
}
