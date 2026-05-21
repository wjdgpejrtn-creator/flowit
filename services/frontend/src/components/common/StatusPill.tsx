import { ExecutionStatus, NodeExecutionState } from '@common/generated';

type StatusType = `${ExecutionStatus}` | NodeExecutionState['status'];

interface StatusPillProps {
  status?: StatusType;
  label?: string;
}

const COLORS: Record<StatusType, string> = {
  pending:   'var(--color-status-pending)',
  running:   'var(--color-status-running)',
  paused:    'var(--color-status-paused)',
  completed: 'var(--color-status-completed)',
  failed:    'var(--color-status-failed)',
  cancelled: 'var(--color-status-cancelled)',
  succeeded: 'var(--color-status-succeeded)',
  retrying:  'var(--color-status-retrying)',
};

const LABELS: Record<StatusType, string> = {
  pending:   '대기',
  running:   '실행 중',
  paused:    '일시정지',
  completed: '완료',
  failed:    '실패',
  cancelled: '취소됨',
  succeeded: '성공',
  retrying:  '재시도',
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
