import AppBar from '@/components/common/AppBar';
import SideNav from '@/components/common/SideNav';

const NAV_ITEMS = [
  { label: '대시보드',        href: '/admin' },
  { label: '자격증명',        href: '/admin/credentials' },
  { label: '승인 큐',         href: '/admin/approvals', badge: 5 },
  { label: '거버넌스 라이브',  href: '/admin/live', badge: 'LIVE', badgeVariant: 'live' as const },
  { label: '부서별 통계',     href: '/admin/stats' },
  { label: 'LLM 사용량',      href: '/admin/usage' },
  { label: '감사 로그',       href: '/admin/audit' },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />
      <div className="flex-1 flex min-h-0">
        <SideNav title="거버넌스" icon="crown" items={NAV_ITEMS} />
        <div className="flex-1 overflow-auto p-4 md:p-6">
          {children}
        </div>
      </div>
    </div>
  );
}
