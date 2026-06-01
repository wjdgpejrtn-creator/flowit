'use client';

import Link from 'next/link';
import Icon from '@/components/common/Icon';
import SkillStatePill from './SkillStatePill';
import type { SkillLifecycleState } from '@/lib/api/skillApi';

/** 마켓플레이스 카드가 쓰는 정규화 뷰모델 — PersonalSkill·MarketplaceSkill 공통 필드. */
export interface CardSkill {
  skill_id: string;
  name: string;
  description: string;
  lifecycle_state: SkillLifecycleState;
  tags: string[];
  version: string;
  updated_at: string;
}

export interface SkillCardActions {
  onEdit: (skill: CardSkill) => void;
  onSubmitReview: (id: string) => void;
  onPublishRequest: (id: string) => void;
  onDelete: (id: string) => void;
  onArchive: (id: string) => void;
  onRestore: (id: string) => void;
  onAddToWorkflow: (id: string) => void;
}

// 태그 색 — 실 API tags는 색 정보가 없어 인덱스로 Flowit 팔레트를 순환(시안의 컬러 태그 느낌 유지).
const TAG_PALETTE: [bg: string, fg: string][] = [
  ['#EAF1FB', '#3B73C4'],
  ['#FBE9D8', '#C8860B'],
  ['#E7F6EF', '#10B981'],
  ['#F1ECE4', '#9C8B7B'],
];

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('ko-KR');
}

function PersonalActions({ skill, actions, busy }: { skill: CardSkill; actions: SkillCardActions; busy: boolean }) {
  if (skill.lifecycle_state === 'archived') {
    return (
      <div className="mt-3 pt-3 border-t border-line-soft flex items-center justify-between">
        <span className="text-[10px] text-ink4 font-bold flex items-center gap-1">
          <Icon name="archive" className="w-3.5 h-3.5" />
          보관된 스킬
        </span>
        <button
          type="button"
          disabled={busy}
          onClick={() => actions.onRestore(skill.skill_id)}
          className="px-3 py-1.5 rounded-lg border border-line-soft bg-white text-ink text-[11px] font-bold hover:bg-paper2 transition-all flex items-center gap-1 disabled:opacity-60"
        >
          <Icon name="rotate-ccw" className="w-3.5 h-3.5" />
          복원
        </button>
      </div>
    );
  }

  if (skill.lifecycle_state === 'draft') {
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
            disabled={busy}
            onClick={() => actions.onDelete(skill.skill_id)}
            className="text-[11px] font-bold flex items-center gap-1 transition-all text-danger hover:opacity-70 disabled:opacity-60"
          >
            <Icon name="trash-2" className="w-3.5 h-3.5" />
            삭제
          </button>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => actions.onSubmitReview(skill.skill_id)}
          className="px-3 py-1.5 rounded-lg border border-line-soft bg-white text-accent text-[11px] font-bold hover:bg-hl transition-all flex items-center gap-1 disabled:opacity-60"
        >
          <Icon name="send" className="w-3.5 h-3.5" />
          리뷰요청
        </button>
      </div>
    );
  }

  if (skill.lifecycle_state === 'review') {
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

  if (skill.lifecycle_state === 'approved') {
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
          disabled={busy}
          onClick={() => actions.onPublishRequest(skill.skill_id)}
          className="px-3.5 py-2 rounded-lg bg-accent text-white text-[11px] font-bold shadow-sm hover:bg-accent3 transition-all flex items-center gap-1.5 disabled:opacity-60"
        >
          <Icon name="store" className="w-3.5 h-3.5" />
          등록 요청
        </button>
      </div>
    );
  }

  // published — 내 소유(Personal 탭은 모두 내 스킬)
  return (
    <div className="mt-3 pt-3 border-t border-line-soft flex items-center justify-between">
      <span className="text-[10px] text-ink4 font-bold flex items-center gap-1">
        <Icon name="check-circle-2" className="w-3.5 h-3.5" />
        게시됨
      </span>
      <button
        type="button"
        disabled={busy}
        onClick={() => actions.onArchive(skill.skill_id)}
        className="px-3 py-1.5 rounded-lg border border-line-soft bg-white text-ink text-[11px] font-bold hover:bg-paper2 transition-all flex items-center gap-1 disabled:opacity-60"
      >
        <Icon name="archive" className="w-3.5 h-3.5" />
        보관
      </button>
    </div>
  );
}

function MarketplaceActions({
  skill,
  actions,
  adopted,
  busy,
}: {
  skill: CardSkill;
  actions: SkillCardActions;
  adopted: boolean;
  busy: boolean;
}) {
  if (adopted) {
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
  return (
    <div className="mt-3 pt-3 border-t border-line-soft">
      <button
        type="button"
        disabled={busy}
        onClick={() => actions.onAddToWorkflow(skill.skill_id)}
        className="w-full py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3 transition-all flex items-center justify-center gap-1.5 disabled:opacity-60"
      >
        <Icon name="plus" className="w-4 h-4" />
        내 워크플로우에 넣기
      </button>
    </div>
  );
}

export default function SkillCard({
  skill,
  variant,
  detailHref,
  actions,
  adopted = false,
  busy = false,
}: {
  skill: CardSkill;
  variant: 'personal' | 'marketplace';
  detailHref: string;
  actions: SkillCardActions;
  adopted?: boolean;
  busy?: boolean;
}) {
  return (
    <div
      className={[
        'bg-white border border-line-soft rounded-2xl p-4 shadow-sm flex flex-col',
        skill.lifecycle_state === 'approved' ? 'ring-1 ring-accent-coral/30' : '',
      ].join(' ')}
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex gap-1.5 flex-wrap">
          {skill.tags.slice(0, 3).map((tag, i) => {
            const [bg, fg] = TAG_PALETTE[i % TAG_PALETTE.length];
            return (
              <span key={tag} className="px-2 py-0.5 rounded-full text-[10px] font-bold" style={{ background: bg, color: fg }}>
                {tag}
              </span>
            );
          })}
        </div>
        <SkillStatePill state={skill.lifecycle_state} />
      </div>

      {/* 제목·설명 → 상세 페이지 링크 (카드↔상세 재연결) */}
      <Link href={detailHref} className="no-underline group">
        <p className="text-sm font-bold text-ink group-hover:text-accent transition-colors">{skill.name}</p>
        <p className="text-[11px] text-ink3 font-bold mt-1 leading-relaxed">{skill.description}</p>
      </Link>

      <div className="flex items-center gap-2 mt-3 text-[10px] text-ink4 font-bold">
        <span className="font-mono">v{skill.version}</span>
        {fmtDate(skill.updated_at) && (
          <>
            <span>·</span>
            <span>{fmtDate(skill.updated_at)}</span>
          </>
        )}
      </div>

      {variant === 'personal' ? (
        <PersonalActions skill={skill} actions={actions} busy={busy} />
      ) : (
        <MarketplaceActions skill={skill} actions={actions} adopted={adopted} busy={busy} />
      )}
    </div>
  );
}
