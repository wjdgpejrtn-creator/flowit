'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import Skel from '@/components/common/Skel';
import Icon from '@/components/common/Icon';
import SkillCard, { type SkillCardActions } from '@/components/marketplace/SkillCard';
import { showToast } from '@/stores/toastStore';
import {
  listSkills,
  submitReview,
  requestPublish,
  deleteSkill as deleteSkillMock,
  archiveSkill,
  restoreSkill,
  addToWorkflow,
  type MockScope,
  type MockSkill,
} from '@/lib/api/marketplaceMockApi';

const TABS: { key: MockScope; label: string }[] = [
  { key: 'personal', label: 'Personal' },
  { key: 'team', label: 'Team' },
  { key: 'company', label: 'Company' },
];

/** 시안 MARKET_HEADERS — [아이콘, 제목, 부제] */
const HEADERS: Record<MockScope, [icon: string, title: string, subtitle: string]> = {
  personal: ['user-cog', '내가 만든 스킬', '초안부터 게시까지, 내 스킬의 상태를 관리하세요.'],
  team: ['users', '동료가 공유한 스킬', '팀에 공유된 스킬을 내 워크플로우에 바로 추가할 수 있습니다.'],
  company: ['building-2', '전사에 공유된 스킬', '회사 전체에 게시된 검증된 스킬 모음입니다.'],
};

function matchesQuery(skill: MockSkill, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    skill.name.toLowerCase().includes(needle) ||
    skill.desc.toLowerCase().includes(needle) ||
    skill.tags.some((t) => t[0].toLowerCase().includes(needle))
  );
}

function TAB_CLASS(active: boolean): string {
  return [
    'px-4 py-1.5 rounded-lg text-xs font-bold transition-all',
    active ? 'bg-accent text-white shadow-sm' : 'text-ink3 hover:text-ink hover:bg-white/40',
  ].join(' ');
}

function MarketplaceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialScope = (searchParams.get('tab') as MockScope) ?? 'personal';

  const [scope, setScope] = useState<MockScope>(
    TABS.some((t) => t.key === initialScope) ? initialScope : 'personal',
  );
  const [skills, setSkills] = useState<MockSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');

  const reload = useCallback(
    (sc: MockScope, withSpinner = false) => {
      if (withSpinner) setLoading(true);
      return listSkills(sc)
        .then(setSkills)
        .finally(() => setLoading(false));
    },
    [],
  );

  useEffect(() => {
    void reload(scope, true);
  }, [scope, reload]);

  const switchTab = (key: MockScope) => {
    if (key === scope) return;
    setScope(key);
    setQuery('');
    router.replace(`/marketplace?tab=${key}`);
  };

  /** 라이프사이클 mutation 공통 래퍼 — 목 호출 → 재조회 → 토스트 */
  const mutate = (fn: (id: string) => Promise<void>, id: string, toast: string) =>
    fn(id)
      .then(() => reload(scope))
      .then(() => showToast(toast));

  const actions: SkillCardActions = {
    onEdit: (skill) => {
      const tags = skill.tags.map((t) => t[0]).join(', ');
      const qs = new URLSearchParams({ edit: '1', name: skill.name, desc: skill.desc, tags });
      showToast(`'${skill.name}' 수정 화면으로 이동했습니다.`);
      router.push(`/skills/builder?${qs.toString()}`);
    },
    onReviewRequest: (id) => void mutate(submitReview, id, '검토를 요청했습니다. 관리자 승인을 기다립니다.'),
    onPublishRequest: (id) => void mutate(requestPublish, id, '마켓플레이스에 게시했습니다. 이제 전사에 공개됩니다.'),
    onDelete: (id) => void mutate(deleteSkillMock, id, '스킬을 삭제했습니다.'),
    onArchive: (id) => void mutate(archiveSkill, id, '스킬을 보관 처리했습니다.'),
    onRestore: (id) => void mutate(restoreSkill, id, '보관된 스킬을 복원했습니다.'),
    onAddToWorkflow: (id) => void mutate(addToWorkflow, id, '내 워크플로우에 추가했습니다.'),
  };

  const filtered = skills.filter((s) => matchesQuery(s, query));
  const [headerIcon, headerTitle, headerSubtitle] = HEADERS[scope];

  return (
    <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-5">
      {/* 탭 + 검색 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-1.5">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => switchTab(tab.key)}
              className={TAB_CLASS(tab.key === scope)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="스킬 검색..."
            aria-label="스킬 검색"
            className="w-48 pl-8 pr-3 py-1.5 text-xs rounded-lg border border-line-soft focus:outline-none focus:border-accent-coral bg-white text-ink font-bold"
          />
          <Icon name="search" className="w-3.5 h-3.5 text-ink3 absolute left-2.5 top-2" />
        </div>
      </div>

      {/* 콘텐츠 */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white border border-line-soft rounded-2xl p-4 shadow-sm flex flex-col gap-2">
              <Skel h={16} w="64px" />
              <Skel h={18} w="140px" />
              <Skel h={28} />
              <Skel h={14} w="100px" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-line-soft rounded-2xl p-8 text-center shadow-sm">
          {query ? (
            <>
              <p className="text-sm font-bold text-ink">&apos;{query}&apos; 검색 결과가 없습니다.</p>
              <p className="text-xs text-ink3 font-bold mt-1">다른 키워드로 검색해보세요.</p>
            </>
          ) : (
            <>
              <p className="text-sm font-bold text-ink">등록된 스킬이 없습니다.</p>
              <p className="text-xs text-ink3 font-bold mt-1">
                스킬빌더에서 맞춤 자동화 스킬을 디자인해보세요!
              </p>
              <button
                type="button"
                onClick={() => router.push('/skills/builder')}
                className="mt-4 px-4 py-2 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3"
              >
                스킬 빌더 바로가기
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Icon name={headerIcon} className="w-4 h-4 text-accent-coral" />
              <h3 className="text-sm font-bold text-ink">{headerTitle}</h3>
              <span className="text-[11px] text-ink4 font-bold hidden md:inline">— {headerSubtitle}</span>
            </div>
            {scope === 'personal' && (
              <button
                type="button"
                onClick={() => router.push('/skills/builder')}
                className="px-3 py-1.5 rounded-lg bg-accent text-white text-[11px] font-bold shadow-sm hover:bg-accent3 transition-all flex items-center gap-1"
              >
                <Icon name="plus" className="w-3.5 h-3.5" />
                새 스킬
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((skill) => (
              <SkillCard key={skill.id} skill={skill} actions={actions} />
            ))}
          </div>
        </div>
      )}
    </main>
  );
}

export default function MarketplacePage() {
  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />
      <Suspense
        fallback={
          <div className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-5">
            <Skel h={32} w="200px" />
            <Skel h={200} />
          </div>
        }
      >
        <MarketplaceContent />
      </Suspense>
      <footer className="bg-white border-t border-line-soft py-6 px-6 mt-12 text-center text-xs text-ink3 font-bold">
        <p className="text-[10px] text-ink3 leading-relaxed">
          © 2026 Flowit Corp. 모든 자동화 프로세스는 실시간으로 격리 분석 처리됩니다.
        </p>
      </footer>
    </div>
  );
}
