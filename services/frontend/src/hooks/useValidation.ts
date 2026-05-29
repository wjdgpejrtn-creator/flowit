'use client';

import { useState, useCallback } from 'react';
import { validateWorkflow } from '@/lib/api/workflowApi';
import type { ValidationErrorResponse } from '@common/generated';

export function useValidation() {
  const [result, setResult] = useState<ValidationErrorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validate = useCallback(async (workflowId: string) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await validateWorkflow(workflowId);
      setResult(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : '검증 요청 실패');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const hasErrors = result ? (result.errors?.length ?? 0) > 0 : false;

  return { result, loading, error, hasErrors, validate };
}
