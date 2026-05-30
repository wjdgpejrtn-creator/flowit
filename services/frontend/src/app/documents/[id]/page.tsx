'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import ErrorBanner from '@/components/common/ErrorBanner';
import FileMetaHeader from '@/components/document/FileMetaHeader';
import DocumentViewer from '@/components/document/DocumentViewer';
import DocumentAnalysisSidebar from '@/components/document/DocumentAnalysisSidebar';
import {
  getDocument,
  getDocumentBlocks,
  getDownloadUrl,
  analyzeDocument,
  type DocumentResponse,
} from '@/lib/api/documentApi';
import { AnalysisStatus, type ContentBlock, type ParseCoverage } from '@common/generated';

// 폴링 정책 — 분석 dispatch 후 2초 간격으로 max 60s.
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 60_000;

const STATUS_LABEL: Record<AnalysisStatus, string> = {
  [AnalysisStatus.PENDING]:   '분석 전',
  [AnalysisStatus.RUNNING]:   '분석 중',
  [AnalysisStatus.COMPLETED]: '분석 완료',
  [AnalysisStatus.FAILED]:    '분석 실패',
};

const STATUS_COLOR: Record<AnalysisStatus, string> = {
  [AnalysisStatus.PENDING]:   'var(--color-ink4)',
  [AnalysisStatus.RUNNING]:   'var(--color-accent)',
  [AnalysisStatus.COMPLETED]: 'var(--color-risk-low)',
  [AnalysisStatus.FAILED]:    'var(--color-risk-high)',
};

function StatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] px-2 py-[2px] rounded-full border-[1.5px] font-bold"
      style={{ borderColor: STATUS_COLOR[status], color: STATUS_COLOR[status] }}
    >
      {status === 'running' && <span className="animate-pulse">●</span>}
      {STATUS_LABEL[status]}
    </span>
  );
}

