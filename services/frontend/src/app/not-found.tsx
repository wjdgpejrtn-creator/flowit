import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4" style={{ background: 'var(--color-paper)' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 48, color: 'var(--color-ink4)' }}>404</div>
      <p style={{ color: 'var(--color-ink3)', fontFamily: 'var(--font-pretendard)' }}>페이지를 찾을 수 없습니다.</p>
      <Link
        href="/"
        className="px-4 py-2 text-sm font-bold border border-[var(--color-ink)] rounded hover:bg-[var(--color-hl)] transition-colors"
        style={{ color: 'var(--color-ink)' }}
      >
        홈으로 돌아가기
      </Link>
    </div>
  );
}
