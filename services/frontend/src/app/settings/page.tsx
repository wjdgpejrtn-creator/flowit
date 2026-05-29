'use client';

import { useAuthStore } from '@/stores/authStore';

const ROWS = (
  userName: string | null,
  dept: string | null,
  role: string,
  userId: string | null,
) => [
  { label: '표시 이름', value: userName || '사용자', note: userName ? '' : '— 이메일 연동 후 자동 설정' },
  { label: '부서 ID', value: dept || '—', mono: true },
  { label: '역할', value: role },
  { label: '사용자 ID', value: userId || '—', mono: true },
];

export default function SettingsProfilePage() {
  const { userName, dept, role, userId } = useAuthStore();

  return (
    <>
      <div className="font-bold text-[16px] mb-[2px]">프로필</div>
      <div className="text-[13px] text-[var(--color-ink3)] mb-3">이름·부서·역할 정보</div>

      <div className="flex flex-col gap-2">
        {ROWS(userName, dept, role, userId).map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[8px] bg-[var(--color-surface)]"
          >
            <span className="text-[13px] text-[var(--color-ink3)]">{row.label}</span>
            <span className="flex items-center gap-2">
              {row.note && (
                <span className="text-[11px] text-[var(--color-ink4)]">{row.note}</span>
              )}
              <span className={`text-[13px] font-bold${row.mono ? ' font-mono' : ''}`}>
                {row.value}
              </span>
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
