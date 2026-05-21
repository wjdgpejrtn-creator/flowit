import AppBar from '@/components/common/AppBar';
import SideNav from '@/components/common/SideNav';
import Btn from '@/components/common/Btn';
import RiskPill from '@/components/common/RiskPill';

const CREDENTIALS = [
  { name: 'Slack · marketing-bot', dept: '마케팅', calls: '144', expires: '12.4일',  risk: undefined },
  { name: 'Drive · sales',          dept: '영업',   calls: '37',  expires: '5일 ⚠',  risk: 'med' as const },
  { name: 'Gmail · hr-bot',         dept: '인사',   calls: '12',  expires: '21일',    risk: undefined },
  { name: 'Notion · OKR',           dept: '마케팅', calls: '89',  expires: '7일',     risk: 'med' as const },
  { name: 'ERP · finance',          dept: '재무',   calls: '3',   expires: '-2일 ✕',  risk: 'high' as const },
];

const NAV_ITEMS = [
  { label: '대시보드',    href: '/admin' },
  { label: '자격증명 ⏵', href: '/admin/credentials' },
  { label: '승인 큐',    href: '/admin/approvals', badge: 5 },
  { label: '거버넌스 라이브', href: '/admin/live', badge: 'LIVE', badgeVariant: 'live' as const },
  { label: '부서별 통계', href: '/admin/stats' },
  { label: 'LLM 사용량', href: '/admin/usage' },
  { label: '감사 로그',  href: '/admin/audit' },
];

const RISK_COLOR: Record<string, string> = {
  med:  'var(--color-risk-med)',
  high: 'var(--color-risk-high)',
};

export default function AdminPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar role="Admin" userName="이팀장" dept="인사팀" />

      <div className="flex-1 flex min-h-0">
        <SideNav title="👑 거버넌스" items={NAV_ITEMS} activeHref="/admin/credentials" />

        {/* Main content */}
        <div className="flex-1 overflow-auto p-[14px]">
          <div className="font-bold text-[16px] mb-[2px]">자격증명 감사</div>
          <div className="text-[13px] text-[var(--color-ink3)] mb-3">
            CredentialInjection 추적 · 부서·노드별
          </div>

          {/* Filter pills */}
          <div className="flex gap-2 mb-3">
            {['전체 (24)', '활성', '만료 임박', '미사용'].map((label, i) => (
              <button
                key={label}
                className={[
                  'text-[11px] border-[1.5px] border-[var(--color-ink)] rounded px-[8px] py-[3px]',
                  i === 0
                    ? 'bg-[var(--color-ink)] text-[var(--color-paper)]'
                    : 'bg-[var(--color-surface)] text-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Table */}
          <div
            className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] overflow-hidden"
          >
            {/* Header */}
            <div
              className="flex items-center font-mono text-[11px] text-[var(--color-ink4)] px-[10px] py-[6px] border-b border-[var(--color-ink4)]"
              style={{ background: 'var(--color-paper2)' }}
            >
              <span style={{ flex: 2 }}>이름</span>
              <span style={{ flex: 1 }}>부서</span>
              <span style={{ flex: 1 }}>24h 사용</span>
              <span style={{ flex: 1 }}>만료</span>
              <span style={{ flex: 0.7 }} />
            </div>

            {CREDENTIALS.map((cred, i) => (
              <div
                key={cred.name}
                className={[
                  'flex items-center px-[10px] py-[8px]',
                  i < CREDENTIALS.length - 1 ? 'border-b border-[var(--color-ink4)]' : '',
                ].join(' ')}
              >
                <span className="font-bold text-[13px]" style={{ flex: 2 }}>{cred.name}</span>
                <span className="text-[13px]" style={{ flex: 1 }}>{cred.dept}</span>
                <span className="font-mono text-[11px]" style={{ flex: 1 }}>{cred.calls}</span>
                <span
                  className="text-[13px]"
                  style={{
                    flex: 1,
                    color: cred.risk ? RISK_COLOR[cred.risk] : 'var(--color-ink)',
                  }}
                >
                  {cred.expires}
                </span>
                <span style={{ flex: 0.7 }}>
                  <Btn ghost>로그</Btn>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
