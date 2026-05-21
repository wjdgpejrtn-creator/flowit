type RiskLevel = 'low' | 'med' | 'high' | 'restricted';

interface RiskPillProps {
  level?: RiskLevel;
  fill?: boolean;
  label?: string;
}

const COLORS: Record<RiskLevel, string> = {
  low: 'var(--color-risk-low)',
  med: 'var(--color-risk-med)',
  high: 'var(--color-risk-high)',
  restricted: 'var(--color-risk-restricted)',
};

const LABELS: Record<RiskLevel, string> = {
  low: 'Low',
  med: 'Medium',
  high: 'High',
  restricted: 'Restricted',
};

export default function RiskPill({ level = 'low', fill = false, label }: RiskPillProps) {
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
