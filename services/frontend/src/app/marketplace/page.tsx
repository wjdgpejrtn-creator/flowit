import AppBar from '@/components/common/AppBar';
import RiskPill from '@/components/common/RiskPill';
import ScopePill from '@/components/common/ScopePill';
import Btn from '@/components/common/Btn';
import { RiskLevel } from '@common/generated';

type SkillItem = {
  name: string;
  cat: string;
  risk: RiskLevel;
  scope: 'private' | 'team' | 'public';
  users: number;
  official?: boolean;
};

const SKILLS: SkillItem[] = [
  { name: '주간 OKR 요약',      cat: '리포트',  risk: RiskLevel.LOW,        scope: 'team',   users: 12, official: false },
  { name: 'CS 분류기',          cat: 'AI 분류', risk: RiskLevel.MEDIUM,     scope: 'team',   users: 34, official: true  },
  { name: '예산 알림',          cat: '알림',    risk: RiskLevel.HIGH,       scope: 'team',   users: 7,  official: false },
  { name: '견적서 자동 응답',    cat: '문서',    risk: RiskLevel.MEDIUM,     scope: 'public', users: 22, official: true  },
  { name: '회의록 요약봇',       cat: 'AI 분류', risk: RiskLevel.LOW,        scope: 'public', users: 58, official: true  },
  { name: '인사 온보딩 자동화',  cat: '인사',    risk: RiskLevel.LOW,        scope: 'team',   users: 9,  official: false },
];

const TABS = ['🪴 Personal', '👥 Team', '🏢 Company'] as const;

export default function MarketplacePage() {
  const activeTab = '👥 Team';

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      <div className="flex-1 flex flex-col gap-[10px] p-[14px]">
        {/* Tabs */}
        <div className="flex gap-2">
          {TABS.map((tab) => (
            <button
              key={tab}
              className={[
                'text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-2 py-[3px]',
                tab === activeTab
                  ? 'bg-[var(--color-ink)] text-[var(--color-paper)]'
                  : 'bg-[var(--color-surface)] text-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
              ].join(' ')}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Search bar + count */}
        <div className="flex items-center justify-between">
          <div className="text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[8px] py-[2px] bg-[var(--color-surface)] text-[var(--color-ink3)]">
            🔍 스킬 검색…
          </div>
          <span className="text-[13px] text-[var(--color-ink3)]">마케팅팀 · 23개</span>
        </div>

        {/* Skill card grid */}
        <div className="grid grid-cols-3 gap-[10px]">
          {SKILLS.map((sk) => (
            <div
              key={sk.name}
              className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[10px] flex flex-col gap-2"
            >
              {/* Top row */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] border border-[var(--color-ink4)] rounded px-[6px] py-0 text-[var(--color-ink3)]">
                  {sk.cat}
                </span>
                <RiskPill level={sk.risk} />
              </div>

              {/* Name */}
              <div className="font-bold text-[15px] text-[var(--color-ink)]">{sk.name}</div>

              {/* Scope + official */}
              <div className="flex items-center gap-2">
                <ScopePill scope={sk.scope} />
                {sk.official && (
                  <span className="text-[10px] border-[1.5px] border-[var(--color-accent)] text-[var(--color-accent)] rounded px-[5px] py-0 font-bold">
                    공식 ✓
                  </span>
                )}
              </div>

              {/* Usage + CTA */}
              <div className="text-[13px] text-[var(--color-ink3)]">사용 {sk.users}명</div>
              <Btn primary>＋ 내 워크플로우에 추가</Btn>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
