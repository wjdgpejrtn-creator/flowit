export default function AdminUsagePage() {
  return (
    <div className="max-w-[1100px]">
      <div className="border-b border-[var(--color-line-soft)] pb-3 mb-4">
        <h1 className="text-lg font-bold text-[var(--color-ink)]">LLM 사용량</h1>
        <p className="text-xs text-[var(--color-ink3)] mt-0.5">모델별 토큰 소비 및 비용 추적</p>
      </div>
      <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm py-20 flex items-center justify-center">
        <span className="text-sm text-[var(--color-ink4)] font-bold">— 준비 중 —</span>
      </div>
    </div>
  );
}
