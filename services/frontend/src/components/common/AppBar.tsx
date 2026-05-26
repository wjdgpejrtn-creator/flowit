'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore, type Role } from '@/stores/authStore';
import { useAuth } from '@/hooks/useAuth';

interface NavItem {
  label: string;
  href: string;
}

interface AppBarProps {
  dept?: string;
  userName?: string;
  role?: Role;
  notifCount?: number;
  navItems?: NavItem[];
}

const DEFAULT_NAV: NavItem[] = [
  { label: '홈', href: '/' },
  { label: 'AI 채팅', href: '/agent' },
  { label: '워크플로우', href: '/workflows' },
  { label: '마켓플레이스', href: '/marketplace' },
  { label: '설정', href: '/settings' },
];

export default function AppBar({
  dept: deptProp,
  userName: userNameProp,
  role: roleProp,
  notifCount = 0,
  navItems = DEFAULT_NAV,
}: AppBarProps) {
  const store = useAuthStore();
  const { logout } = useAuth();
  const pathname = usePathname();

  const dept = deptProp ?? store.dept ?? '';
  const userName = userNameProp ?? (store.userName || '사용자');
  const role = roleProp ?? store.role;

  return (
    <header
      className="flex items-center gap-[10px] px-3 py-2 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)]"
    >
      {/* Logo */}
      <Link
        href="/"
        className="font-bold text-[15px] px-[6px] py-[2px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] text-[var(--color-ink)] bg-[var(--color-surface)] flex-shrink-0 whitespace-nowrap no-underline"
      >
        ∿ flow
      </Link>

      {/* Nav */}
      <nav className="flex gap-2 flex-1 min-w-0 text-[12px] text-[var(--color-ink3)] overflow-hidden">
        {[...navItems, ...(role === 'Admin' ? [{ label: '관리자', href: '/admin' }] : [])].map((item) => {
          const isCur = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={[
                'px-1 py-[2px] whitespace-nowrap flex-shrink-0 no-underline',
                isCur
                  ? 'text-[var(--color-accent)] border-b-2 border-[var(--color-accent)]'
                  : 'text-[var(--color-ink3)] hover:text-[var(--color-ink)]',
              ].join(' ')}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Dept badge */}
      <span
        className="text-[13px] text-[var(--color-ink3)] border border-[var(--color-ink4)] px-[6px] py-[1px] rounded flex-shrink-0 whitespace-nowrap"
      >
        📍 {dept || '—'}
      </span>

      {/* User badge */}
      <span
        className={[
          'text-[13px] px-2 py-[2px] border-[1.5px] rounded-full flex-shrink-0 whitespace-nowrap',
          role === 'Admin'
            ? 'bg-[var(--color-accent)] border-[var(--color-accent)] text-white'
            : 'bg-[var(--color-paper2)] border-[var(--color-ink)] text-[var(--color-ink)]',
        ].join(' ')}
      >
        {role === 'Admin' && '👑 '}
        {userName} · {role}
      </span>

      {/* Notification */}
      <span className="text-[13px] border border-[var(--color-ink4)] px-[6px] py-[1px] rounded flex-shrink-0">
        🔔 {notifCount}
      </span>

      {/* Logout */}
      <button
        type="button"
        onClick={logout}
        className="text-[13px] border border-[var(--color-ink4)] px-[6px] py-[1px] rounded flex-shrink-0 bg-transparent cursor-pointer text-[var(--color-ink3)] hover:text-[var(--color-ink)]"
      >
        로그아웃
      </button>
    </header>
  );
}
