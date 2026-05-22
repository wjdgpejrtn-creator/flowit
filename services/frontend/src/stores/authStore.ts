import { create } from 'zustand';

export type Role = 'User' | 'Admin';

interface AuthState {
  role: Role;
  userId: string | null;
  userName: string | null;
  dept: string | null;
  isAuthenticated: boolean;
  setAuth: (payload: { role: Role; userId: string; userName: string; dept: string }) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  role: 'User',
  userId: null,
  userName: null,
  dept: null,
  isAuthenticated: false,
  setAuth: ({ role, userId, userName, dept }) =>
    set({ role, userId, userName, dept, isAuthenticated: true }),
  clearAuth: () =>
    set({ role: 'User', userId: null, userName: null, dept: null, isAuthenticated: false }),
}));

// 외부에서 현재 userName을 동기적으로 읽을 수 있는 셀렉터
export const selectUserDisplay = (state: AuthState): string => {
  if (!state.isAuthenticated || !state.userName) return '사용자';
  return state.dept ? `${state.userName}님 · ${state.dept}` : `${state.userName}님`;
};
