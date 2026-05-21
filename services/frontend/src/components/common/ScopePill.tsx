import { WorkflowSchema } from '@common/generated';

type Scope = WorkflowSchema['scope'];

interface ScopePillProps {
  scope?: Scope;
}

const CONFIG: Record<Scope, { color: string; label: string }> = {
  private: { color: 'var(--color-scope-private)', label: '🔒 비공개' },
  team:    { color: 'var(--color-scope-team)',    label: '👥 팀' },
  public:  { color: 'var(--color-scope-public)',  label: '🏢 사내' },
};

export default function ScopePill({ scope = 'private' }: ScopePillProps) {
  const { color, label } = CONFIG[scope];
  return (
    <span
      className="inline-flex items-center gap-[3px] text-[11px] px-[6px] py-0 border-[1.5px] rounded-[3px] whitespace-nowrap"
      style={{ borderColor: color, color }}
    >
      {label}
    </span>
  );
}
