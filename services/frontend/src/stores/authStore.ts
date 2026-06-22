import { create } from 'zustand';

export type Role = 'User' | 'team_manager' | 'company_manager' | 'Admin';

interface AuthState {
  role: Role;
  userId: string | null;
  userName: string | null;
  // 로그인 사용자 이메일. name 미설정 시 화면 fallback(이메일 앞부분 표시)용. /auth/me가 내려줌.
  email: string | null;
  dept: string | null;
  isAuthenticated: boolean;
  setAuth: (payload: { role: Role; userId: string; userName: string; email: string; dept: string }) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  role: 'User',
  userId: null,
  userName: null,
  email: null,
  dept: null,
  isAuthenticated: false,
  setAuth: ({ role, userId, userName, email, dept }) =>
    set({ role, userId, userName, email, dept, isAuthenticated: true }),
  clearAuth: () =>
    set({ role: 'User', userId: null, userName: null, email: null, dept: null, isAuthenticated: false }),
}));

// 외부에서 현재 userName을 동기적으로 읽을 수 있는 셀렉터
export const selectUserDisplay = (state: AuthState): string => {
  if (!state.isAuthenticated || !state.userName) return '사용자';
  return state.dept ? `${state.userName}님 · ${state.dept}` : `${state.userName}님`;
};
