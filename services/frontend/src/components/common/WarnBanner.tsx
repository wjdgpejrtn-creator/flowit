import { ReactNode } from 'react';

interface WarnBannerProps {
  children: ReactNode;
  small?: boolean;
}

export default function WarnBanner({ children, small }: WarnBannerProps) {
  return (
    <div
      className={[
        'flex items-center gap-2 font-medium rounded border-[1.5px] px-[10px] py-[6px]',
        small ? 'text-[11px]' : 'text-[13px]',
      ].join(' ')}
      style={{
        background: '#FEF3C7',
        borderColor: 'var(--color-risk-high)',
        color: 'var(--color-risk-high)',
      }}
    >
      {children}
    </div>
  );
}
