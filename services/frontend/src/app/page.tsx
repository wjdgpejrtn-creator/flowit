'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Skel from '@/components/common/Skel';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import { useAuthStore } from '@/stores/authStore';
import { listWorkflows } from '@/lib/api/workflowApi';
import type { WorkflowSchema } from '@common/generated';

const QUICK_CHIPS: { icon: string; label: string; prompt: string }[] = [
  { icon: 'bar-chart-2', label: '광고 리포트', prompt: '광고 리포트 매주 월요일 자동 취합 및 발송' },
  { icon: 'file-text', label: 'PDF 처리', prompt: '계약서 PDF 정보 자동 추출 및 ERP 등록' },
  { icon: 'message-square', label: 'Slack 알림', prompt: 'Slack 채널로 일일 알림 보내기' },
];
const RECENT_LIMIT = 5;

const SHORTCUTS: { href: string; icon: string; label: string }[] = [
  { href: '/agent', icon: 'message-square', label: '새 대화 시작' },
  { href: '/workflows', icon: 'folder', label: '워크플로우 목록' },
  { href: '/marketplace', icon: 'store', label: '스킬 마켓플레이스' },
];

export default function DashboardPage() {
  const router = useRouter();
  const { userName, email } = useAuthStore();
  const displayName = userName || email?.split('@')[0] || '사용자';

  const [input, setInput] = useState('');
  const [recent, setRecent] = useState<WorkflowSchema[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [otterFailed, setOtterFailed] = useState(false);
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
      showToast('자동화할 작업을 입력해 주세요!');
      inputRef.current?.focus();
      return;
    }
    showToast('자동화 설계를 시작합니다...');
    // 시안 submitPrompt: 토스트 후 0.8초 연출 뒤 AI채팅 이동
    setTimeout(() => {
      router.push(`/agent?q=${encodeURIComponent(text)}&autosend=1`);
    }, 800);
  };

  const autofill = (prompt: string) => {
    setInput(prompt);
    showToast('추천 템플릿이 입력되었습니다.');
    inputRef.current?.focus();
  };

  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />

      <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-6">
        {/* Hero */}
        <div className="py-8 text-center max-w-2xl mx-auto space-y-4 relative">
          <div className="absolute top-[68px] right-10 md:right-24 z-10 w-14">
            <span
              className="absolute -top-3 right-0.5 font-black text-lg leading-none text-accent-coral"
              aria-hidden="true"
            >
              ?
            </span>
            {otterFailed ? (
              <span className="text-3xl block">🦦</span>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src="/images/otter-doc.png"
                alt="수달"
                className="w-14 h-auto block"
                style={{ transform: 'scaleX(0.92)' }}
                onError={() => setOtterFailed(true)}
              />
            )}
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-ink pt-6 md:pt-2">
            무엇을 <span className="text-accent-coral">자동화할까요?</span>
          </h1>
          <p className="text-sm text-ink3 font-bold">
            <strong className="text-ink font-bold">{displayName}님</strong> · 자연어로 말씀해주세요.
          </p>
        </div>

        {/* Input */}
        <div className="max-w-4xl mx-auto">
          <form
            onSubmit={handleSubmit}
            className="bg-white rounded-2xl border border-line-soft p-2.5 shadow-md focus-within:border-accent focus-within:ring-4 focus-within:ring-accent-coral/10 transition-all"
          >
            <div className="flex items-center space-x-3 px-3">
              <Icon name="sparkles" className="w-5 h-5 text-accent-coral animate-pulse flex-shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="매주 월요일 9시에 광고 시트 정리하고 Slack으로 리포트 보내줘..."
                aria-label="워크플로우 자연어 설명"
                className="flex-1 bg-transparent text-ink placeholder-ink4 border-none outline-none py-3 text-base font-bold min-w-[200px]"
              />
              <button
                type="submit"
                className="bg-accent hover:bg-accent3 text-white px-5 py-2.5 rounded-xl font-bold flex items-center space-x-1.5 transition-all shadow-md flex-shrink-0"
              >
                <span>전송</span>
                <Icon name="arrow-up" className="w-4 h-4" />
              </button>
            </div>
          </form>

          {/* Quick chips */}
          <div className="flex flex-wrap gap-2 mt-4 justify-center">
            {QUICK_CHIPS.map((chip) => (
              <button
                key={chip.label}
                type="button"
                onClick={() => autofill(chip.prompt)}
                className="px-4 py-2 rounded-full border border-line-soft bg-white text-xs font-bold text-ink hover:bg-hl hover:border-accent-coral transition-all flex items-center space-x-1.5 shadow-sm"
              >
                <Icon name={chip.icon} className="w-3.5 h-3.5 text-accent-coral" />
                <span>{chip.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 2-column */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-5xl mx-auto pt-6">
          {/* 이어서 작업 */}
          <div className="lg:col-span-7 space-y-3">
            <h3 className="text-sm font-bold text-ink flex items-center space-x-2">
              <Icon name="clock" className="w-4 h-4 text-accent-coral" />
              <span>이어서 작업</span>
            </h3>

            {recentLoading && (
              <div className="space-y-2">
                <Skel h={60} className="rounded-2xl" />
                <Skel h={60} className="rounded-2xl" />
              </div>
            )}

            {!recentLoading && recent.length === 0 && (
              <div className="flowit-card rounded-2xl p-8 text-center flex flex-col items-center justify-center min-h-[220px]">
                <div className="w-14 h-14 rounded-full bg-paper text-accent flex items-center justify-center mb-3 shadow-inner flex-shrink-0">
                  <Icon name="calendar-range" className="w-7 h-7" />
                </div>
                <p className="text-sm font-bold text-ink">진행 중인 자동화 워크플로우가 없습니다.</p>
                <p className="text-xs text-ink3 font-bold mt-1">위 입력창에서 자연어로 시작해보세요.</p>
                <Link
                  href="/agent"
                  className="mt-4 px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-white text-xs font-bold rounded-xl transition-all no-underline"
                >
                  예시 워크플로우 만들기
                </Link>
              </div>
            )}

            {!recentLoading && recent.length > 0 && (
              <div className="space-y-2.5">
                {recent.map((wf) => (
                  <Link
                    key={wf.workflow_id}
                    href={`/workflows/${wf.workflow_id}`}
                    className="flex items-center justify-between p-4 rounded-xl bg-white border border-line-soft hover:border-accent-coral hover:bg-hl transition-all shadow-sm no-underline"
                  >
                    <div className="flex items-center space-x-3">
                      <Icon name="workflow" className="w-5 h-5 text-accent" />
                      <span className="text-sm font-bold text-ink">{wf.name}</span>
                    </div>
                    <span className="text-[11px] text-ink3 font-bold">
                      {wf.is_draft ? '초안' : '활성'}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* 바로가기 */}
          <div className="lg:col-span-5 space-y-3">
            <h3 className="text-sm font-bold text-ink flex items-center space-x-2">
              <Icon name="compass" className="w-4 h-4 text-accent-coral" />
              <span>바로가기</span>
            </h3>
            <div className="space-y-2.5">
              {SHORTCUTS.map((s) => (
                <Link
                  key={s.href}
                  href={s.href}
                  className="flex items-center justify-between p-4 rounded-xl bg-white border border-line-soft hover:border-accent-coral hover:bg-hl transition-all shadow-sm no-underline"
                >
                  <div className="flex items-center space-x-3">
                    <Icon name={s.icon} className="w-5 h-5 text-accent" />
                    <span className="text-sm font-bold text-ink">{s.label}</span>
                  </div>
                  <Icon name="arrow-right" className="w-4 h-4 text-ink3" />
                </Link>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
