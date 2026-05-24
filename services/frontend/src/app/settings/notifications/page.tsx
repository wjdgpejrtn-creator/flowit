'use client';

import { useState } from 'react';

interface NotifItem {
  id: string;
  label: string;
  desc: string;
}

const ITEMS: NotifItem[] = [
  { id: 'workflow_done',   label: '워크플로우 완료',      desc: '실행이 정상 완료될 때 알림' },
  { id: 'workflow_fail',   label: '워크플로우 실패',      desc: '실행 중 오류 발생 시 알림' },
  { id: 'token_expiry',    label: '토큰 만료 임박',       desc: '연결된 서비스 토큰이 7일 이내 만료될 때 알림' },
  { id: 'session_expired', label: '세션 만료',            desc: '로그인 세션이 만료될 때 알림' },
];

function Toggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onToggle}
      className="relative inline-flex h-[20px] w-[36px] shrink-0 cursor-pointer items-center rounded-full border-[1.5px] border-[var(--color-ink)] transition-colors"
      style={{ backgroundColor: on ? 'var(--color-ink)' : 'var(--color-surface)' }}
    >
      <span
        className="inline-block h-[12px] w-[12px] rounded-full transition-transform"
        style={{
          backgroundColor: on ? 'var(--color-paper)' : 'var(--color-ink3)',
          transform: on ? 'translateX(18px)' : 'translateX(2px)',
        }}
      />
    </button>
  );
}

export default function SettingsNotificationsPage() {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({
    workflow_done: true,
    workflow_fail: true,
    token_expiry: true,
    session_expired: false,
  });

  const toggle = (id: string) =>
    setEnabled((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <>
      <div className="font-bold text-[16px] mb-[2px]">알림</div>
      <div className="text-[13px] text-[var(--color-ink3)] mb-3">워크플로우 완료·실패·만료 임박 알림 설정</div>

      <div className="flex flex-col gap-2">
        {ITEMS.map((item) => (
          <div
            key={item.id}
            className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[8px] bg-[var(--color-surface)]"
          >
            <span>
              <div className="font-bold text-[13px]">{item.label}</div>
              <div className="text-[11px] text-[var(--color-ink3)]">{item.desc}</div>
            </span>
            <Toggle on={!!enabled[item.id]} onToggle={() => toggle(item.id)} />
          </div>
        ))}
      </div>
    </>
  );
}
