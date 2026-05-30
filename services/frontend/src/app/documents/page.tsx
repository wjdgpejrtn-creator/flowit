'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import ErrorBanner from '@/components/common/ErrorBanner';
import { uploadDocument, type DocumentResponse } from '@/lib/api/documentApi';
import { DOCS_STORAGE_KEY } from '@/lib/storage/keys';

// TODO(#219): 문서 목록이 localStorage SSOT — 디바이스 간 sync X, 다중 사용자 privacy 위험.
// 백엔드 GET /api/v1/documents 추가 후 서버 목록을 SSOT 로 전환 예정. (PR #216 리뷰 #2)
function loadStoredDocs(): DocumentResponse[] {
  try {
    const raw = localStorage.getItem(DOCS_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as DocumentResponse[]) : [];
  } catch {
    return [];
  }
}

function fmt(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// 파일타입 태그 — mime_type / 확장자에서 유추.
function fileTag(doc: DocumentResponse): string {
  const ext = doc.file_name.split('.').pop()?.toUpperCase();
  if (ext && ext.length <= 4) return ext;
  const sub = doc.mime_type.split('/').pop() ?? doc.mime_type;
  return sub.toUpperCase().slice(0, 4);
}

// 카드 — 클릭 시 상세(분석 뷰)로 이동. 디자인 SSOT: screens-3.jsx DocumentsScreen "통합" v1.
function DocCard({
  doc,
  onOpen,
  onDelete,
}: {
  doc: DocumentResponse;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(doc.document_id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(doc.document_id);
        }
      }}
      className="group relative flex flex-col gap-[6px] border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] p-[10px] bg-[var(--color-surface)] hover:bg-[var(--color-paper2)] cursor-pointer transition-colors"
    >
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-bold px-[6px] py-[1px] border-[1.5px] border-[var(--color-ink)] rounded-[3px_6px_3px_6px] bg-[var(--color-paper2)]">
          {fileTag(doc)}
        </span>
        <span className="text-[11px] text-[var(--color-ink3)]">{fmt(doc.file_size)}</span>
        <div className="flex-1" />
        <span className="font-mono text-[11px] text-[var(--color-ink4)]">열기 →</span>
      </div>

      <div className="font-bold text-[15px] truncate" title={doc.file_name}>
        {doc.file_name}
      </div>

      {/* 분석 상태 — 품질 점수는 백엔드 미연동이라 분석 상태로 대체 (placeholder). */}
      <div className="flex items-center justify-between mt-1">
        <span className="text-[11px] text-[var(--color-ink3)]">분석 상태</span>
        <span
          className="text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px] whitespace-nowrap"
          style={{
            color: doc.is_analyzed ? 'var(--color-risk-low)' : 'var(--color-ink4)',
            borderColor: doc.is_analyzed ? 'var(--color-risk-low)' : 'var(--color-ink4)',
          }}
        >
          {doc.is_analyzed ? '분석 완료' : '분석 전'}
        </span>
      </div>

      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(doc.document_id);
        }}
        title="삭제"
        className="absolute top-[8px] right-[8px] text-[11px] text-[var(--color-risk-restricted)] border-[1.5px] border-[var(--color-risk-restricted)] rounded-[4px_8px_4px_8px] px-[6px] bg-[var(--color-surface)] cursor-pointer hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        ✕
      </button>
    </div>
  );
}

export default function DocumentsPage() {
  const router = useRouter();
  const [docs, setDocs] = useState<DocumentResponse[]>(() => loadStoredDocs());
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem(DOCS_STORAGE_KEY, JSON.stringify(docs));
    } catch {}
  }, [docs]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const doc = await uploadDocument(file);
      setDocs((prev) => [doc, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : '업로드 실패');
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleUpload(file);
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) void handleUpload(file);
  };

  const handleDelete = (id: string) => {
    setDocs((prev) => prev.filter((d) => d.document_id !== id));
  };

  const handleOpen = (id: string) => {
    router.push(`/documents/${id}`);
  };

  return (
    <div className="h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* 본문 — 좌: 문서 그리드 / 우: 업로드 패널 (디자인 SSOT 2단 레이아웃) */}
      <div className="flex-1 grid grid-cols-[1fr_260px] min-h-0">
        {/* 좌측 — 문서 그리드 */}
        <div className="p-4 overflow-auto">
          {error && (
            <div className="mb-3">
              <ErrorBanner><span>⚠ {error}</span></ErrorBanner>
            </div>
          )}

          <div className="flex items-center justify-between">
            <h1 className="font-bold text-[18px] tracking-[-0.02em]">문서 ({docs.length})</h1>
            <div className="flex items-center gap-1 text-[13px] text-[var(--color-ink4)] border-[1.5px] border-[var(--color-line-soft)] rounded-[4px_8px_4px_8px] px-2 py-[2px]">
              🔍 검색…
            </div>
          </div>
          <p className="text-[11px] text-[var(--color-ink3)] mt-2">
            ↓ 카드를 클릭하면 분석 결과(상세 뷰)로 이동합니다
          </p>

          {docs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-[var(--color-ink4)]">
              <div className="text-[36px] mb-3">🗂</div>
              <div className="font-bold text-[13px] mb-1">문서가 없습니다</div>
              <div className="text-[12px]">오른쪽 패널에서 파일을 업로드해 AI 분석을 시작하세요.</div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-[10px] mt-[10px]">
              {docs.map((doc) => (
                <DocCard key={doc.document_id} doc={doc} onOpen={handleOpen} onDelete={handleDelete} />
              ))}
            </div>
          )}
        </div>

        {/* 우측 — 업로드 패널 */}
        <div className="border-l-[1.5px] border-[var(--color-ink)] p-3 bg-[var(--color-paper2)] overflow-auto">
          <div className="font-bold text-[13px]">업로드</div>
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
            className="mt-2 border-[2px] border-dashed border-[var(--color-ink3)] rounded-[5px_11px_6px_10px] px-4 py-6 text-center text-[12px] text-[var(--color-ink3)] hover:border-[var(--color-ink)] hover:bg-[var(--color-surface)] transition-colors cursor-pointer"
          >
            {uploading ? (
              <span>업로드 중…</span>
            ) : (
              <>
                <div className="text-[28px]">⤓</div>
                <div className="mt-1">파일을 드래그하거나<br />클릭해서 선택</div>
                <div className="font-mono text-[11px] text-[var(--color-ink4)] mt-2">
                  PDF · DOCX · XLSX · CSV · TXT · MD
                </div>
              </>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.docx,.xlsx,.csv,.txt,.md"
            onChange={handleFileChange}
          />
        </div>
      </div>
    </div>
  );
}
