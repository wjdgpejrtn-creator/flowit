'use client';

import { ButtonHTMLAttributes } from 'react';

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  primary?: boolean;
  ghost?: boolean;
  danger?: boolean;
  lg?: boolean;
}

export default function Btn({ primary, ghost, danger, lg, children, className = '', ...props }: BtnProps) {
  const base = [
    'inline-flex items-center gap-1 font-bold border-[1.5px] cursor-pointer whitespace-nowrap transition-colors',
    'rounded-[5px_10px_5px_10px]',
    lg ? 'text-base px-[18px] py-[6px]' : 'text-[13px] px-3 py-[4px]',
  ];

  let variant: string;
  if (primary) {
    variant = [
      'bg-[var(--color-accent)] text-white border-[var(--color-accent)]',
      'shadow-[2px_3px_0_var(--color-accent3)]',
      'hover:bg-[var(--color-accent2)] hover:border-[var(--color-accent2)]',
      'active:bg-[var(--color-accent3)]',
    ].join(' ');
  } else if (ghost) {
    variant = [
      'text-[var(--color-ink3)] bg-transparent border-[var(--color-ink)]',
      'hover:bg-[var(--color-paper2)]',
    ].join(' ');
  } else if (danger) {
    variant = [
      'text-[var(--color-risk-restricted)] border-[var(--color-risk-restricted)] bg-[var(--color-surface)]',
      'hover:bg-red-50',
    ].join(' ');
  } else {
    variant = [
      'text-[var(--color-ink)] bg-[var(--color-surface)] border-[var(--color-ink)]',
      'hover:bg-[var(--color-hl)]',
    ].join(' ');
  }

  return (
    <button className={[...base, variant, className].join(' ')} {...props}>
      {children}
    </button>
  );
}
