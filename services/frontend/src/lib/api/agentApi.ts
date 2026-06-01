import { apiFetch } from '@/lib/apiClient';

export interface AgentSession {
  session_id: string;
  langgraph_thread_id: string;
}

export interface AgentMessageRequest {
  message: string;
  session_id?: string;
}

type FrameHandler = (frame: Record<string, unknown>) => void;

// SSE 응답 body를 읽어 `data:` 프레임을 onFrame으로 흘린다 (round1 생성 / round2 슬롯 공용).
async function pumpSSE(res: Response, onFrame: FrameHandler): Promise<void> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
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
  } finally {
    reader.releaseLock();
  }
}

export async function streamCreateSession(
  req: AgentMessageRequest,
  onFrame: FrameHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch('/api/v1/agents/sessions', {
    method: 'POST',
    body: JSON.stringify(req),
    signal,
  });
  await pumpSSE(res, onFrame);
}

// two-shot 2차(REQ-013): 스킬 선택(또는 건너뛰기) → round=2 스트림 소비.
// selectedSkillId=null → 건너뛰기(바인딩 no-op). round1과 동일 onFrame으로 이어 처리.
export async function streamSlotAnswer(
  sessionId: string,
  selectedSkillId: string | null,
  onFrame: FrameHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch(`/api/v1/agents/sessions/${sessionId}/slot`, {
    method: 'POST',
    body: JSON.stringify({ skill_id: selectedSkillId, field_name: 'skill_selection' }),
    signal,
  });
  await pumpSSE(res, onFrame);
}

// 상대 경로 — 단일 출처 원칙 준수 (ADR-0021), 쿠키 자동 전송
export function getStreamUrl(sessionId: string): string {
  return `/api/v1/ai/sessions/${sessionId}/stream`;
}