export default function DocumentDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;

  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [blocks, setBlocks] = useState<ContentBlock[]>([]);
  const [coverage, setCoverage] = useState<ParseCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // 폴링 lifecycle 관리 — 컴포넌트 언마운트 / 새 분석 dispatch 시 기존 타이머 정리.
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartRef = useRef<number>(0);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // 분석 완료 시 blocks 한 번만 fetch — completed 상태 진입 트리거.
  const fetchBlocksOnce = useCallback(async (docId: string) => {
    try {
      const res = await getDocumentBlocks(docId);
      setBlocks(res.blocks);
      setCoverage(res.coverage ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '분석 결과 조회 실패');
    }
  }, []);

  // 폴링 1틱: 메타 갱신 후 상태 분기.
  // - completed: blocks fetch + 폴링 중단
  // - failed: 폴링 중단 (사용자가 retry 클릭)
  // - running/pending: 계속 폴링 (timeout까지)
  const pollOnce = useCallback(async () => {
    try {
      const fresh = await getDocument(id);
      setDoc(fresh);
      if (fresh.analysis_status === AnalysisStatus.COMPLETED) {
        stopPolling();
        await fetchBlocksOnce(id);
      } else if (fresh.analysis_status === AnalysisStatus.FAILED) {
        stopPolling();
      } else if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
        // 60s 안에 끝나지 않음 — 폴링 멈추고 사용자에게 수동 새로고침 안내.
        stopPolling();
        setError('분석 시간이 60초를 초과했습니다. 잠시 후 새로고침해 주세요.');
      }
    } catch (e) {
      // 폴링 중 일시 실패는 비활성화하지 않고 다음 틱 시도 — 네트워크 일시 단절 허용.
      // 단, 명시적 에러는 표시.
      setError(e instanceof Error ? e.message : '폴링 실패');
    }
  }, [id, stopPolling, fetchBlocksOnce]);

  const startPolling = useCallback(() => {
    stopPolling();
    pollStartRef.current = Date.now();
    pollTimerRef.current = setInterval(pollOnce, POLL_INTERVAL_MS);
  }, [pollOnce, stopPolling]);

  // 마운트 시 메타 fetch — 이미 completed 면 즉시 blocks 호출, running 이면 폴링 시작.
  useEffect(() => {
    setLoading(true);
    getDocument(id)
      .then(async (fresh) => {
        setDoc(fresh);
        if (fresh.analysis_status === AnalysisStatus.COMPLETED) {
          await fetchBlocksOnce(id);
        } else if (fresh.analysis_status === AnalysisStatus.RUNNING) {
          startPolling();
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : '문서 조회 실패'))
      .finally(() => setLoading(false));

    return () => stopPolling();
  }, [id, fetchBlocksOnce, startPolling, stopPolling]);

  const handleAnalyze = async () => {
    if (!doc) return;
    setAnalyzing(true);
    setError(null);
    setBlocks([]);
    setCoverage(null);
    try {
      await analyzeDocument(id);
      // dispatch 직후 메타가 아직 running 으로 갱신 안 됐을 수 있음 — 폴링이 따라잡음.
      setDoc((prev) => prev ? { ...prev, analysis_status: AnalysisStatus.RUNNING, is_analyzed: false } : prev);
      startPolling();
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

  const status: AnalysisStatus = doc?.analysis_status ?? AnalysisStatus.PENDING;
  const isRunning = status === AnalysisStatus.RUNNING || analyzing;
  const isFailed = status === AnalysisStatus.FAILED;

  return (
    <div className="h-screen flex flex-col bg-[var(--color-paper)]">
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
        {doc && <StatusBadge status={status} />}
        <div className="flex-1" />
        <Btn ghost onClick={handleDownload} disabled={downloading || !doc}>
          {downloading ? '준비 중…' : '⬇ 다운로드'}
        </Btn>
        <Btn onClick={handleAnalyze} disabled={isRunning || !doc}>
          {isRunning ? '분석 중…' : isFailed ? '🔁 다시 분석' : '🔍 분석'}
        </Btn>
        {/* 문서 → 스킬빌더 핸드오프 — REQ-013(황대원) 영역. UI 자리만, 동작 wiring 후속. */}
        <Btn primary disabled title="스킬빌더 연동 예정 (REQ-013)" className="opacity-60">
          🛠 이 문서로 스킬 만들기
        </Btn>
      </div>

      {error && (
        <div className="px-4 pt-2">
          <ErrorBanner><span>⚠ {error}</span></ErrorBanner>
        </div>
      )}
      {isFailed && doc?.analysis_error && (
        <div className="px-4 pt-2 text-[12px] text-[var(--color-risk-high)] border-b border-[var(--color-line-soft)] pb-2 bg-[var(--color-paper2)]">
          ✗ 분석 실패: {doc.analysis_error}
        </div>
      )}
      {isRunning && (
        <div className="px-4 pt-2 text-[12px] text-[var(--color-ink3)] border-b border-[var(--color-line-soft)] pb-2 bg-[var(--color-paper2)]">
          🔄 분석 중입니다… (최대 60초)
        </div>
      )}
      {coverage && status === AnalysisStatus.COMPLETED && (
        <div className="px-4 py-2 border-b border-[var(--color-line-soft)] bg-[var(--color-paper2)] flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-[var(--color-ink3)]">
          <span className="font-bold text-[var(--color-ink)]">📊 파싱 커버리지</span>
          <span>페이지 <b>{coverage.parsed_pages}/{coverage.total_pages}</b></span>
          <span>텍스트 {coverage.text_blocks}</span>
          <span>표 {coverage.table_blocks}</span>
          {coverage.vision_blocks > 0 && <span>이미지 {coverage.vision_blocks}</span>}
          {coverage.failed_blocks > 0 && (
            <span className="text-[var(--color-risk-high)]">실패 {coverage.failed_blocks}</span>
          )}
          {coverage.warnings.length > 0 && (
            <span className="text-[var(--color-risk-restricted)]" title={coverage.warnings.join('\n')}>
              ⚠ 경고 {coverage.warnings.length}건
            </span>
          )}
        </div>
      )}

      {/* 파일 메타 */}
      {doc && <FileMetaHeader doc={doc} />}

      {/* 본문 — 좌: 문서 뷰어 / 우: 분석 사이드바 (디자인 SSOT 2단 레이아웃) */}
      <div className="flex-1 grid grid-cols-[1fr_320px] min-h-0">
        <div className="overflow-auto">
          {loading ? (
            <DocumentViewer blocks={[]} loading />
          ) : doc ? (
            <DocumentViewer blocks={blocks} />
          ) : (
            <div className="flex items-center justify-center py-16 text-[13px] text-[var(--color-ink4)]">
              문서를 찾을 수 없습니다.
            </div>
          )}
        </div>
        <DocumentAnalysisSidebar analyzed={status === AnalysisStatus.COMPLETED} />
      </div>
    </div>
  );
}
