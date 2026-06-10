'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import { uploadDocument, listDocuments, type DocumentResponse } from '@/lib/api/documentApi';
import { DOCS_STORAGE_KEY } from '@/lib/storage/keys';

// #219: 서버(GET /api/v1/documents)가 SSOT. localStorage 는 optimistic 캐시로만 유지
// (첫 페인트 즉시 표시 + 서버 조회 실패 시 폴백).
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

function fileTag(doc: DocumentResponse): string {
  const ext = doc.file_name.split('.').pop()?.toUpperCase();
  if (ext && ext.length <= 4) return ext;
  const sub = doc.mime_type.split('/').pop() ?? doc.mime_type;
  return sub.toUpperCase().slice(0, 4);
}

/** 파일타입별 배지 색 (시안: PDF 빨강, CSV/표 파랑) */
function tagColors(tag: string): { bg: string; fg: string } {
  if (tag === 'PDF') return { bg: '#FDECEC', fg: '#D9534F' };
  if (['CSV', 'XLSX', 'XLS'].includes(tag)) return { bg: '#EAF1FB', fg: '#3B73C4' };
  if (['DOC', 'DOCX'].includes(tag)) return { bg: '#EAF1FB', fg: '#3B73C4' };
  return { bg: '#F1ECE4', fg: '#9C8B7B' };
}

