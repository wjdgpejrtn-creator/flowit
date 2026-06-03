import Icon from '@/components/common/Icon';

const CREDENTIALS = [
  { name: 'Slack · marketing-bot', dept: '마케팅', calls: '144', expires: '12.4일', urgency: undefined },
  { name: 'Drive · sales',          dept: '영업',   calls: '37',  expires: '5일',     urgency: 'med' as const },
  { name: 'Gmail · hr-bot',         dept: '인사',   calls: '12',  expires: '21일',    urgency: undefined },
  { name: 'Notion · OKR',           dept: '마케팅', calls: '89',  expires: '7일',     urgency: 'med' as const },
  { name: 'ERP · finance',          dept: '재무',   calls: '3',   expires: '-2일',    urgency: 'high' as const },
];

const FILTERS = ['전체 (24)', '활성', '만료 임박', '미사용'];

const URGENCY_COLOR: Record<string, string> = {
  med:  'var(--color-risk-med)',
  high: 'var(--color-danger)',
};

export default function AdminCredentialsPage() {
  return (
    <div className="max-w-[1200px]">
      <div className="border-b border-[var(--color-line-soft)] pb-3 mb-4">
        <h1 className="text-lg font-bold text-[var(--color-ink)]">자격증명 감사</h1>
        <p className="text-xs text-[var(--color-ink3)] mt-0.5">Credential Injection 추적 · 부서·노드별</p>
      </div>

      {/* 필터 알약 탭 */}
      <div className="flex gap-1 mb-4">
        {FILTERS.map((label, i) => (
          <button
            key={label}
            type="button"
            className={[
              'rounded-lg px-4 py-1.5 text-xs font-bold transition-colors',
              i === 0
                ? 'bg-[var(--color-accent)] text-white shadow-sm'
                : 'text-[var(--color-ink3)] hover:text-[var(--color-ink)] hover:bg-white/40',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 테이블 */}
      <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm overflow-hidden">
        {/* 헤더 */}
        <div className="grid grid-cols-12 px-4 py-3 border-b border-[var(--color-line-soft)] text-[11px] font-bold uppercase tracking-wide text-[var(--color-ink3)]">
          <span className="col-span-4">이름</span>
          <span className="col-span-2">부서</span>
          <span className="col-span-2">24h 사용</span>
          <span className="col-span-2">만료</span>
          <span className="col-span-2" />
        </div>

        <div className="divide-y divide-[var(--color-line-soft)]">
          {CREDENTIALS.map((cred) => (
            <div
              key={cred.name}
              className="grid grid-cols-12 px-4 py-4 items-center hover:bg-[var(--color-hl)]/40 transition-colors"
            >
              <span className="col-span-4 font-bold text-[13px] text-[var(--color-ink)]">{cred.name}</span>
              <span className="col-span-2 text-[13px] text-[var(--color-ink2)]">{cred.dept}</span>
              <span className="col-span-2 font-mono text-[12px] text-[var(--color-ink3)]">{cred.calls}</span>
              <span
                className="col-span-2 text-[13px] font-bold flex items-center gap-1"
                style={{ color: cred.urgency ? URGENCY_COLOR[cred.urgency] : 'var(--color-ink)' }}
              >
                {cred.expires}
                {cred.urgency === 'med' && <Icon name="alert-triangle" className="w-3.5 h-3.5" />}
                {cred.urgency === 'high' && <Icon name="x" className="w-3.5 h-3.5" />}
              </span>
              <span className="col-span-2 flex justify-end">
                <button
                  type="button"
                  className="px-3 py-1.5 rounded-lg border border-[var(--color-line-soft)] bg-white text-[var(--color-ink)] text-xs font-bold hover:bg-[var(--color-paper)] transition-colors"
                >
                  로그
                </button>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
