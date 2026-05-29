import type { ContentBlock } from '@common/generated';
import ContentBlockRenderer from './ContentBlockRenderer';

interface Props {
  blocks: ContentBlock[];
  loading?: boolean;
}

export default function DocumentViewer({ blocks, loading }: Props) {
  if (loading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        {[120, 80, 160, 60, 200].map((w, i) => (
          <div
            key={i}
            className="animate-shimmer rounded"
            style={{ height: 14, width: w }}
          />
        ))}
      </div>
    );
  }

  if (blocks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center text-[13px] text-[var(--color-ink4)]">
        <div className="text-[32px] mb-3">📋</div>
        <div className="font-bold mb-1">분석 전 문서입니다</div>
        <div className="text-[12px]">상단의 분석 버튼을 눌러 내용을 추출하세요.</div>
      </div>
    );
  }

  // page별로 그룹핑
  const pages = blocks.reduce<Map<number, ContentBlock[]>>((acc, b) => {
    const page = b.page ?? 0;
    if (!acc.has(page)) acc.set(page, []);
    acc.get(page)!.push(b);
    return acc;
  }, new Map());

  return (
    <div className="flex flex-col gap-1 p-4">
      {[...pages.entries()].sort(([a], [b]) => a - b).map(([page, pageBlocks]) => (
        <div key={page}>
          {page > 0 && (
            <div className="flex items-center gap-2 my-3">
              <div className="flex-1 h-[1px] bg-[var(--color-line-soft)]" />
              <span className="text-[10px] font-mono text-[var(--color-ink4)]">p.{page}</span>
              <div className="flex-1 h-[1px] bg-[var(--color-line-soft)]" />
            </div>
          )}
          <div className="flex flex-col gap-2">
            {pageBlocks.map((block) => (
              <ContentBlockRenderer key={block.block_id} block={block} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
