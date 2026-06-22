import type { Metadata } from 'next';
import './globals.css';
import AuthInitializer from '@/components/common/AuthInitializer';
import Toaster from '@/components/common/Toaster';

export const metadata: Metadata = {
  title: '똑똑한 업무 자동화, 플로잇 (Flowit)',
  description: '사내 AI 자동화 스킬 마켓플레이스',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="antialiased selection:bg-accent-coral/20 selection:text-accent">
        <AuthInitializer />
        {children}
        <Toaster />
      </body>
    </html>
  );
}
