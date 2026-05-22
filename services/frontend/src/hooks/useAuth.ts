'use client';

import { useCallback } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { getAuthorizeUrl, me } from '@/lib/api/authApi';

export function useAuth() {
  const { isAuthenticated, userId, userName, dept, role, setAuth, clearAuth } = useAuthStore();

  const initFromRefreshToken = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/auth/refresh', { method: 'POST' });
      if (!res.ok) return false;
      const user = await me();
      setAuth({
        role: user.role === 'Admin' ? 'Admin' : 'User',
        userId: user.user_id,
        userName: user.email.split('@')[0],
        dept: user.dept ?? '',
      });
      return true;
    } catch {
      return false;
    }
  }, [setAuth]);

  const startGoogleLogin = useCallback(async () => {
    const { authorization_url } = await getAuthorizeUrl();
    window.location.href = authorization_url;
  }, []);

  const logout = useCallback(async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    clearAuth();
    window.location.href = '/login';
  }, [clearAuth]);

  return { isAuthenticated, userId, userName, dept, role, initFromRefreshToken, startGoogleLogin, logout };
}
