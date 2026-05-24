'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import ScopePill from '@/components/common/ScopePill';
import Skel from '@/components/common/Skel';
import { listWorkflows } from '@/lib/api/workflowApi';
import type { WorkflowSchema } from '@common/generated';

const TABLE_HEAD = ['이름', 'SCOPE', '노드', '상태', '수정'];
const TABS = [
  { label: 'My', key: 'my' },
  { label: 'Team', key: 'team' },
  { label: 'Public', key: 'public' },
] as const;

function WorkflowListContent() {
  const searchParams = useSearchParams();
  const activeTab = searchParams.get('tab') ?? 'my';

  const [workflows, setWorkflows] = useState<WorkflowSchema[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listWorkflows()
      .then(setWorkflows)
      .catch(() => setWorkflows([]))
      .finally(() => setLoading(false));
  }, []);

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
          {TABS.map(({ label, key }) => (
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
          <span style={{ flex: 1 }}>{TABLE_HEAD[4]}</span>
        </div>

        {/* Skeleton */}
        {loading && (
          <div className="flex flex-col gap-[6px] p-[10px]">
            {[1, 2, 3].map((i) => (
              <Skel key={i} className="h-[32px] w-full" />
            ))}
          </div>
        )}

        {/* Empty */}
        {!loading && filtered.length === 0 && (
          <div className="px-[10px] py-[24px] text-center text-[13px] text-[var(--color-ink3)]">
            워크플로우가 없습니다.
          </div>
        )}

        {/* Rows */}
        {!loading &&
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
              <span className="text-[13px] text-[var(--color-ink3)]" style={{ flex: 1 }}>
                —
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
