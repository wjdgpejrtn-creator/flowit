'use client';

import { useEffect, useRef } from 'react';
import { useToastStore } from '@/stores/toastStore';
import Icon from './Icon';

const AUTO_HIDE_MS = 3000;

/**
 * 전역 토스트. 시안(Flowit.html)의 #toast 마크업·동작을 포팅.
 * layout.tsx 에 1회 마운트되어 showToast()/useToastStore 로 트리거된다.
 */
export default function Toaster() {
  const { message, icon, visible, nonce, hide } = useToastStore();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!visible) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => hide(), AUTO_HIDE_MS);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // nonce 가 바뀔 때마다(=show() 호출마다) 타이머를 리셋
  }, [visible, nonce, hide]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={[
        'fixed bottom-6 right-6 z-[80] flex items-center gap-4 bg-accent3 pl-5 pr-7 py-4',
        'rounded-[22px] shadow-[0_14px_34px_-10px_rgba(70,52,35,.55)]',
        'transition-all duration-300 ease-out',
        visible
          ? 'translate-y-0 opacity-100'
          : 'translate-y-12 opacity-0 pointer-events-none',
      ].join(' ')}
    >
      <span className="flex items-center justify-center flex-shrink-0 text-white">
        <Icon name={icon} className="w-8 h-8" />
      </span>
      <p className="text-base font-bold text-white whitespace-nowrap leading-snug">{message}</p>
    </div>
  );
}
