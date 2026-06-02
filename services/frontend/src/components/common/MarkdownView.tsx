import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * 스킬 지침서(SKILL.md) 본문 렌더러 — paper/ink 테마에 맞춘 마크다운 표시.
 *
 * react-markdown(+remark-gfm)으로 제목/목록/코드블록/표/링크를 실제 서식으로 렌더링한다.
 * 신뢰 경계: 기본값으로 raw HTML을 렌더하지 않는다(rehype-raw 미사용) — 본문 내 `<script>` 등은
 * 그대로 텍스트로 표시되어 XSS가 발생하지 않는다. 코드는 하이라이팅 없이 모노스페이스로만 표시.
 */
const COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className="text-[18px] font-bold text-[var(--color-ink)] mt-4 mb-2 first:mt-0 pb-1 border-b border-[var(--color-line-soft)]">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-[16px] font-bold text-[var(--color-ink)] mt-4 mb-2 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-[14px] font-bold text-[var(--color-ink)] mt-3 mb-1 first:mt-0">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-[13px] font-semibold text-[var(--color-ink)] mt-3 mb-1 first:mt-0">{children}</h4>
  ),
  p: ({ children }) => (
    <p className="text-[13px] text-[var(--color-ink)] leading-[1.7] my-2">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc pl-5 my-2 text-[13px] text-[var(--color-ink)] leading-[1.7] flex flex-col gap-[2px]">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-5 my-2 text-[13px] text-[var(--color-ink)] leading-[1.7] flex flex-col gap-[2px]">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-1">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[var(--color-accent)] underline break-words"
    >
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-bold text-[var(--color-ink)]">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-[3px] border-[var(--color-line-soft)] pl-3 my-2 text-[var(--color-ink3)] italic">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-0 border-t border-[var(--color-line-soft)]" />,
  pre: ({ children }) => (
    <pre className="text-[12px] whitespace-pre-wrap break-words font-mono leading-[1.5] bg-[var(--color-paper2)] border border-[var(--color-line-soft)] rounded p-[10px] my-2 overflow-auto">
      {children}
    </pre>
  ),
  // 블록 코드(language-* 클래스)는 pre가 박스를 그리므로 코드 자체는 무장식,
  // 인라인 코드만 작은 배경 pill 로 표시.
  code: ({ className, children }) => {
    const isBlock = /\blanguage-/.test(className ?? '');
    if (isBlock) return <code className="font-mono">{children}</code>;
    return (
      <code className="font-mono text-[12px] bg-[var(--color-paper2)] border border-[var(--color-line-soft)] rounded px-[4px] py-[1px]">
        {children}
      </code>
    );
  },
  table: ({ children }) => (
    <div className="my-2 overflow-auto">
      <table className="text-[12px] border-collapse border border-[var(--color-line-soft)]">
        {children}
      </table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-[var(--color-line-soft)] px-2 py-1 bg-[var(--color-paper2)] text-left font-semibold text-[var(--color-ink)]">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-[var(--color-line-soft)] px-2 py-1 text-[var(--color-ink)]">{children}</td>
  ),
};

export default function MarkdownView({ source }: { source: string }) {
  return (
    <div className="break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {source}
      </ReactMarkdown>
    </div>
  );
}
