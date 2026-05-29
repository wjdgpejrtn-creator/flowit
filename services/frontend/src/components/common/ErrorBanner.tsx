import { ReactNode } from 'react';

interface ErrorBannerProps {
  children: ReactNode;
  small?: boolean;
}

export default function ErrorBanner({ children, small }: ErrorBannerProps) {
  return (
    <div
      className={[
        'flex items-center gap-2 font-medium rounded border-[1.5px] px-[10px] py-[6px]',
        small ? 'text-[11px]' : 'text-[13px]',
      ].join(' ')}
      style={{
        background: '#FEE2E2',
        borderColor: 'var(--color-risk-restricted)',
        color: 'var(--color-risk-restricted)',
      }}
    >
      {children}
    </div>
  );
}
