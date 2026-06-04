import { apiJson } from '@/lib/apiClient';
import type { WorkflowSchema, ValidationErrorResponse, ExecutionStatus } from '@common/generated';

export interface ExecuteRequest {
  trigger_type?: string;
  parameters?: Record<string, unknown>;
}

export interface ExecuteResponse {
  execution_id: string;
  status: string;
  task_id: string;
}

export interface ControlResponse {
  execution_id: string;
  action: string;
  task_id: string;
}

export interface NodeResultEntry {
  node_instance_id: string;
  // 'skipped' = L2 조건 분기에서 안 탄 가지 노드(execution_engine `_skipped_result`, ADR-0023).
  // execution_engine이 save하는 NodeResult.status 기준 — 백엔드가 raw list[dict]로 반환한다.
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'retrying' | 'cancelled' | 'skipped';
  attempt?: number;
  last_error?: string | null;
}

export interface WorkflowLatestExecution {
  execution_id: string;
  workflow_id: string;
  status: ExecutionStatus;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  node_states_summary: Record<string, number>;
  node_results: NodeResultEntry[];
}

export async function listWorkflows(limit = 50, offset = 0): Promise<WorkflowSchema[]> {
  return apiJson<WorkflowSchema[]>(`/api/v1/workflows?limit=${limit}&offset=${offset}`);
}

export async function getWorkflow(id: string): Promise<WorkflowSchema> {
  return apiJson<WorkflowSchema>(`/api/v1/workflows/${id}`);
}

export async function createWorkflow(data: WorkflowSchema): Promise<WorkflowSchema> {
  return apiJson<WorkflowSchema>('/api/v1/workflows', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateWorkflow(id: string, data: WorkflowSchema): Promise<WorkflowSchema> {
  return apiJson<WorkflowSchema>(`/api/v1/workflows/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function validateWorkflow(id: string): Promise<ValidationErrorResponse> {
  return apiJson<ValidationErrorResponse>(`/api/v1/workflows/${id}/validate`, {
    method: 'POST',
  });
}

export async function executeWorkflow(id: string, req: ExecuteRequest = {}): Promise<ExecuteResponse> {
  return apiJson<ExecuteResponse>(`/api/v1/workflows/${id}/execute`, {
    method: 'POST',
    body: JSON.stringify({ trigger_type: req.trigger_type ?? 'manual', parameters: req.parameters ?? {} }),
  });
}

export async function cancelExecution(executionId: string): Promise<ControlResponse> {
  return apiJson<ControlResponse>(`/api/v1/executions/${executionId}/cancel`, { method: 'POST' });
}

export async function resumeExecution(executionId: string): Promise<ControlResponse> {
  return apiJson<ControlResponse>(`/api/v1/executions/${executionId}/resume`, { method: 'POST' });
}

export async function getLatestExecution(
  workflowId: string,
): Promise<WorkflowLatestExecution | null> {
  return apiJson<WorkflowLatestExecution | null>(
    `/api/v1/workflows/${workflowId}/executions/latest`,
  );
}
