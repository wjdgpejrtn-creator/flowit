import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '∿ flow — 워크플로우 자동화',
  description: '사내 AI 자동화 스킬 마켓플레이스',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
