'use client';

import { useAuth } from '@/hooks/useAuth';
import { useAuthStore } from '@/stores/authStore';
import Btn from '@/components/common/Btn';

export default function SettingsSecurityPage() {
  const { logout } = useAuth();
  const { isAuthenticated } = useAuthStore();

  return (
    <>
      <div className="font-bold text-[16px] mb-[2px]">보안</div>
      <div className="text-[13px] text-[var(--color-ink3)] mb-3">세션 관리</div>

      <div className="flex flex-col gap-2">
        <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[8px] bg-[var(--color-surface)]">
          <div className="flex items-center justify-between">
            <span>
              <div className="font-bold text-[13px]">현재 세션</div>
              <div className="text-[11px] text-[var(--color-ink3)]">HttpOnly 쿠키 기반 인증</div>
            </span>
            <span className="text-[11px] px-[6px] py-0 border border-[var(--color-ink4)] rounded text-[var(--color-ink3)]">
              {isAuthenticated ? '활성' : '—'}
            </span>
          </div>
        </div>

        <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[8px] bg-[var(--color-surface)] flex items-center justify-between">
          <span>
            <div className="font-bold text-[13px]">로그아웃</div>
            <div className="text-[11px] text-[var(--color-ink3)]">서버 세션 revoke 포함</div>
          </span>
          <Btn danger onClick={logout}>로그아웃</Btn>
        </div>
      </div>
    </>
  );
}
