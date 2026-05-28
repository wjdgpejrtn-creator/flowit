import { ExecutionStatus } from '@common/generated';

const CONFIG: Record<string, { label: string; color: string }> = {
  [ExecutionStatus.PENDING]:   { label: '대기',      color: 'var(--color-status-pending)' },
  [ExecutionStatus.RUNNING]:   { label: '실행 중',   color: 'var(--color-status-running)' },
  [ExecutionStatus.PAUSED]:    { label: '일시정지',  color: 'var(--color-status-paused)' },
  [ExecutionStatus.COMPLETED]: { label: '완료',      color: 'var(--color-status-completed)' },
  [ExecutionStatus.FAILED]:    { label: '실패',      color: 'var(--color-status-failed)' },
  [ExecutionStatus.CANCELLED]: { label: '취소됨',   color: 'var(--color-status-cancelled)' },
};

interface Props {
  status: string;
  label?: string;
}

export default function ExecutionStatusBadge({ status, label }: Props) {
  const { label: defaultLabel, color } = CONFIG[status] ?? { label: status, color: 'var(--color-ink4)' };
  const isRunning = status === ExecutionStatus.RUNNING;

  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px] whitespace-nowrap"
      style={{ borderColor: color, color, background: 'var(--color-paper)' }}
    >
      <span
        className={`w-[6px] h-[6px] rounded-full flex-shrink-0 ${isRunning ? 'animate-pulse-dot' : ''}`}
        style={{ background: color }}
      />
      {label ?? defaultLabel}
    </span>
  );
}
