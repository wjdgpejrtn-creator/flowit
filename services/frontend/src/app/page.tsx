'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import Skel from '@/components/common/Skel';
import { useAuthStore } from '@/stores/authStore';
import { listWorkflows } from '@/lib/api/workflowApi';
import type { WorkflowSchema } from '@common/generated';

const QUICK_CHIPS = ['📈 광고 리포트', '📄 PDF 처리', '💬 Slack 알림', '📅 캘린더 동기화'];
const RECENT_LIMIT = 5;

export default function DashboardPage() {
  const router = useRouter();
  const { userName, dept } = useAuthStore();
  const userDisplay = userName ? `${userName}님${dept ? ` · ${dept}` : ''}` : '사용자님';

  const [input, setInput] = useState('');
  const [recent, setRecent] = useState<WorkflowSchema[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listWorkflows(RECENT_LIMIT, 0)
      .then(setRecent)
      .catch(() => setRecent([]))
      .finally(() => setRecentLoading(false));
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) {
      router.push('/agent');
      return;
    }
    router.push(`/agent?q=${encodeURIComponent(text)}&autosend=1`);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* Hero area */}
      <div
        className="px-7 pt-[34px] pb-[18px] border-b-[1.5px] border-[var(--color-ink3)]"
        style={{ background: 'var(--color-paper2)' }}
      >
        <h1 className="font-bold text-[30px] tracking-[-0.02em] mb-[6px]">
          무엇을 <span className="bg-[var(--color-hl)] px-1">자동화</span>할까요?
        </h1>
        <p className="text-[var(--color-ink3)] text-[14px] mb-[14px]">
          {userDisplay} · 자연어로 그냥 말씀해주세요.
        </p>

        {/* Large input */}
        <form
          onSubmit={handleSubmit}
          className="flex items-center gap-3 border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[18px] py-[10px] bg-[var(--color-surface)]"
          style={{ boxShadow: '3px 4px 0 var(--color-ink)' }}
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="매주 월요일 9시에 광고 시트…"
            className="flex-1 text-[18px] bg-transparent focus:outline-none placeholder:text-[var(--color-ink4)]"
            aria-label="워크플로우 자연어 설명"
          />
          <span className="font-mono text-[var(--color-ink3)] text-[12px]">⌘ + K</span>
          <Btn primary type="submit" className="text-[13px]">
            전송 ↑
          </Btn>
        </form>

        {/* Quick chips */}
        <div className="flex gap-2 mt-3 flex-wrap">
          {QUICK_CHIPS.map((chip) => (
            <Link
              key={chip}
              href={`/agent?q=${encodeURIComponent(chip)}&autosend=1`}
              className="text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[8px] py-[3px] bg-[var(--color-surface)] hover:bg-[var(--color-paper2)] no-underline text-[var(--color-ink)]"
            >
              {chip}
            </Link>
          ))}
          <Link
            href="/marketplace"
            className="text-[13px] text-[var(--color-ink4)] px-[8px] py-[3px] no-underline hover:text-[var(--color-ink3)]"
          >
            + 더 보기
          </Link>
        </div>
      </div>

      {/* Bottom 2-column content */}
      <div className="flex-1 grid grid-cols-2 gap-3 p-5">
        {/* Left: 이어서 작업 */}
        <div>
          <div className="text-[13px] text-[var(--color-ink3)] mb-[6px]">이어서 작업</div>
          <div className="flex flex-col gap-2">
            {recentLoading && (
              <>
                <Skel className="h-[36px] w-full" />
                <Skel className="h-[36px] w-full" />
              </>
            )}
            {!recentLoading && recent.length === 0 && (
              <div className="text-[13px] text-[var(--color-ink4)] border-[1.5px] border-dashed border-[var(--color-ink4)] rounded-[5px_11px_6px_10px] px-[10px] py-[14px] text-center">
                아직 만든 워크플로우가 없어요.<br />
                위 입력창에서 시작해보세요.
              </div>
            )}
            {!recentLoading &&
              recent.map((wf) => (
                <Link
                  key={wf.workflow_id}
                  href={`/workflows/${wf.workflow_id}`}
                  className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[6px] bg-[var(--color-surface)] no-underline hover:bg-[var(--color-paper2)]"
                >
                  <span className="font-bold text-[var(--color-ink)]">{wf.name}</span>
                  <span className="text-[11px] text-[var(--color-ink3)]">
                    {wf.is_draft ? '초안' : '활성'}
                  </span>
                </Link>
              ))}
          </div>
        </div>

        {/* Right: 알림 */}
        <div>
          <div className="text-[13px] text-[var(--color-ink3)] mb-[6px]">바로가기</div>
          <div className="flex flex-col gap-2">
            <Link
              href="/agent"
              className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[6px] bg-[var(--color-surface)] no-underline hover:bg-[var(--color-paper2)]"
            >
              <span className="text-[var(--color-ink)]">💬 새 대화 시작</span>
              <span className="font-mono text-[13px] text-[var(--color-ink3)]">→</span>
            </Link>
            <Link
              href="/workflows"
              className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[6px] bg-[var(--color-surface)] no-underline hover:bg-[var(--color-paper2)]"
            >
              <span className="text-[var(--color-ink)]">📂 워크플로우 목록</span>
              <span className="font-mono text-[13px] text-[var(--color-ink3)]">→</span>
            </Link>
            <Link
              href="/marketplace"
              className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[6px] bg-[var(--color-surface)] no-underline hover:bg-[var(--color-paper2)]"
            >
              <span className="text-[var(--color-ink)]">🛒 스킬 마켓플레이스</span>
              <span className="font-mono text-[13px] text-[var(--color-ink3)]">→</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
