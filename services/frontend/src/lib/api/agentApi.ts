import { apiFetch } from '@/lib/apiClient';

export interface AgentSession {
  session_id: string;
  langgraph_thread_id: string;
}

export interface AgentMessageRequest {
  message: string;
  session_id?: string;
}

export async function streamCreateSession(
  req: AgentMessageRequest,
  onFrame: (frame: Record<string, unknown>) => void,
): Promise<void> {
  const res = await apiFetch('/api/v1/agents/sessions', {
    method: 'POST',
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      for (const line of part.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            onFrame(JSON.parse(line.slice(6)) as Record<string, unknown>);
          } catch { /* skip malformed */ }
        }
      }
    }
  }
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
