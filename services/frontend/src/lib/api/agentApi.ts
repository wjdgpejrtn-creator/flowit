import { apiFetch, apiJson } from '@/lib/apiClient';

export interface AgentSession {
  session_id: string;
  langgraph_thread_id: string;
}

export interface AgentMessageRequest {
  message: string;
  session_id?: string;
}

// /api/v1/ai/compose SSE 스트리밍 세션 생성
// 백엔드 엔드포인트 구현 후 활성화 (신정혜님 REQ-004)
export async function createSession(req: AgentMessageRequest): Promise<AgentSession> {
  return apiJson<AgentSession>('/api/v1/ai/sessions', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// SSE 스트리밍 URL 반환 — useSSEStream 훅에 전달
export function getStreamUrl(sessionId: string): string {
  const base = process.env.NEXT_PUBLIC_SSE_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  return `${base}/api/v1/ai/sessions/${sessionId}/stream`;
}

// 슬롯 필링 응답 전송
export async function sendSlotAnswer(sessionId: string, fieldName: string, value: string): Promise<void> {
  await apiFetch(`/api/v1/ai/sessions/${sessionId}/slot`, {
    method: 'POST',
    body: JSON.stringify({ field_name: fieldName, value }),
  });
}
