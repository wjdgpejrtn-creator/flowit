'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import RiskPill from '@/components/common/RiskPill';
import ScopePill from '@/components/common/ScopePill';
import Btn from '@/components/common/Btn';
import Skel from '@/components/common/Skel';
import { RiskLevel } from '@common/generated';
import { listPersonalSkills, type PersonalSkill, type SkillLifecycleState } from '@/lib/api/skillApi';

/* ── Lifecycle 상태 pill ── */

const LIFECYCLE_CONFIG: Record<SkillLifecycleState, { color: string; label: string }> = {
  draft:     { color: 'var(--color-ink4)',    label: '초안' },
  review:    { color: 'var(--color-risk-med)', label: '검토 중' },
  approved:  { color: 'var(--color-risk-low)', label: '승인됨' },
  published: { color: 'var(--color-accent)',   label: '게시됨' },
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

/* ── Team/Company 더미 데이터 (기존) ── */

type SkillItem = {
  name: string;
  cat: string;
  risk: RiskLevel;
  scope: 'private' | 'team' | 'public';
  users: number;
  official?: boolean;
};

const DUMMY_SKILLS: SkillItem[] = [
  { name: '주간 OKR 요약',      cat: '리포트',  risk: RiskLevel.LOW,        scope: 'team',   users: 12, official: false },
  { name: 'CS 분류기',          cat: 'AI 분류', risk: RiskLevel.MEDIUM,     scope: 'team',   users: 34, official: true  },
  { name: '예산 알림',          cat: '알림',    risk: RiskLevel.HIGH,       scope: 'team',   users: 7,  official: false },
  { name: '견적서 자동 응답',    cat: '문서',    risk: RiskLevel.MEDIUM,     scope: 'public', users: 22, official: true  },
  { name: '회의록 요약봇',       cat: 'AI 분류', risk: RiskLevel.LOW,        scope: 'public', users: 58, official: true  },
  { name: '인사 온보딩 자동화',  cat: '인사',    risk: RiskLevel.LOW,        scope: 'team',   users: 9,  official: false },
];

/* ── 에러 메시지 분류 ── */

function toErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : '';
  if (msg.startsWith('401')) return '로그인이 만료되었습니다.';
  if (msg.startsWith('5')) return '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
  if (msg === 'Failed to fetch' || msg === 'Load failed') return '네트워크 연결을 확인해 주세요.';
  return '스킬 목록을 불러올 수 없습니다.';
}

/* ── Tabs ── */

const TABS = [
  { key: 'personal', label: 'Personal' },
  { key: 'team',     label: 'Team' },
  { key: 'company',  label: 'Company' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

/* ── Personal 탭 콘텐츠 ── */

function PersonalTabContent() {
  const [skills, setSkills] = useState<PersonalSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listPersonalSkills()
      .then(setSkills)
      .catch((err) => setError(toErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [fetchKey]);

  if (loading) {
    return (
      <div className="grid grid-cols-3 gap-[10px]">
        {[1, 2, 3].map((i) => (
          <div key={i} className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[10px] flex flex-col gap-2">
            <Skel className="h-[18px] w-[60px]" />
            <Skel className="h-[20px] w-[120px]" />
            <Skel className="h-[14px] w-full" />
            <Skel className="h-[14px] w-[80px]" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] px-[10px] py-[24px] text-center text-[13px] text-red-600 flex flex-col items-center gap-2">
        <span>{error}</span>
        <button
          type="button"
          onClick={() => setFetchKey((k) => k + 1)}
          className="text-[12px] px-3 py-1 border border-red-300 rounded bg-white text-red-600 hover:bg-red-50 cursor-pointer"
        >
          다시 시도
        </button>
      </div>
    );
  }

  if (skills.length === 0) {
    return (
      <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] px-[10px] py-[24px] text-center text-[13px] text-[var(--color-ink3)]">
        등록된 개인 스킬이 없습니다.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-[10px]">
      {skills.map((sk) => (
        <Link
          key={sk.skill_id}
          href={`/skills/${sk.skill_id}`}
          className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[10px] flex flex-col gap-2 no-underline text-[var(--color-ink)] hover:bg-[var(--color-paper2)] transition-colors"
        >
          <div className="flex items-center justify-between">
            {sk.tags.length > 0 && (
              <span className="text-[11px] border border-[var(--color-ink4)] rounded px-[6px] py-0 text-[var(--color-ink3)]">
                {sk.tags[0]}
              </span>
            )}
            <LifecyclePill state={sk.lifecycle_state} />
          </div>

          <div className="font-bold text-[15px]">{sk.name}</div>

          <div className="text-[12px] text-[var(--color-ink3)] line-clamp-2">
            {sk.description}
          </div>

          <div className="flex items-center justify-between text-[11px] text-[var(--color-ink4)]">
            <span>v{sk.version}</span>
            <span>{new Date(sk.updated_at).toLocaleDateString('ko-KR')}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}

/* ── Team/Company 더미 카드 그리드 ── */

function DummySkillGrid() {
  return (
    <div className="grid grid-cols-3 gap-[10px]">
      {DUMMY_SKILLS.map((sk) => (
        <div
          key={sk.name}
          className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[10px] flex flex-col gap-2"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] border border-[var(--color-ink4)] rounded px-[6px] py-0 text-[var(--color-ink3)]">
              {sk.cat}
            </span>
            <RiskPill level={sk.risk} />
          </div>
          <div className="font-bold text-[15px] text-[var(--color-ink)]">{sk.name}</div>
          <div className="flex items-center gap-2">
            <ScopePill scope={sk.scope} />
            {sk.official && (
              <span className="text-[10px] border-[1.5px] border-[var(--color-accent)] text-[var(--color-accent)] rounded px-[5px] py-0 font-bold">
                공식
              </span>
            )}
          </div>
          <div className="text-[13px] text-[var(--color-ink3)]">사용 {sk.users}명</div>
          <Btn primary>+ 내 워크플로우에 추가</Btn>
        </div>
      ))}
    </div>
  );
}

/* ── 메인 콘텐츠 ── */

function MarketplaceContent() {
  const searchParams = useSearchParams();
  const activeTab = (searchParams.get('tab') as TabKey) ?? 'personal';

  return (
    <div className="flex-1 flex flex-col gap-[10px] p-[14px]">
      {/* Tabs */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {TABS.map((tab) => (
            <Link
              key={tab.key}
              href={`/marketplace?tab=${tab.key}`}
              className={[
                'text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-2 py-[3px] no-underline',
                tab.key === activeTab
                  ? 'bg-[var(--color-ink)] text-[var(--color-paper)]'
                  : 'bg-[var(--color-surface)] text-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
              ].join(' ')}
            >
              {tab.label}
            </Link>
          ))}
        </div>

        <div className="text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[8px] py-[2px] bg-[var(--color-surface)] text-[var(--color-ink3)]">
          스킬 검색…
        </div>
      </div>

      {/* Tab content */}
      {activeTab === 'personal' ? <PersonalTabContent /> : <DummySkillGrid />}
    </div>
  );
}

export default function MarketplacePage() {
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
        <MarketplaceContent />
      </Suspense>
    </div>
  );
}
