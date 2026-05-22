'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface SideNavItem {
  label: string;
  href?: string;
  badge?: string | number;
  badgeVariant?: 'default' | 'live';
  onClick?: () => void;
}

interface SideNavProps {
  title: string;
  items: SideNavItem[];
  activeHref?: string;
}

export default function SideNav({ title, items, activeHref }: SideNavProps) {
  const pathname = usePathname();
  return (
    <aside
      className="border-r-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)] p-3 flex-shrink-0"
      style={{ width: 180 }}
    >
      <div className="font-bold text-[13px]">{title}</div>
      <div
        className="my-2"
        style={{ height: '1.5px', background: 'var(--color-ink3)' }}
      />
      <nav className="flex flex-col gap-2 text-[13px]">
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
                    'inline-flex items-center px-[5px] py-0 rounded text-[10px] font-bold border-[1.5px]',
                    item.badgeVariant === 'live'
                      ? 'border-[var(--color-accent)] text-[var(--color-accent)]'
                      : 'border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-paper)]',
                  ].join(' ')}
                >
                  {item.badge}
                </span>
              )}
            </span>
          );

          const baseClass = [
            'flex items-center px-2 py-[4px] rounded border-[1.5px] cursor-pointer',
            isActive
              ? 'bg-[var(--color-hl)] border-[var(--color-ink)] font-bold'
              : 'bg-[var(--color-surface)] border-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
          ].join(' ');

          if (item.href) {
            return (
              <Link key={i} href={item.href} className={`${baseClass} no-underline text-[var(--color-ink)]`}>
                {inner}
              </Link>
            );
          }

          return (
            <button key={i} className={`${baseClass} text-left`} onClick={item.onClick}>
              {inner}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
