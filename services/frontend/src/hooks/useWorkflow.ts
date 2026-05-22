'use client';

import { useState, useCallback } from 'react';
import * as workflowApi from '@/lib/api/workflowApi';
import type { WorkflowSchema } from '@common/generated';

export function useWorkflow() {
  const [workflow, setWorkflow] = useState<WorkflowSchema | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await workflowApi.getWorkflow(id);
      setWorkflow(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : '워크플로우 조회 실패');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const save = useCallback(async (data: WorkflowSchema) => {
    setLoading(true);
    setError(null);
    try {
      const result = data.workflow_id
        ? await workflowApi.updateWorkflow(String(data.workflow_id), data)
        : await workflowApi.createWorkflow(data);
      setWorkflow(result);
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장 실패');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const execute = useCallback(async (id: string, req: workflowApi.ExecuteRequest = {}) => {
    setLoading(true);
    setError(null);
    try {
      return await workflowApi.executeWorkflow(id, req);
    } catch (e) {
      setError(e instanceof Error ? e.message : '실행 요청 실패');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { workflow, loading, error, load, save, execute };
}
