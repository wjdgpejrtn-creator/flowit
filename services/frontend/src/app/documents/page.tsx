'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import Skel from '@/components/common/Skel';
import ErrorBanner from '@/components/common/ErrorBanner';
import { getDocument, uploadDocument, type DocumentResponse } from '@/lib/api/documentApi';

function fmt(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DocRow({ doc, onDelete }: { doc: DocumentResponse; onDelete: (id: string) => void }) {
  return (
    <div className="flex items-center gap-3 border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-3 py-[6px] bg-[var(--color-surface)] hover:bg-[var(--color-paper2)] group">
      <span className="text-[16px]">📄</span>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-[13px] truncate">{doc.file_name}</div>
        <div className="text-[11px] text-[var(--color-ink3)] flex items-center gap-2 mt-[1px]">
          <span className="font-mono">{doc.mime_type}</span>
          <span>·</span>
          <span>{fmt(doc.file_size)}</span>
        </div>
      </div>
      <span
        className="text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px] whitespace-nowrap"
        style={{
          color: doc.is_analyzed ? 'var(--color-risk-low)' : 'var(--color-ink4)',
          borderColor: doc.is_analyzed ? 'var(--color-risk-low)' : 'var(--color-ink4)',
        }}
      >
        {doc.is_analyzed ? '분석 완료' : '분석 전'}
      </span>
      <Link
        href={`/documents/${doc.document_id}`}
        className="text-[12px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-2 py-[2px] no-underline text-[var(--color-ink)] bg-[var(--color-surface)] hover:bg-[var(--color-hl)] opacity-0 group-hover:opacity-100 transition-opacity"
      >
        열기
      </Link>
      <button
        onClick={() => onDelete(doc.document_id)}
        className="text-[11px] text-[var(--color-risk-restricted)] border-[1.5px] border-[var(--color-risk-restricted)] rounded-[4px_8px_4px_8px] px-2 py-[2px] bg-transparent cursor-pointer hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        삭제
      </button>
    </div>
  );
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // NOTE: 현재 백엔드에 list 엔드포인트가 없어 빈 목록으로 시작.
  // 업로드한 문서는 직접 목록에 추가하는 방식으로 동작.
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

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      <div className="px-6 pt-5 pb-3 border-b-[1.5px] border-[var(--color-ink3)] bg-[var(--color-paper2)] flex items-center justify-between">
        <div>
          <h1 className="font-bold text-[20px] tracking-[-0.02em]">문서</h1>
          <p className="text-[12px] text-[var(--color-ink3)] mt-1">
            업로드한 문서를 AI로 분석하고 워크플로우에 활용하세요.
          </p>
        </div>
        <Btn primary onClick={() => fileInputRef.current?.click()} disabled={uploading}>
          {uploading ? '업로드 중…' : '+ 문서 업로드'}
        </Btn>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.xlsx,.csv,.txt,.md"
          onChange={handleFileChange}
        />
      </div>

      <div className="flex-1 p-5 flex flex-col gap-4">
        {error && (
          <ErrorBanner><span>⚠ {error}</span></ErrorBanner>
        )}

        {/* 드래그 앤 드롭 업로드 영역 */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          className="border-[2px] border-dashed border-[var(--color-ink3)] rounded-[5px_11px_6px_10px] px-6 py-8 text-center text-[13px] text-[var(--color-ink3)] hover:border-[var(--color-ink)] hover:bg-[var(--color-paper2)] transition-colors cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? (
            <span>업로드 중…</span>
          ) : (
            <>
              <div className="text-[24px] mb-2">📎</div>
              <div>여기에 파일을 드래그하거나 클릭해서 업로드</div>
              <div className="text-[11px] mt-1 text-[var(--color-ink4)]">PDF, DOCX, XLSX, CSV, TXT, MD · 최대 50MB</div>
            </>
          )}
        </div>

        {/* 문서 목록 */}
        {loading ? (
          <div className="flex flex-col gap-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-3 py-[6px]">
                <Skel h={14} w="60%" />
              </div>
            ))}
          </div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center text-[var(--color-ink4)]">
            <div className="text-[36px] mb-3">🗂</div>
            <div className="font-bold text-[13px] mb-1">문서가 없습니다</div>
            <div className="text-[12px]">파일을 업로드해서 AI 분석을 시작하세요.</div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="text-[11px] text-[var(--color-ink3)] font-bold uppercase tracking-wider mb-1">
              문서 {docs.length}개
            </div>
            {docs.map((doc) => (
              <DocRow key={doc.document_id} doc={doc} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
