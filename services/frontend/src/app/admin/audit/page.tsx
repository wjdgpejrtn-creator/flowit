export default function AdminAuditPage() {
  return (
    <div className="max-w-[1100px]">
      <div className="border-b border-[var(--color-line-soft)] pb-3 mb-4">
        <h1 className="text-lg font-bold text-[var(--color-ink)]">감사 로그</h1>
        <p className="text-xs text-[var(--color-ink3)] mt-0.5">전체 워크플로우 실행 · 자격증명 접근 이력</p>
      </div>
      <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm py-20 flex items-center justify-center">
        <span className="text-sm text-[var(--color-ink4)] font-bold">— 준비 중 —</span>
      </div>
    </div>
  );
}
