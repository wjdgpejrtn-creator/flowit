type StatusType = 'pending' | 'running' | 'succeeded' | 'failed' | 'retrying' | 'paused' | 'cancelled';

interface StatusPillProps {
  status?: StatusType;
  label?: string;
}

const COLORS: Record<StatusType, string> = {
  pending: 'var(--color-status-pending)',
  running: 'var(--color-status-running)',
  succeeded: 'var(--color-status-succeeded)',
  failed: 'var(--color-status-failed)',
  retrying: 'var(--color-status-retrying)',
  paused: 'var(--color-status-paused)',
  cancelled: 'var(--color-status-cancelled)',
};

const LABELS: Record<StatusType, string> = {
  pending: '대기',
  running: '실행 중',
  succeeded: '성공',
  failed: '실패',
  retrying: '재시도',
  paused: '일시정지',
  cancelled: '취소됨',
};

export default function StatusPill({ status = 'pending', label }: StatusPillProps) {
  const color = COLORS[status];
  const isRunning = status === 'running';

  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px] whitespace-nowrap"
      style={{ borderColor: color, color, background: 'var(--color-paper)' }}
    >
      <span
        className={`w-[6px] h-[6px] rounded-full flex-shrink-0 ${isRunning ? 'animate-pulse-dot' : ''}`}
        style={{ background: color }}
      />
      {label ?? LABELS[status]}
    </span>
  );
}
