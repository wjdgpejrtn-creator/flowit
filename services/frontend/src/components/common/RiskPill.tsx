import { RiskLevel } from '@common/generated';

interface RiskPillProps {
  level?: RiskLevel;
  fill?: boolean;
  label?: string;
}

const COLORS: Record<RiskLevel, string> = {
  [RiskLevel.LOW]: 'var(--color-risk-low)',
  [RiskLevel.MEDIUM]: 'var(--color-risk-med)',
  [RiskLevel.HIGH]: 'var(--color-risk-high)',
  [RiskLevel.RESTRICTED]: 'var(--color-risk-restricted)',
};

const LABELS: Record<RiskLevel, string> = {
  [RiskLevel.LOW]: 'Low',
  [RiskLevel.MEDIUM]: 'Medium',
  [RiskLevel.HIGH]: 'High',
  [RiskLevel.RESTRICTED]: 'Restricted',
};

export default function RiskPill({ level = RiskLevel.LOW, fill = false, label }: RiskPillProps) {
  const color = COLORS[level];
  return (
    <span
      className="inline-flex items-center gap-[3px] text-[11px] font-semibold px-[7px] py-[1px] rounded-full border-[1.5px] whitespace-nowrap"
      style={{
        borderColor: color,
        color: fill ? 'var(--color-paper)' : color,
        background: fill ? color : 'var(--color-paper)',
      }}
    >
      <span
        className="w-[6px] h-[6px] rounded-full flex-shrink-0"
        style={{ background: fill ? 'var(--color-paper)' : color }}
      />
      {label ?? LABELS[level]}
    </span>
  );
}
