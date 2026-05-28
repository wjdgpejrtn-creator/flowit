import type { AnalysisResult } from '@common/generated';

interface Props {
  result: AnalysisResult;
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? 'var(--color-risk-low)' : pct >= 50 ? 'var(--color-risk-med)' : 'var(--color-risk-high)';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-[8px] border-[1.5px] border-[var(--color-ink)] rounded-full bg-[var(--color-paper)] overflow-hidden">
        <div
          className="h-full border-r-[1.5px] border-[var(--color-ink)] transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="font-mono text-[12px] text-[var(--color-ink3)] w-8 text-right">{pct}%</span>
    </div>
  );
}

export default function AnalysisResultCard({ result }: Props) {
  return (
    <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-4 flex flex-col gap-3">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <div className="font-bold text-[13px]">{result.document_title}</div>
          <div className="text-[11px] text-[var(--color-ink3)] mt-[2px]">
            {result.category}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] text-[var(--color-ink3)]">신뢰도</div>
          <div className="font-mono font-bold text-[14px]">{Math.round(result.confidence * 100)}%</div>
        </div>
      </div>

      <ScoreBar score={result.confidence} />

      {/* 요약 */}
      <div>
        <div className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider mb-1">요약</div>
        <p className="text-[12px] leading-relaxed text-[var(--color-ink2)]">{result.summary}</p>
      </div>

      {/* 핵심 포인트 */}
      {result.key_points.length > 0 && (
        <div>
          <div className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider mb-1">핵심 포인트</div>
          <ul className="flex flex-col gap-1">
            {result.key_points.map((pt, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] text-[var(--color-ink2)]">
                <span className="text-[var(--color-ink4)] flex-shrink-0 mt-[1px]">▸</span>
                <span>{pt}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 경고 */}
      {result.warnings.length > 0 && (
        <div className="border-[1.5px] border-[var(--color-risk-med)] rounded-[4px_8px_4px_8px] p-2 bg-orange-50">
          <div className="text-[11px] font-bold text-[var(--color-risk-med)] mb-1">주의사항</div>
          {result.warnings.map((w, i) => (
            <div key={i} className="text-[11px] text-[var(--color-risk-med)]">⚠ {w}</div>
          ))}
        </div>
      )}

      {/* 추가 질문 */}
      {result.questions.length > 0 && (
        <div>
          <div className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider mb-1">추가 검토 필요</div>
          {result.questions.map((q, i) => (
            <div key={i} className="text-[11px] text-[var(--color-ink3)] flex items-start gap-1">
              <span>?</span><span>{q}</span>
            </div>
          ))}
        </div>
      )}

      <div className="text-[10px] text-[var(--color-ink4)] font-mono pt-1 border-t border-[var(--color-line-soft)]">
        {result.template_type} · v{result.prompt_version} · few-shot {result.few_shot_count}
      </div>
    </div>
  );
}
