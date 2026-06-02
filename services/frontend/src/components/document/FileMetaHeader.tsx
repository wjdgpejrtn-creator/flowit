import type { DocumentResponse } from '@/lib/api/documentApi';

function fmt(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface FileMetaHeaderProps {
  doc: DocumentResponse;
}

export default function FileMetaHeader({ doc }: FileMetaHeaderProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)]">
      <span className="text-[22px]">📄</span>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-[14px] truncate">{doc.file_name}</div>
        <div className="text-[11px] text-[var(--color-ink3)] flex items-center gap-2 mt-[2px]">
          <span className="font-mono">{doc.mime_type}</span>
          <span>·</span>
          <span>{fmt(doc.file_size)}</span>
          <span>·</span>
          <span
            className="inline-flex items-center gap-1 font-semibold"
            style={{ color: doc.is_analyzed ? 'var(--color-risk-low)' : 'var(--color-ink4)' }}
          >
            <span
              className="w-[6px] h-[6px] rounded-full"
              style={{ background: doc.is_analyzed ? 'var(--color-risk-low)' : 'var(--color-ink4)' }}
            />
            {doc.is_analyzed ? '분석 완료' : '분석 전'}
          </span>
        </div>
      </div>
      <span className="font-mono text-[11px] text-[var(--color-ink4)] break-all max-w-[200px] truncate">
        {doc.document_id.slice(0, 8)}…
      </span>
    </div>
  );
}
