import { create } from 'zustand';

/** 시안(Flowit.html)의 resolveToastIcon() 포팅 — 메시지 내용으로 lucide 아이콘 추론 */
export function resolveToastIcon(msg: string): string {
  const m = String(msg);
  if (/환영|로그인|입장/.test(m)) return 'log-in';
  if (/로그아웃/.test(m)) return 'log-out';
  if (/알림이 없/.test(m)) return 'bell-off';
  if (/알림이 있|새 알림/.test(m)) return 'bell';
  if (/프로필/.test(m)) return 'folder-check';
  if (/입력해\s?주세요|작성해\s?주세요/.test(m)) return 'file-pen-line';
  if (/연결|연동/.test(m)) return 'link-2';
  if (/전송|발송|보냈/.test(m)) return 'send';
  if (/업로드/.test(m)) return 'upload-cloud';
  if (/제거|삭제|로그아웃했/.test(m)) return 'trash-2';
  if (/추가|등록|생성|시작/.test(m)) return 'plus-circle';
  if (/설계|자동화/.test(m)) return 'sparkles';
  if (/비밀번호/.test(m)) return 'key-round';
  if (/저장|완료|설정/.test(m)) return 'check-circle-2';
  return 'bell';
}

interface ToastState {
  message: string;
  icon: string;
  /** show() 호출마다 증가 — Toaster가 동일 메시지 반복 표시 시에도 타이머를 리셋하도록 */
  nonce: number;
  visible: boolean;
  show: (message: string, icon?: string) => void;
  hide: () => void;
}

export const useToastStore = create<ToastState>((set, get) => ({
  message: '',
  icon: 'bell',
  nonce: 0,
  visible: false,
  show: (message, icon) =>
    set({
      message,
      icon: icon || resolveToastIcon(message),
      nonce: get().nonce + 1,
      visible: true,
    }),
  hide: () => set({ visible: false }),
}));

/**
 * 컴포넌트 밖(이벤트 핸들러·유틸)에서도 호출 가능한 토스트 트리거.
 * 시안의 전역 showToast(message, icon) 와 동일한 시그니처.
 */
export function showToast(message: string, icon?: string): void {
  useToastStore.getState().show(message, icon);
}
