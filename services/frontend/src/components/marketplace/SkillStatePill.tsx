import type { SkillLifecycleState } from '@/lib/api/skillApi';

/** 시안 STATE_PILL — [라벨, 배경, 글자] */
const STATE_PILL: Record<SkillLifecycleState, [label: string, bg: string, fg: string]> = {
  draft: ['초안', '#F1ECE4', '#9C8B7B'],
  review: ['검토중', '#FBE9D8', '#C8860B'],
  approved: ['승인됨', '#E7F6EF', '#10B981'],
  published: ['게시됨', '#EAF1FB', '#3B73C4'],
  archived: ['보관됨', '#F1ECE4', '#A2917F'],
};

export default function SkillStatePill({ state }: { state: SkillLifecycleState }) {
  const [label, bg, fg] = STATE_PILL[state];
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
      style={{ background: bg, color: fg }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: fg }} />
      {label}
    </span>
  );
}
