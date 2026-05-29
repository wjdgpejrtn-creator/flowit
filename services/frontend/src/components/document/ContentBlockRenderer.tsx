import type { ContentBlock } from '@common/generated';

interface Props {
  block: ContentBlock;
}

export default function ContentBlockRenderer({ block }: Props) {
  if (block.is_corrupted) {
    return (
      <div className="border-[1.5px] border-[var(--color-risk-restricted)] rounded-[4px_8px_4px_8px] px-3 py-2 text-[12px] text-[var(--color-risk-restricted)] bg-red-50">
        ⚠ 손상된 블록 (block_id: {block.block_id.slice(0, 8)}…)
      </div>
    );
  }

  switch (block.block_type) {
    case 'heading':
      return (
        <div className="font-bold text-[15px] mt-3 mb-1 text-[var(--color-ink)]">
          {block.content}
        </div>
      );

    case 'text':
      return (
        <p className="text-[13px] leading-relaxed text-[var(--color-ink2)] whitespace-pre-wrap">
          {block.content}
        </p>
      );

    case 'code':
      return (
        <pre className="font-mono text-[12px] bg-[var(--color-paper2)] border-[1.5px] border-[var(--color-line-soft)] rounded-[4px_8px_4px_8px] p-3 overflow-x-auto text-[var(--color-ink2)] leading-relaxed">
          {block.content}
        </pre>
      );

    case 'table':
      if (!block.table?.length) return null;
      return (
        <div className="overflow-x-auto">
          <table className="text-[12px] border-collapse w-full">
            {block.table.map((row, ri) => (
              <tr key={ri} className={ri === 0 ? 'bg-[var(--color-paper2)] font-bold' : ''}>
                {(row as unknown[]).map((cell, ci) => (
                  <td
                    key={ci}
                    className="border-[1px] border-[var(--color-ink3)] px-2 py-[3px] text-[var(--color-ink)]"
                  >
                    {String(cell ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </table>
        </div>
      );

    case 'image':
      return (
        <div className="border-[1.5px] border-[var(--color-line-soft)] rounded-[4px_8px_4px_8px] px-3 py-4 text-center text-[12px] text-[var(--color-ink4)] bg-[var(--color-paper2)]">
          🖼 이미지 블록 {block.section_title ? `— ${block.section_title}` : ''}
          {block.page != null && (
            <span className="ml-2 text-[11px] font-mono">p.{block.page}</span>
          )}
        </div>
      );

    default:
      return (
        <div className="text-[12px] text-[var(--color-ink4)] italic">
          [{block.block_type}] {block.content ?? ''}
        </div>
      );
  }
}
