interface Props {
  text: string;
}

export default function RationaleStream({ text }: Props) {
  return (
    <div className="text-[12px] text-[var(--color-ink2)] leading-relaxed bg-[var(--color-surface)] border-[1.5px] border-[var(--color-line-soft)] rounded-[4px_8px_4px_8px] p-[8px] min-h-[64px]">
      {text || (
        <span className="text-[var(--color-ink4)] italic">
          AI가 분석 중이면 여기에 판단 근거가 표시됩니다.
          <br />
          노드 선택 이유, 리스크 평가 등…
        </span>
      )}
    </div>
  );
}
