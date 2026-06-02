'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useAuthStore, type Role } from '@/stores/authStore';
import { useAuth } from '@/hooks/useAuth';
import { showToast } from '@/stores/toastStore';
import Icon from './Icon';

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
  { label: '문서', href: '/documents' },
  { label: '스킬빌더', href: '/skills/builder' },
  { label: '마켓플레이스', href: '/marketplace' },
  { label: '설정', href: '/settings' },
];

const NAV_BASE =
  'px-3.5 py-1.5 rounded-xl transition-all flex-shrink-0 no-underline';
const NAV_ACTIVE = 'text-white bg-accent shadow-sm';
const NAV_IDLE = 'text-ink3 hover:text-ink hover:bg-paper2/50';

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
  const [logoFailed, setLogoFailed] = useState(false);

  const dept = deptProp ?? store.dept ?? '';
  const userName = userNameProp ?? (store.userName || '사용자');
  const role = roleProp ?? store.role;

  const items = [
    ...navItems,
    ...(role === 'Admin' ? [{ label: '관리자', href: '/admin' }] : []),
  ];

  const isActive = (href: string) =>
    pathname === href || (href !== '/' && pathname.startsWith(href));

  return (
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-line-soft px-4 md:px-6 py-3 flex items-center justify-between overflow-x-auto whitespace-nowrap shadow-sm">
      <div className="flex items-center space-x-6 md:space-x-8 flex-shrink-0">
        {/* 로고 (가로형 워드마크) */}
        <Link href="/" className="flex items-center space-x-3 group flex-shrink-0 no-underline">
          <div className="h-8 flex items-center justify-center relative flex-shrink-0">
            {logoFailed ? (
              <span className="flex items-center space-x-1 text-accent font-black text-lg">
                <span>🦦 Flowit</span>
              </span>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src="/images/flowit-wordmark-v2.png"
                alt="Flowit"
                className="h-7 md:h-8 object-contain flex-shrink-0"
                onError={() => setLogoFailed(true)}
              />
            )}
          </div>
        </Link>

        {/* 탭 네비게이션 — App Router 라우트로 이동, 시안의 탭 전환 UX 유지 */}
        <nav className="hidden md:flex space-x-1 text-sm font-semibold flex-shrink-0 whitespace-nowrap">
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={[NAV_BASE, isActive(item.href) ? NAV_ACTIVE : NAV_IDLE].join(' ')}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-1.5 text-xs flex-shrink-0 whitespace-nowrap">
        {/* 부서 라벨 배지 (PR #277 — user_id(UUID) 대신 부서 라벨 노출) */}
        <span className="hidden xl:flex items-center gap-1.5 text-ink4 font-bold flex-shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
          {dept || '—'}
        </span>

        {/* 알림 */}
        <button
          type="button"
          onClick={() =>
            showToast(notifCount > 0 ? '새 알림이 있습니다.' : '새 알림이 없습니다.')
          }
          className="relative p-2 rounded-lg text-ink3 hover:bg-paper hover:text-ink transition-all flex-shrink-0"
          aria-label="알림"
        >
          <Icon name="bell" className="w-[18px] h-[18px]" />
          {notifCount > 0 && (
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-accent-coral" />
          )}
        </button>

        {/* 사용자 */}
        <div className="flex items-center gap-2 pl-1 flex-shrink-0">
          <span className="font-bold text-ink flex-shrink-0">{userName}</span>
        </div>

        <span className="w-px h-4 bg-line-soft mx-1 flex-shrink-0" />

        {/* 로그아웃 */}
        <button
          type="button"
          onClick={() => void logout()}
          className="px-2.5 py-1.5 rounded-lg text-ink3 hover:text-accent font-bold transition-all flex-shrink-0 bg-transparent cursor-pointer"
        >
          로그아웃
        </button>
      </div>
    </header>
  );
}
