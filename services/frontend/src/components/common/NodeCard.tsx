type RiskLevel = 'low' | 'med' | 'high' | 'restricted';
type NodeStatus = 'running' | 'succeeded' | 'failed' | 'pending';

interface NodeCardProps {
  icon?: string;
  name: string;
  risk?: RiskLevel;
  status?: NodeStatus;
  locked?: boolean;
  meta?: string;
  style?: React.CSSProperties;
}

const RISK_COLORS: Record<RiskLevel, string> = {
  low: 'var(--color-risk-low)',
  med: 'var(--color-risk-med)',
  high: 'var(--color-risk-high)',
  restricted: 'var(--color-risk-restricted)',
};

const STATUS_SHADOWS: Record<NodeStatus, string> = {
  running: '0 0 0 2px var(--color-status-running), 2px 3px 0 var(--color-ink4)',
  succeeded: '0 0 0 2px var(--color-status-succeeded), 2px 3px 0 var(--color-ink4)',
  failed: '0 0 0 2px var(--color-status-failed), 2px 3px 0 var(--color-ink4)',
  pending: '2px 3px 0 var(--color-ink4)',
};

export default function NodeCard({ icon = 'N', name, risk = 'low', status, locked = false, meta, style }: NodeCardProps) {
  const riskColor = RISK_COLORS[risk];
  const boxShadow = status ? STATUS_SHADOWS[status] : '2px 3px 0 var(--color-ink4)';
  const isAnimating = status === 'failed';

  return (
    <div
      className={[
        'relative border-[1.5px] border-[var(--color-ink)] rounded-[5px_9px_5px_9px] pl-3 pr-2 py-[5px]',
        'min-w-[110px] text-[13px] text-[var(--color-ink)] bg-[var(--color-surface)]',
        locked ? 'opacity-70' : '',
        isAnimating ? 'animate-wiggle' : '',
      ].join(' ')}
      style={{ boxShadow, ...style }}
    >
      {/* risk stripe */}
      <span
        className="absolute left-0 top-1 bottom-1 w-1 rounded-r-sm"
        style={{ background: riskColor }}
      />
      <div className="flex items-center gap-1">
        <span
          className="inline-flex items-center justify-center w-[18px] h-[18px] border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper2)] font-mono text-[11px] leading-none flex-shrink-0"
        >
          {icon}
        </span>
        <span className="font-bold leading-none">{name}</span>
        {locked && <span className="ml-1 text-xs">🔒</span>}
      </div>
      {meta && (
        <div className="font-mono text-[10px] text-[var(--color-ink3)] mt-[2px]">{meta}</div>
      )}
    </div>
  );
}
