import { apiJson } from '@/lib/apiClient';
import type { WorkflowSchema, ValidationErrorResponse } from '@common/generated';

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
