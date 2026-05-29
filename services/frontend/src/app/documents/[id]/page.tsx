'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import ErrorBanner from '@/components/common/ErrorBanner';
import FileMetaHeader from '@/components/document/FileMetaHeader';
import DocumentViewer from '@/components/document/DocumentViewer';
import {
  getDocument,
  getDownloadUrl,
  analyzeDocument,
  type DocumentResponse,
} from '@/lib/api/documentApi';

export default function DocumentDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;

  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeMsg, setAnalyzeMsg] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getDocument(id)
      .then(setDoc)
      .catch((e) => setError(e instanceof Error ? e.message : '문서 조회 실패'))
      .finally(() => setLoading(false));
  }, [id]);

  const handleAnalyze = async () => {
    if (!doc) return;
    setAnalyzing(true);
    setAnalyzeMsg(null);
    try {
      const res = await analyzeDocument(id);
      setAnalyzeMsg(`분석 요청 완료 (task: ${res.task_id.slice(0, 8)}…). 잠시 후 새로고침하세요.`);
      setDoc((prev) => prev ? { ...prev, is_analyzed: false } : prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : '분석 요청 실패');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const { download_url } = await getDownloadUrl(id);
      window.open(download_url, '_blank');
    } catch (e) {
      setError(e instanceof Error ? e.message : '다운로드 URL 발급 실패');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* 헤더 */}
      <div className="flex items-center gap-3 px-4 py-2 border-b-[1.5px] border-[var(--color-ink3)] bg-[var(--color-paper2)]">
        <Link
          href="/documents"
          className="text-[12px] text-[var(--color-ink3)] no-underline hover:text-[var(--color-ink)]"
        >
          ← 문서 목록
        </Link>
        <span className="text-[var(--color-ink4)]">/</span>
        <span className="text-[12px] text-[var(--color-ink3)] truncate">
          {loading ? '로딩 중…' : (doc?.file_name ?? id)}
        </span>
        <div className="flex-1" />
        <Btn ghost onClick={handleDownload} disabled={downloading || !doc}>
          {downloading ? '준비 중…' : '⬇ 다운로드'}
        </Btn>
        <Btn onClick={handleAnalyze} disabled={analyzing || !doc}>
          {analyzing ? '요청 중…' : '🔍 분석'}
        </Btn>
      </div>

      {error && (
        <div className="px-4 pt-2">
          <ErrorBanner><span>⚠ {error}</span></ErrorBanner>
        </div>
      )}
      {analyzeMsg && (
        <div className="px-4 pt-2 text-[12px] text-[var(--color-risk-low)] border-b border-[var(--color-line-soft)] pb-2 bg-[var(--color-paper2)]">
          ✓ {analyzeMsg}
        </div>
      )}

      {/* 파일 메타 */}
      {doc && <FileMetaHeader doc={doc} />}

      {/* 본문 */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <DocumentViewer blocks={[]} loading />
        ) : doc ? (
          <DocumentViewer
            blocks={[]}
          />
        ) : (
          <div className="flex items-center justify-center py-16 text-[13px] text-[var(--color-ink4)]">
            문서를 찾을 수 없습니다.
          </div>
        )}
      </div>
    </div>
  );
}
