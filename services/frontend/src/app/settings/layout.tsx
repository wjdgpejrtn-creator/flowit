import AppBar from '@/components/common/AppBar';
import SideNav from '@/components/common/SideNav';

const NAV_ITEMS = [
  { label: '프로필', href: '/settings' },
  { label: '통합', href: '/settings/integrations' },
  { label: '알림', href: '/settings/notifications' },
  { label: '보안', href: '/settings/security' },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />
      <div className="flex-1 flex min-h-0">
        <SideNav title="설정" items={NAV_ITEMS} />
        <div className="flex-1 overflow-auto p-[14px]">
          {children}
        </div>
      </div>
    </div>
  );
}
