import { RiskLevel } from '@common/generated';

/**
 * 설정 패널용 위험도 표시 — 시안(Flowit.html) 노드 디자인 통일에 따라
 * 알약(RiskPill) 대신 작은 점 + 라벨로 표기. (점만 위험도 색, 텍스트는 ink3)
 * 캔버스 노드 카드의 코너 점/자물쇠 표기와 시각 언어를 맞춘다.
 */
const DOT: Record<RiskLevel, string> = {
  [RiskLevel.LOW]: 'var(--color-risk-low)',
  [RiskLevel.MEDIUM]: 'var(--color-risk-med)',
  [RiskLevel.HIGH]: 'var(--color-risk-high)',
  [RiskLevel.RESTRICTED]: 'var(--color-risk-restricted)',
};

const LABEL: Record<RiskLevel, string> = {
  [RiskLevel.LOW]: 'Low',
  [RiskLevel.MEDIUM]: 'Medium',
  [RiskLevel.HIGH]: 'High',
  [RiskLevel.RESTRICTED]: 'Restricted',
};

export default function RiskDot({ level = RiskLevel.LOW }: { level?: RiskLevel }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[var(--color-ink3)]">
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: DOT[level] }}
      />
      {LABEL[level]}
    </span>
  );
}
