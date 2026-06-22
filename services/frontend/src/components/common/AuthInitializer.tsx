'use client';

import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';

export default function AuthInitializer() {
  const { isAuthenticated, initFromRefreshToken } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      void initFromRefreshToken();
    }
  }, [isAuthenticated, initFromRefreshToken]);

  return null;
}
