'use client';

import { useSkillBuilderStore } from '@/stores/skillBuilderStore';
import SkillBuilderChooseCards from './SkillBuilderChooseCards';
import SkillDetailCanvas, { type SkillDetailCanvasProps } from './SkillDetailCanvas';

/**
 * 위저드 풀 레이아웃 — 헤더 + (재료 선택 카드 | 상세 편집 캔버스) + 가이드 사이드.
 *
 * 독립 빌더 페이지(/skills/builder)와 문서 탭 서브뷰가 그대로 소비한다. 채팅에서는
 * 이 조립을 쓰지 않고 SkillBuilderChooseCards(좌측) + SkillDetailCanvas(우측)를 따로
 * 배치한다. 위저드 진행 상태는 skillBuilderStore가 공유한다.
 */

const STEPS = [
  { step: '1', label: '재료 선택', desc: '문서 또는 업종/직무 템플릿' },
  { step: '2', label: '추출 & 검토', desc: 'AI 초안을 검토·편집' },
  { step: '3', label: '검토 & 게시', desc: '게시하면 워크플로우에서 바로 사용' },
  { step: '4', label: '팀/전사 공유', desc: '승격 요청으로 범위 확장(후속)' },
];

export default function SkillBuilderWizard(props: SkillDetailCanvasProps) {
  const phase = useSkillBuilderStore((s) => s.phase);
  const isEdit = useSkillBuilderStore((s) => s.isEdit);
  const editLabel = useSkillBuilderStore((s) => s.editLabel);

  return (
    <>
      <div>
        <h2 className="text-lg font-bold text-ink">{isEdit ? '스킬 수정' : '스킬빌더'}</h2>
        <p className="text-xs text-ink3 font-bold">
          {isEdit
            ? `'${editLabel}' 스킬의 내용을 수정합니다.`
            : '문서가 있으면 문서로, 없으면 업종/직무 템플릿으로 — 검토·편집만으로 나만의 스킬을 만드세요.'}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* 좌: 위저드/폼 */}
        <div className="lg:col-span-9">
          {phase === 'choose' ? <SkillBuilderChooseCards /> : <SkillDetailCanvas {...props} />}
        </div>

        {/* 우: 가이드 */}
        <aside className="lg:col-span-3 self-start">
          <h4 className="text-sm font-bold text-ink uppercase tracking-wider mb-5">스킬 생성 흐름</h4>
          <div className="space-y-6 text-sm">
            {STEPS.map(({ step, label, desc }) => (
              <div key={step} className="flex items-start gap-2.5">
                <span className="w-7 h-7 rounded-full bg-accent text-white flex items-center justify-center text-xs font-black flex-shrink-0">
                  {step}
                </span>
                <div>
                  <p className="font-bold text-ink">{label}</p>
                  <p className="text-ink3 font-bold text-xs leading-relaxed mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </>
  );
}
