'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import Skel from '@/components/common/Skel';
import Icon from '@/components/common/Icon';
import { listWorkflows } from '@/lib/api/workflowApi';
import { useAuthStore } from '@/stores/authStore';
import type { WorkflowSchema } from '@common/generated';

const ALL_TABS = [
  { label: 'My', key: 'my' },
  { label: 'Team', key: 'team' },
  { label: 'Public', key: 'public' },
] as const;

type TabKey = (typeof ALL_TABS)[number]['key'];

function visibleTabs(role: string): (typeof ALL_TABS)[number][] {
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

/** 시안 scope 칩 — private→Personal, team→Team, public→Company */
function ScopeChip({ scope }: { scope?: WorkflowSchema['scope'] }) {
  const map: Record<string, [string, string]> = {
    private: ['Personal', 'bg-paper2 text-ink3'],
    team: ['Team', 'bg-hl text-accent'],
    public: ['Company', 'bg-[#EAF1FB] text-[#3B73C4]'],
  };
  const [label, cls] = map[scope ?? 'private'] ?? map.private;
  return <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${cls}`}>{label}</span>;
}

function StatusChip({ isDraft }: { isDraft?: boolean }) {
  const color = isDraft ? '#9C8B7B' : '#10B981';
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-bold"
      style={{ color, borderColor: color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
      {isDraft ? '초안' : '활성'}
    </span>
  );
}

function WorkflowListContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { role } = useAuthStore();
  const tabs = visibleTabs(role);
  const activeTab = (searchParams.get('tab') as TabKey) ?? 'my';

  const [workflows, setWorkflows] = useState<WorkflowSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);
  const [query, setQuery] = useState('');

  useEffect(() => {
    setLoading(true);
    setError(null);
    listWorkflows()
      .then(setWorkflows)
      .catch((err) => setError(toErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [fetchKey]);

  const filtered = useMemo(() => {
    const byScope = activeTab === 'my' ? workflows : workflows.filter((w) => w.scope === activeTab);
    const q = query.trim().toLowerCase();
    return q ? byScope.filter((w) => w.name.toLowerCase().includes(q)) : byScope;
  }, [workflows, activeTab, query]);

  return (
    <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-4">
      {/* 헤더/툴바 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <span className="px-3 py-1.5 rounded-xl bg-accent text-white text-xs font-bold">
            워크플로우
          </span>
          <p className="text-xs text-ink3 font-bold">
            내 워크플로우를 체계적으로 관리하고 자동화를 구성합니다.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {tabs.length > 1 &&
            tabs.map(({ label, key }) => (
              <button
                key={key}
                type="button"
                onClick={() => router.replace(`/workflows?tab=${key}`)}
                className={[
                  'px-3 py-1.5 rounded-lg text-xs font-bold transition-all',
                  key === activeTab ? 'bg-accent text-white shadow-sm' : 'text-ink3 hover:text-ink hover:bg-paper2/50',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="워크플로우 검색..."
              aria-label="워크플로우 검색"
              className="w-48 pl-8 pr-3 py-1.5 text-xs rounded-lg border border-line-soft focus:outline-none focus:border-accent-coral bg-white text-ink font-bold"
            />
            <Icon name="search" className="w-3.5 h-3.5 text-ink3 absolute left-2.5 top-2" />
          </div>
          <button
            type="button"
            onClick={() => router.push('/agent?mode=edit')}
            className="px-3 py-1.5 rounded-lg border border-line-soft text-xs font-bold text-ink hover:bg-paper flex items-center space-x-1"
          >
            <Icon name="plus" className="w-3.5 h-3.5" />
            <span>빈 캔버스</span>
          </button>
          <button
            type="button"
            onClick={() => router.push('/agent')}
            className="px-3 py-1.5 rounded-lg bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 flex items-center space-x-1"
          >
            <Icon name="sparkles" className="w-3.5 h-3.5" />
            <span>AI에게 요청</span>
          </button>
        </div>
      </div>

      {/* 테이블 */}
      <div className="bg-white border border-line-soft rounded-2xl overflow-hidden shadow-sm">
        <div className="grid grid-cols-12 px-4 py-2.5 border-b border-line-soft text-[11px] font-bold text-ink3 uppercase tracking-wide">
          <div className="col-span-5">이름</div>
          <div className="col-span-2">Scope</div>
          <div className="col-span-2">노드</div>
          <div className="col-span-2">상태</div>
          <div className="col-span-1 text-right">동작</div>
        </div>

        {error ? (
          <div className="px-4 py-8 text-center flex flex-col items-center gap-2">
            <span className="text-xs font-bold text-danger">{error}</span>
            <button
              type="button"
              onClick={() => setFetchKey((k) => k + 1)}
              className="text-xs px-3 py-1 border border-danger/40 rounded-lg bg-white text-danger font-bold hover:bg-danger-soft"
            >
              다시 시도
            </button>
          </div>
        ) : loading ? (
          <div className="flex flex-col gap-1.5 p-4">
            {[1, 2, 3].map((i) => (
              <Skel key={i} h={36} className="rounded-lg" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <p className="text-xs font-bold text-ink3">워크플로우가 없습니다.</p>
            <p className="text-xs text-ink3 font-bold mt-1">
              상단의 &apos;AI에게 요청&apos;으로 새로운 자동화 흐름을 만들 수 있어요.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-line-soft">
            {filtered.map((item) => (
              <button
                key={item.workflow_id}
                type="button"
                onClick={() => router.push(`/workflows/${item.workflow_id}`)}
                className="w-full text-left grid grid-cols-12 px-4 py-4 items-center font-bold hover:bg-hl/40 transition-all cursor-pointer text-[13px]"
              >
                <div className="col-span-5 flex items-center space-x-2">
                  <Icon name="workflow" className="w-4 h-4 text-accent flex-shrink-0" />
                  <span className="text-ink truncate">{item.name}</span>
                </div>
                <div className="col-span-2">
                  <ScopeChip scope={item.scope} />
                </div>
                <div className="col-span-2 text-ink3">{item.nodes.length}개</div>
                <div className="col-span-2">
                  <StatusChip isDraft={item.is_draft} />
                </div>
                <div className="col-span-1 text-right">
                  <Icon name="more-horizontal" className="w-4 h-4 text-ink3 inline" />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function WorkflowListPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />
      <Suspense
        fallback={
          <div className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-4">
            <Skel h={32} w="200px" />
            <Skel h={200} />
          </div>
        }
      >
        <WorkflowListContent />
      </Suspense>
    </div>
  );
}
