import { apiFetch, apiJson } from '@/lib/apiClient';

export interface AgentSession {
  session_id: string;
  langgraph_thread_id: string;
}

export interface AgentMessageRequest {
  message: string;
  session_id?: string;
}

// REQ-009 spec 경로: /api/v1/agents/sessions (신정혜님 REQ-004)
export async function createSession(req: AgentMessageRequest): Promise<AgentSession> {
  return apiJson<AgentSession>('/api/v1/agents/sessions', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// 상대 경로 — 단일 출처 원칙 준수 (ADR-0021), 쿠키 자동 전송
export function getStreamUrl(sessionId: string): string {
  return `/api/v1/ai/sessions/${sessionId}/stream`;
}

// 슬롯 필링 응답 전송
export async function sendSlotAnswer(sessionId: string, fieldName: string, value: string): Promise<void> {
  await apiFetch(`/api/v1/agents/sessions/${sessionId}/slot`, {
    method: 'POST',
    body: JSON.stringify({ field_name: fieldName, value }),
  });
}
