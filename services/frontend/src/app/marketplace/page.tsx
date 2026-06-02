'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import Skel from '@/components/common/Skel';
import Icon from '@/components/common/Icon';
import SkillCard, { type CardSkill, type SkillCardActions } from '@/components/marketplace/SkillCard';
import { showToast } from '@/stores/toastStore';
import {
  listPersonalSkills,
  listMarketplaceSkills,
  submitSkill,
  publishSkill,
  promoteSkill,
  deletePersonalSkill,
  archivePersonalSkill,
  restorePersonalSkill,
  addSkillToWorkflow,
  type MarketplaceScope,
} from '@/lib/api/skillApi';

type TabKey = 'personal' | 'team' | 'company';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'personal', label: 'Personal' },
  { key: 'team', label: 'Team' },
  { key: 'company', label: 'Company' },
];

/** 시안 MARKET_HEADERS — [아이콘, 제목, 부제] */
const HEADERS: Record<TabKey, [icon: string, title: string, subtitle: string]> = {
  personal: ['user-cog', '내가 만든 스킬', '초안부터 게시까지, 내 스킬의 상태를 관리하세요.'],
  team: ['users', '동료가 공유한 스킬', '팀에 공유된 스킬을 내 워크플로우에 바로 추가할 수 있습니다.'],
  company: ['building-2', '전사에 공유된 스킬', '회사 전체에 게시된 검증된 스킬 모음입니다.'],
};

function toErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : '';
  if (msg.startsWith('401')) return '로그인이 만료되었습니다.';
  if (msg.startsWith('5')) return '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
  if (msg === 'Failed to fetch' || msg === 'Load failed') return '네트워크 연결을 확인해 주세요.';
  return '스킬 목록을 불러올 수 없습니다.';
}

function matchesQuery(skill: CardSkill, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    skill.name.toLowerCase().includes(needle) ||
    skill.description.toLowerCase().includes(needle) ||
    skill.tags.some((t) => t.toLowerCase().includes(needle))
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
  const initialScope = (searchParams.get('tab') as TabKey) ?? 'personal';

  const [scope, setScope] = useState<TabKey>(
    TABS.some((t) => t.key === initialScope) ? initialScope : 'personal',
  );
  const [items, setItems] = useState<CardSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);
  const [query, setQuery] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [adopted, setAdopted] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    setError(null);
    const fetcher =
      scope === 'personal'
        ? listPersonalSkills()
        : listMarketplaceSkills(scope as MarketplaceScope);
    fetcher
      .then((rows) => setItems(rows as CardSkill[]))
      .catch((err) => setError(toErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [scope, fetchKey]);

  const switchTab = (key: TabKey) => {
    if (key === scope) return;
    setScope(key);
    setQuery('');
    router.replace(`/marketplace?tab=${key}`);
  };

  // 전이 공통 래퍼 — 호출 중 busy 잠금 → 성공 시 updater로 로컬 상태 반영 + 토스트.
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

  const setState = (id: string, lifecycle_state: CardSkill['lifecycle_state']) =>
    setItems((prev) => prev.map((s) => (s.skill_id === id ? { ...s, lifecycle_state } : s)));

  const actions: SkillCardActions = {
    onEdit: (skill) => {
      const qs = new URLSearchParams({
        edit: '1',
        name: skill.name,
        desc: skill.description,
        tags: skill.tags.join(', '),
      });
      showToast(`'${skill.name}' 수정 화면으로 이동했습니다.`);
      router.push(`/skills/builder?${qs.toString()}`);
    },
    onSubmitReview: (id) =>
      void runAction(id, () => submitSkill(id, 'personal'), () => setState(id, 'review'), '검토를 요청했습니다. 관리자 승인을 기다립니다.'),
    onPublishRequest: (id) =>
      void runAction(id, () => publishSkill(id, 'personal'), () => setState(id, 'published'), '마켓플레이스에 게시했습니다. 이제 전사에 공개됩니다.'),
    onDelete: (id) =>
      void runAction(id, () => deletePersonalSkill(id), () => setItems((prev) => prev.filter((s) => s.skill_id !== id)), '스킬을 삭제했습니다.'),
    onArchive: (id) =>
      void runAction(id, () => archivePersonalSkill(id), () => setState(id, 'archived'), '스킬을 보관 처리했습니다.'),
    onRestore: (id) =>
      void runAction(id, () => restorePersonalSkill(id), () => setState(id, 'published'), '보관된 스킬을 복원했습니다.'),
    onAddToWorkflow: (id) =>
      void runAction(
        id,
        () => addSkillToWorkflow(id, scope as MarketplaceScope),
        () => setAdopted((prev) => new Set(prev).add(id)),
        '내 워크플로우에 추가했습니다.',
      ),
    // 승격 요청 — personal→team, team→company. 상위 scope에 REVIEW 스킬을 만들어 관리자 심사로 보낸다.
    // 원본은 그대로 둔다(로컬 상태 변경 없음). 결과는 관리자 승인 페이지(/admin/approvals)에 노출.
    onPromote: (id) =>
      void runAction(
        id,
        () => promoteSkill(id, scope === 'personal' ? 'personal' : 'team'),
        () => {},
        scope === 'personal'
          ? 'Team 스킬로 승격 요청했습니다. 관리자 승인을 기다립니다.'
          : 'Company 스킬로 승격 요청했습니다. 관리자 승인을 기다립니다.',
      ),
  };

  const filtered = useMemo(() => items.filter((s) => matchesQuery(s, query)), [items, query]);
  const [headerIcon, headerTitle, headerSubtitle] = HEADERS[scope];

  const detailHref = (id: string) =>
    scope === 'personal' ? `/skills/${id}` : `/skills/marketplace/${id}?scope=${scope}`;

  return (
    <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-5">
      {/* 탭 + 검색 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-1.5">
          {TABS.map((tab) => (
            <button key={tab.key} type="button" onClick={() => switchTab(tab.key)} className={TAB_CLASS(tab.key === scope)}>
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
      ) : error ? (
        <div className="bg-white border border-line-soft rounded-2xl p-8 text-center shadow-sm flex flex-col items-center gap-2">
          <p className="text-sm font-bold text-danger">{error}</p>
          <button
            type="button"
            onClick={() => setFetchKey((k) => k + 1)}
            className="text-xs px-3 py-1.5 rounded-lg border border-danger/40 bg-white text-danger font-bold hover:bg-danger-soft"
          >
            다시 시도
          </button>
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
              <p className="text-xs text-ink3 font-bold mt-1">스킬빌더에서 맞춤 자동화 스킬을 디자인해보세요!</p>
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
              <SkillCard
                key={skill.skill_id}
                skill={skill}
                variant={scope === 'personal' ? 'personal' : 'marketplace'}
                detailHref={detailHref(skill.skill_id)}
                actions={actions}
                adopted={adopted.has(skill.skill_id)}
                busy={busyId === skill.skill_id}
                // 승격 요청 노출: personal은 게시된 스킬만(→team), team 탭은 전부(→company), company는 없음.
                canPromote={
                  scope === 'personal'
                    ? skill.lifecycle_state === 'published'
                    : scope === 'team'
                }
              />
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
