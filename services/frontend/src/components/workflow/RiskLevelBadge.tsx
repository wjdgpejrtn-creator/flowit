import { RiskLevel } from '@common/generated';

const CONFIG: Record<RiskLevel, { label: string; color: string }> = {
  [RiskLevel.LOW]:        { label: 'Low',        color: 'var(--color-risk-low)' },
  [RiskLevel.MEDIUM]:     { label: 'Medium',     color: 'var(--color-risk-med)' },
  [RiskLevel.HIGH]:       { label: 'High',       color: 'var(--color-risk-high)' },
  [RiskLevel.RESTRICTED]: { label: 'Restricted', color: 'var(--color-risk-restricted)' },
};

interface Props {
  level: RiskLevel;
  showLabel?: boolean;
}

export default function RiskLevelBadge({ level, showLabel = true }: Props) {
  const { label, color } = CONFIG[level] ?? { label: level, color: 'var(--color-ink4)' };
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px] whitespace-nowrap"
      style={{ borderColor: color, color }}
    >
      <span className="w-[6px] h-[6px] rounded-full flex-shrink-0" style={{ background: color }} />
      {showLabel && label}
    </span>
  );
}
