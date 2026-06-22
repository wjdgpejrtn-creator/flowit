'use client';

import { useEffect, useState } from 'react';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import { getAuthorizeUrl } from '@/lib/api/authApi';
import { consumePendingToast } from '@/lib/pendingToast';

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [logoFailed, setLogoFailed] = useState(false);
  const [badgeFailed, setBadgeFailed] = useState(false);

  // 로그아웃 등 전체 이동 후 도착 시 보류 토스트 1회 표시
  useEffect(() => {
    const msg = consumePendingToast();
    if (msg) showToast(msg);
  }, []);

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
    <section className="login-bg fixed inset-0 z-[60] overflow-y-auto">
      <div className="flex flex-col items-center justify-center min-h-screen px-4 py-12 animate-fade-in">
        {/* 로고 (수달 + 태그라인) */}
        <div className="text-center mb-9">
          {logoFailed ? (
            <span className="text-6xl">🦦</span>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src="/images/flowit-logo-v2.png"
              alt="Flowit — 똑똑한 업무 자동화, 플로잇"
              className="h-28 md:h-32 object-contain mx-auto select-none"
              draggable={false}
              onError={() => setLogoFailed(true)}
            />
          )}
        </div>

        {/* 로그인 카드 */}
        <div className="w-full max-w-xl bg-white rounded-[28px] p-8 md:p-10 shadow-[0_24px_60px_-24px_rgba(70,58,48,0.28)] border border-line-soft/70">
          <div className="space-y-1.5 mb-7">
            <span className="block text-[11px] font-bold text-ink3 uppercase tracking-[0.22em]">
              LOGIN
            </span>
            <h2 className="text-xl font-bold text-ink flex items-center gap-2">
              {!badgeFailed && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src="/images/idcard-badge.png"
                  alt=""
                  className="w-6 h-6 object-contain flex-shrink-0"
                  onError={() => setBadgeFailed(true)}
                />
              )}
              <span>사내계정</span>
            </h2>
          </div>

          <div className="space-y-3">
            <button
              type="button"
              onClick={() => void handleGoogleLogin()}
              disabled={loading}
              className="group w-full flex items-center justify-center gap-3 px-6 py-4 rounded-2xl bg-accent3 hover:bg-ink text-white transition-all shadow-[0_8px_18px_-8px_rgba(70,58,48,0.55)] hover:-translate-y-0.5 disabled:opacity-60 disabled:hover:translate-y-0"
            >
              <span className="w-9 h-9 rounded-full bg-white flex items-center justify-center shadow-sm flex-shrink-0">
                <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" aria-hidden="true">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.76h3.56c2.08-1.92 3.28-4.74 3.28-8.09Z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.76c-.98.66-2.23 1.06-3.72 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
                  <path fill="#FBBC05" d="M5.84 14.09a6.6 6.6 0 0 1 0-4.18V7.07H2.18a11 11 0 0 0 0 9.86l3.66-2.84Z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38Z" />
                </svg>
              </span>
              <span className="text-base font-semibold leading-none">
                {loading ? '연결 중…' : 'Google 로그인'}
              </span>
            </button>

            <button
              type="button"
              onClick={() => showToast('네이버 로그인은 준비 중입니다.')}
              className="group w-full flex items-center justify-center gap-3 px-6 py-4 rounded-2xl bg-accent3 hover:bg-ink text-white transition-all shadow-[0_8px_18px_-8px_rgba(70,58,48,0.55)] hover:-translate-y-0.5"
            >
              <span className="w-9 h-9 rounded-lg bg-[#03C75A] flex items-center justify-center shadow-sm flex-shrink-0">
                <span className="text-white font-black text-base leading-none">N</span>
              </span>
              <span className="text-base font-semibold leading-none">Naver 로그인</span>
            </button>
          </div>

          {error && (
            <p className="mt-4 text-xs font-bold text-danger flex items-center justify-center gap-1.5">
              <Icon name="alert-triangle" className="w-3.5 h-3.5" />
              {error}
            </p>
          )}

          <div className="border-t border-line-soft mt-6 pt-5">
            <p className="text-xs text-ink4 font-bold flex items-center justify-center gap-1.5">
              <Icon name="lock" className="w-3.5 h-3.5" />
              로그인 시 인증 쿠키 HttpOnly로 안전하게 저장됩니다.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
