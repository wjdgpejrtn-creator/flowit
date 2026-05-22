'use client';

import { useState } from 'react';
import Btn from '@/components/common/Btn';
import ErrorBanner from '@/components/common/ErrorBanner';
import { getAuthorizeUrl } from '@/lib/api/authApi';

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleGoogleLogin = async () => {
    setLoading(true);
    setError('');
    try {
      const { authorization_url } = await getAuthorizeUrl();
      window.location.href = authorization_url;
    } catch {
      setError('로그인 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-[var(--color-paper2)]">
      {/* Left: copy */}
      <div
        className="flex flex-col justify-center gap-[14px] p-10 border-r-[1.5px] border-[var(--color-ink3)]"
        style={{ flex: '1.1' }}
      >
        <div className="font-bold text-[22px] tracking-[-0.02em]">∿ flow</div>
        <div className="font-bold text-[18px] leading-[1.4] font-normal">
          자연어로 <span className="bg-[var(--color-hl)] px-1">업무 자동화</span>를<br />
          요청하세요.
        </div>
        <div className="text-[14px] text-[var(--color-ink3)] leading-[1.55]">
          AI 에이전트가 56종 노드로<br />
          워크플로우를 조립합니다.
        </div>
        <div className="font-mono text-[var(--color-ink4)] mt-[14px] text-[12px]">v1.0 · 베타</div>
      </div>

      {/* Right: login form */}
      <div
        className="flex flex-col justify-center gap-3 p-[30px_24px]"
        style={{ flex: '1' }}
      >
        <div className="text-[12px] text-[var(--color-ink3)] font-medium">로그인</div>
        <Btn lg primary onClick={() => void handleGoogleLogin()} disabled={loading}>
          {loading ? '연결 중…' : '🇬 Google로 로그인'}
        </Btn>
        <div className="text-[13px] text-[var(--color-ink3)]">
          사내 도메인:{' '}
          <span className="font-mono text-[var(--color-ink)]">@naver.com</span>
        </div>

        {error && (
          <ErrorBanner>
            <span>⚠</span>
            <span>{error}</span>
          </ErrorBanner>
        )}

        <div className="mt-[14px] h-[1.5px] bg-[var(--color-ink3)] rounded" />
        <div className="text-[11px] text-[var(--color-ink3)]">
          로그인 시 인증 쿠키가 HttpOnly로 안전하게 저장됩니다.
        </div>
      </div>
    </div>
  );
}
