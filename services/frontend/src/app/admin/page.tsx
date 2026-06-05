export default function AdminDashboardPage() {
  return (
    <div className="max-w-[1100px]">
      <div className="border-b border-[var(--color-line-soft)] pb-3 mb-4">
        <h1 className="text-lg font-bold text-[var(--color-ink)]">거버넌스 대시보드</h1>
        <p className="text-xs text-[var(--color-ink3)] mt-0.5">조직 전체 자격증명 · 승인 큐 · 감사 현황</p>
      </div>
      <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm py-20 flex items-center justify-center">
        <span className="text-sm text-[var(--color-ink4)] font-bold">— 준비 중 —</span>
      </div>
    </div>
  );
}
