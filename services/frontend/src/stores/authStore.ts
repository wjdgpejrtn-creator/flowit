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
