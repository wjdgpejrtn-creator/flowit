import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import RiskPill from '@/components/common/RiskPill';
import StatusPill from '@/components/common/StatusPill';
import WarnBanner from '@/components/common/WarnBanner';

const RECENT_WORKFLOWS = [
  { name: '주간 회의록 요약', status: 'running' as const, risk: 'high' as const },
  { name: '견적 PDF 분류', status: 'succeeded' as const, risk: 'med' as const },
];

const QUICK_CHIPS = ['📈 광고 리포트', '📄 PDF 처리', '💬 Slack 알림', '📅 캘린더 동기화'];

export default function DashboardPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* Hero area */}
      <div
        className="px-7 pt-[34px] pb-[18px] border-b-[1.5px] border-[var(--color-ink3)]"
        style={{ background: 'var(--color-paper2)' }}
      >
        <h1 className="font-bold text-[30px] tracking-[-0.02em] mb-[6px]">
          무엇을 <span className="bg-[var(--color-hl)] px-1">자동화</span>할까요?
        </h1>
        <p className="text-[var(--color-ink3)] text-[14px] mb-[14px]">
          김주임님 · 마케팅팀 · 자연어로 그냥 말씀해주세요.
        </p>

        {/* Large input */}
        <Link
          href="/agent"
          className="flex items-center gap-3 border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[18px] py-[14px] text-[22px] bg-[var(--color-surface)] no-underline"
          style={{ boxShadow: '3px 4px 0 var(--color-ink)' }}
        >
          <span className="text-[var(--color-ink4)] flex-1 text-[18px]">
            매주 월요일 9시에 광고 시트…
          </span>
          <span className="font-mono text-[var(--color-ink3)] text-[12px]">⌘ + K</span>
        </Link>

        {/* Quick chips */}
        <div className="flex gap-2 mt-3 flex-wrap">
          {QUICK_CHIPS.map((chip) => (
            <span
              key={chip}
              className="text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[8px] py-[3px] bg-[var(--color-surface)] cursor-pointer hover:bg-[var(--color-paper2)]"
            >
              {chip}
            </span>
          ))}
          <span className="text-[13px] text-[var(--color-ink4)] px-[8px] py-[3px] cursor-pointer">
            + 더 보기
          </span>
        </div>
      </div>

      {/* Bottom 2-column content */}
      <div className="flex-1 grid grid-cols-2 gap-3 p-5">
        {/* Left: 이어서 작업 */}
        <div>
          <div className="text-[13px] text-[var(--color-ink3)] mb-[6px]">이어서 작업</div>
          <div className="flex flex-col gap-2">
            {RECENT_WORKFLOWS.map((wf) => (
              <Link
                key={wf.name}
                href="/workflows"
                className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[6px] bg-[var(--color-surface)] no-underline hover:bg-[var(--color-paper2)]"
              >
                <span className="flex items-center gap-2">
                  <RiskPill level={wf.risk} />
                  <span className="font-bold text-[var(--color-ink)]">{wf.name}</span>
                </span>
                <StatusPill status={wf.status} />
              </Link>
            ))}
          </div>
        </div>

        {/* Right: 알림 */}
        <div>
          <div className="text-[13px] text-[var(--color-ink3)] mb-[6px]">알림</div>
          <div className="flex flex-col gap-2">
            <WarnBanner small>⏰ 자격증명 만료 임박 · Slack</WarnBanner>
            <Link
              href="/agent"
              className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[6px] bg-[var(--color-surface)] no-underline hover:bg-[var(--color-paper2)]"
            >
              <span className="text-[var(--color-ink)]">💬 미응답 질문 2건</span>
              <span className="font-mono text-[13px] text-[var(--color-ink3)]">이어가기</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
