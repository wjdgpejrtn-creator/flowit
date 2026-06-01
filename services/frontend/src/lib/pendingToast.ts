/**
 * 전체 페이지 이동(window.location) 직후에도 토스트를 1회 보여주기 위한 보류 토스트.
 *
 * 로그아웃은 서버 세션 revoke + window.location.href='/login' 전체 이동이라
 * 이동 전에 showToast() 해도 페이지가 리로드되며 사라진다. 그래서 메시지를
 * sessionStorage 에 잠시 적어두고, 도착 페이지(로그인)에서 1회 소비해 표시한다.
 */
const KEY = 'flowit_pending_toast';

export function setPendingToast(message: string): void {
  try {
    sessionStorage.setItem(KEY, message);
  } catch {
    /* sessionStorage 불가 환경 — 무시 */
  }
}

export function consumePendingToast(): string | null {
  try {
    const v = sessionStorage.getItem(KEY);
    if (v) sessionStorage.removeItem(KEY);
    return v;
  } catch {
    return null;
  }
}
