'use client';

import Icon from '@/components/common/Icon';
import SkillStatePill from './SkillStatePill';
import type { MockSkill } from '@/lib/api/marketplaceMockApi';

export interface SkillCardActions {
  onEdit: (skill: MockSkill) => void;
  onReviewRequest: (id: string) => void;
  onPublishRequest: (id: string) => void;
  onDelete: (id: string) => void;
  onArchive: (id: string) => void;
  onRestore: (id: string) => void;
  onAddToWorkflow: (id: string) => void;
}

/** 시안 skillActions() 포팅 — 상태별 버튼 위계 */
function CardActions({ skill, actions }: { skill: MockSkill; actions: SkillCardActions }) {
  if (skill.state === 'archived') {
    return (
      <div className="mt-3 pt-3 border-t border-line-soft flex items-center justify-between">
        <span className="text-[10px] text-ink4 font-bold flex items-center gap-1">
          <Icon name="archive" className="w-3.5 h-3.5" />
          보관된 스킬
        </span>
        <button
          type="button"
          onClick={() => actions.onRestore(skill.id)}
          className="px-3 py-1.5 rounded-lg border border-line-soft bg-white text-ink text-[11px] font-bold hover:bg-paper2 transition-all flex items-center gap-1"
        >
          <Icon name="rotate-ccw" className="w-3.5 h-3.5" />
          복원
        </button>
      </div>
    );
  }

  if (skill.state === 'draft') {
    return (
      <div className="mt-3 pt-3 border-t border-line-soft flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => actions.onEdit(skill)}
            className="text-[11px] font-bold text-ink3 hover:text-ink flex items-center gap-1 transition-all"
          >
            <Icon name="pencil" className="w-3.5 h-3.5" />
            수정
          </button>
          <button
            type="button"
            onClick={() => actions.onDelete(skill.id)}
            className="text-[11px] font-bold flex items-center gap-1 transition-all text-danger hover:opacity-70"
          >
            <Icon name="trash-2" className="w-3.5 h-3.5" />
            삭제
          </button>
        </div>
        <button
          type="button"
          onClick={() => actions.onReviewRequest(skill.id)}
          className="px-3 py-1.5 rounded-lg border border-line-soft bg-white text-accent text-[11px] font-bold hover:bg-hl transition-all flex items-center gap-1"
        >
          <Icon name="send" className="w-3.5 h-3.5" />
          리뷰요청
        </button>
      </div>
    );
  }

  if (skill.state === 'review') {
    return (
      <div className="mt-3 pt-3 border-t border-line-soft">
        <button
          type="button"
          disabled
          className="w-full py-2 rounded-lg bg-paper2 text-ink4 text-[11px] font-bold flex items-center justify-center gap-1.5 cursor-not-allowed"
        >
          <Icon name="clock" className="w-3.5 h-3.5" />
          검토 대기중
        </button>
      </div>
    );
  }

  if (skill.state === 'approved') {
    return (
      <div className="mt-3 pt-3 border-t border-line-soft flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => actions.onEdit(skill)}
          className="text-[11px] font-bold text-ink3 hover:text-ink flex items-center gap-1 transition-all"
        >
          <Icon name="pencil" className="w-3.5 h-3.5" />
          수정
        </button>
        <button
          type="button"
          onClick={() => actions.onPublishRequest(skill.id)}
          className="px-3.5 py-2 rounded-lg bg-accent text-white text-[11px] font-bold shadow-sm hover:bg-accent3 transition-all flex items-center gap-1.5"
        >
          <Icon name="store" className="w-3.5 h-3.5" />
          등록 요청
        </button>
      </div>
    );
  }

  // published — 내 소유
  if (skill.owner) {
    return (
      <div className="mt-3 pt-3 border-t border-line-soft flex items-center justify-between">
        <span className="text-[10px] text-ink4 font-bold flex items-center gap-1">
          <Icon name="bar-chart-2" className="w-3.5 h-3.5" />
          사용 {skill.uses || '-'}
        </span>
        <button
          type="button"
          onClick={() => actions.onArchive(skill.id)}
          className="px-3 py-1.5 rounded-lg border border-line-soft bg-white text-ink text-[11px] font-bold hover:bg-paper2 transition-all flex items-center gap-1"
        >
          <Icon name="archive" className="w-3.5 h-3.5" />
          보관
        </button>
      </div>
    );
  }

  // published — 남의 스킬, 이미 도입
  if (skill.added) {
    return (
      <div className="mt-3 pt-3 border-t border-line-soft">
        <button
          type="button"
          disabled
          className="w-full py-2.5 rounded-xl bg-paper2 text-ink3 text-xs font-bold flex items-center justify-center gap-1.5 cursor-default"
        >
          <Icon name="check" className="w-4 h-4" />
          도입 완료
        </button>
      </div>
    );
  }

  // published — 남의 스킬, 미도입
  return (
    <div className="mt-3 pt-3 border-t border-line-soft">
      <button
        type="button"
        onClick={() => actions.onAddToWorkflow(skill.id)}
        className="w-full py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 transition-all flex items-center justify-center gap-1.5"
      >
        <Icon name="plus" className="w-4 h-4" />
        내 워크플로우에 넣기
      </button>
    </div>
  );
}

export default function SkillCard({
  skill,
  actions,
}: {
  skill: MockSkill;
  actions: SkillCardActions;
}) {
  return (
    <div
      className={[
        'bg-white border border-line-soft rounded-2xl p-4 shadow-sm flex flex-col',
        skill.state === 'approved' ? 'ring-1 ring-accent-coral/30' : '',
      ].join(' ')}
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex gap-1.5">
          {skill.tags.map(([label, bg, fg]) => (
            <span
              key={label}
              className="px-2 py-0.5 rounded-full text-[10px] font-bold"
              style={{ background: bg, color: fg }}
            >
              {label}
            </span>
          ))}
        </div>
        <SkillStatePill state={skill.state} />
      </div>

      <p className="text-sm font-bold text-ink">{skill.name}</p>
      <p className="text-[11px] text-ink3 font-bold mt-1 leading-relaxed flex-1">{skill.desc}</p>

      <div className="flex items-center gap-2 mt-3 text-[10px] text-ink4 font-bold">
        <span className="font-mono">{skill.version}</span>
        <span>·</span>
        <span>{skill.meta}</span>
      </div>

      <CardActions skill={skill} actions={actions} />
    </div>
  );
}