function DocRow({
  doc,
  onOpen,
  onAnalyze,
  onDelete,
}: {
  doc: DocumentResponse;
  onOpen: (id: string) => void;
  onAnalyze: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const tag = fileTag(doc);
  const { bg, fg } = tagColors(tag);
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
      className="group relative doc-row bg-white border border-line-soft rounded-2xl p-4 flex items-center justify-between shadow-sm hover:border-accent-coral transition-all cursor-pointer"
    >
      <div className="flex items-center space-x-3">
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center font-black text-[10px] flex-shrink-0"
          style={{ background: bg, color: fg }}
        >
          {tag}
        </div>
        <div>
          <p className="text-sm font-bold text-ink truncate" title={doc.file_name}>
            {doc.file_name}
          </p>
          <p className="text-[11px] text-ink3 font-bold">
            {fmt(doc.file_size)} · 상태: {doc.is_analyzed ? '분석 완료' : '분석 준비'}
          </p>
        </div>
      </div>
      <div className="flex items-center space-x-3">
        <span
          className="px-2.5 py-1 rounded-full text-[10px] font-bold whitespace-nowrap"
          style={
            doc.is_analyzed
              ? { background: '#E7F6EF', color: '#10B981' }
              : { background: '#FBF1DF', color: '#C8860B' }
          }
        >
          {doc.is_analyzed ? '분석 완료' : '미분석'}
        </span>
        {doc.is_analyzed ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onOpen(doc.document_id);
            }}
            className="px-3 py-1.5 rounded-lg border border-line-soft text-xs font-bold text-ink hover:bg-paper flex items-center space-x-1"
          >
            <span>열기</span>
            <Icon name="chevron-right" className="w-3.5 h-3.5" />
          </button>
        ) : (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onAnalyze(doc.document_id);
            }}
            className="px-3 py-1.5 rounded-lg bg-accent text-white text-xs font-bold hover:bg-accent3"
          >
            분석하기
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(doc.document_id);
        }}
        title="삭제"
        aria-label="문서 삭제"
        className="absolute -top-2.5 -right-2.5 w-7 h-7 flex items-center justify-center rounded-full opacity-0 group-hover:opacity-100 bg-white border border-line-soft shadow-md text-ink4 hover:bg-danger-soft hover:border-danger/40 hover:text-danger transition-all"
      >
        <Icon name="x" className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export default function DocumentsPage() {
  const router = useRouter();
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hydratedRef = useRef(false);

  useEffect(() => {
    if (!hydratedRef.current) return;
    try {
      localStorage.setItem(DOCS_STORAGE_KEY, JSON.stringify(docs));
    } catch {}
  }, [docs]);

  useEffect(() => {
    const cached = loadStoredDocs();
    if (cached.length > 0) setDocs(cached);
    hydratedRef.current = true;

    let cancelled = false;
    void (async () => {
      try {
        const serverDocs = await listDocuments();
        if (!cancelled) setDocs(serverDocs);
      } catch {
        /* 서버 조회 실패 — localStorage 캐시 유지 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    showToast('파일 업로드를 시작합니다...');
    try {
      const doc = await uploadDocument(file);
      setDocs((prev) => [doc, ...prev]);
      showToast('업로드 및 동기화 완료!');
    } catch (e) {
      showToast(e instanceof Error ? e.message : '업로드 실패');
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
    showToast('문서를 삭제했습니다.');
  };

  const handleOpen = (id: string) => router.push(`/documents/${id}`);
  // 목록의 "분석하기" — 상세페이지로 이동해 거기서 분석을 시작한다(?analyze=1).
  // 상세페이지가 분석 진행/결과(blocks·coverage·폴링) UI를 이미 갖추고 있어 진입점만 담당.
  const handleAnalyze = (id: string) => router.push(`/documents/${id}?analyze=1`);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? docs.filter((d) => d.file_name.toLowerCase().includes(q)) : docs;
  }, [docs, query]);

  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />

      <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-4">
        {/* 헤더 */}
        <div className="flex items-end justify-between border-b border-line-soft pb-3">
          <div>
            <h2 className="text-lg font-bold text-ink">문서 보관함</h2>
            <p className="text-xs text-ink3 font-bold">카드를 클릭하여 상세 분석 결과를 확인하세요.</p>
          </div>
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="문서 이름 검색..."
              aria-label="문서 이름 검색"
              className="w-48 pl-8 pr-3 py-1.5 text-xs rounded-lg border border-line-soft focus:outline-none focus:border-accent-coral bg-white text-ink font-bold"
            />
            <Icon name="search" className="w-3.5 h-3.5 text-ink3 absolute left-2.5 top-2" />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* 좌: 문서 목록 */}
          <div className="lg:col-span-8 space-y-3">
            {filtered.length === 0 ? (
              <div className="bg-white border border-line-soft rounded-2xl p-8 text-center shadow-sm">
                {query ? (
                  <p className="text-sm font-bold text-ink">검색 결과가 없습니다.</p>
                ) : (
                  <>
                    <div className="w-12 h-12 rounded-full bg-paper text-accent flex items-center justify-center mx-auto mb-2">
                      <Icon name="folder-open" className="w-6 h-6" />
                    </div>
                    <p className="text-sm font-bold text-ink">문서가 없습니다</p>
                    <p className="text-xs text-ink3 font-bold mt-1">
                      오른쪽 패널에서 파일을 업로드해 AI 분석을 시작하세요.
                    </p>
                  </>
                )}
              </div>
            ) : (
              filtered.map((doc) => (
                <DocRow
                  key={doc.document_id}
                  doc={doc}
                  onOpen={handleOpen}
                  onAnalyze={handleAnalyze}
                  onDelete={handleDelete}
                />
              ))
            )}
          </div>

          {/* 우: 업로드 패널 */}
          <div className="lg:col-span-4 space-y-2">
            <h4 className="text-xs font-bold text-ink uppercase tracking-wider">업로드</h4>
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileInputRef.current?.click()}
              className="bg-white border border-dashed border-line-soft hover:border-accent-coral rounded-2xl p-8 text-center cursor-pointer transition-all shadow-sm"
            >
              <div className="w-12 h-12 rounded-full bg-paper text-accent flex items-center justify-center mx-auto mb-2">
                <Icon name="upload-cloud" className="w-6 h-6" />
              </div>
              <p className="text-sm font-bold text-ink">
                {uploading ? '업로드 중…' : '파일을 드래그하거나 클릭해서 선택'}
              </p>
              <p className="text-[10px] text-ink3 font-bold mt-1">PDF · DOCX · XLSX · CSV · TXT · MD</p>
            </div>
            <p className="text-[10px] text-ink4 font-bold leading-relaxed">
              업로드된 문서는 플로잇 보안 규정에 따라 암호화 격리 처리되어 분석 연동됩니다.
            </p>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.docx,.xlsx,.csv,.txt,.md"
              onChange={handleFileChange}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
