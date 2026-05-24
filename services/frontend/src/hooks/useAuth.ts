'use client';

import { useCallback } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { getAuthorizeUrl, me } from '@/lib/api/authApi';

export function useAuth() {
  const { isAuthenticated, userId, userName, dept, role, setAuth, clearAuth } = useAuthStore();

  const initFromRefreshToken = useCallback(async (): Promise<boolean> => {
    try {
      // BFF 래퍼 제거 — 백엔드 /api/v1/auth/refresh 직접 호출 (ADR-0021)
      // 쿠키는 백엔드가 Set-Cookie로 갱신, 응답 본문은 { expires_in } 뿐
      const res = await fetch('/api/v1/auth/refresh', { method: 'POST' });
      if (!res.ok) return false;

      // PermissionSource 반환 — email/dept 미제공 (백엔드 /auth/me 확장 결정 대기)
      const user = await me();
      setAuth({
        role: user.role,
        userId: user.user_id,
        userName: '',          // 백엔드 /auth/me에 email 추가 후 교체 예정
        dept: user.department_id,
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
    // BFF 래퍼 제거 — 백엔드 /api/v1/auth/logout 직접 호출 (ADR-0021, 서버 세션 revoke 포함)
    await fetch('/api/v1/auth/logout', { method: 'POST' });
    clearAuth();
    window.location.href = '/login';
  }, [clearAuth]);

  return { isAuthenticated, userId, userName, dept, role, initFromRefreshToken, startGoogleLogin, logout };
}
