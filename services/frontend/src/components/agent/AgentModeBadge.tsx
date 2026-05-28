import { AgentMode } from '@common/generated';

const MODE_CONFIG: Record<AgentMode, { label: string; color: string }> = {
  [AgentMode.ONBOARDING]:    { label: '온보딩',      color: 'var(--color-ink3)' },
  [AgentMode.WIZARD]:        { label: '워크플로우',  color: 'var(--color-accent)' },
  [AgentMode.EDIT]:          { label: '편집',        color: 'var(--color-risk-med)' },
  [AgentMode.GENERAL]:       { label: '일반',        color: 'var(--color-ink3)' },
  [AgentMode.SECURITY]:      { label: '보안 검토',   color: 'var(--color-risk-restricted)' },
  [AgentMode.SKILL_BUILDER]: { label: '스킬 빌더',   color: 'var(--color-risk-low)' },
};

interface Props {
  mode: AgentMode;
}

export default function AgentModeBadge({ mode }: Props) {
  const { label, color } = MODE_CONFIG[mode] ?? { label: mode, color: 'var(--color-ink3)' };
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-bold px-[6px] py-[1px] rounded border-[1.5px] whitespace-nowrap"
      style={{ borderColor: color, color }}
    >
      ⬡ {label}
    </span>
  );
}
