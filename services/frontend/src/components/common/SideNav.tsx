'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Icon from '@/components/common/Icon';

interface SideNavItem {
  label: string;
  href?: string;
  badge?: string | number;
  badgeVariant?: 'default' | 'live';
  onClick?: () => void;
}

interface SideNavProps {
  title: string;
  /** kebab-case lucide 아이콘 이름 (예: "crown") — 타이틀 좌측에 accent 색으로 표시 */
  icon?: string;
  items: SideNavItem[];
  activeHref?: string;
}

export default function SideNav({ title, icon, items, activeHref }: SideNavProps) {
  const pathname = usePathname();
  return (
    <aside className="flex-shrink-0 p-4" style={{ width: 220 }}>
      <div className="flex items-center gap-2 px-2 mb-3">
        {icon && <Icon name={icon} className="w-4 h-4 text-[var(--color-accent)]" />}
        <span className="font-bold text-[13px] text-[var(--color-ink)]">{title}</span>
      </div>

      <nav className="bg-[var(--color-paper2)]/40 rounded-2xl p-3 space-y-1">
        {items.map((item, i) => {
          const isActive = activeHref
            ? item.href === activeHref
            : item.href === pathname;

          const inner = (
            <span className="flex items-center justify-between gap-1 w-full">
              <span>{item.label}</span>
              {item.badge !== undefined && (
                <span
                  className={[
                    'inline-flex items-center rounded px-1.5 text-[10px] font-bold leading-tight',
                    item.badgeVariant === 'live'
                      ? 'border border-[var(--color-accent-coral)] text-[var(--color-accent-coral)]'
                      : isActive
                        ? 'bg-white/25 text-white'
                        : 'bg-[var(--color-accent)] text-white',
                  ].join(' ')}
                >
                  {item.badge}
                </span>
              )}
            </span>
          );

          const baseClass = [
            'block w-full text-left px-4 py-2.5 rounded-xl text-xs font-bold transition-colors',
            isActive
              ? 'bg-[var(--color-accent)] text-white shadow-sm'
              : 'text-[var(--color-ink3)] hover:text-[var(--color-ink)] hover:bg-white',
          ].join(' ');

          if (item.href) {
            return (
              <Link key={i} href={item.href} className={`${baseClass} no-underline`}>
                {inner}
              </Link>
            );
          }

          return (
            <button key={i} type="button" className={baseClass} onClick={item.onClick}>
              {inner}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
