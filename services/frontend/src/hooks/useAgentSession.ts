'use client';

import { useRef, useState } from 'react';
import { streamCreateSession, sendSlotAnswer } from '@/lib/api/agentApi';
import { useAgentStore, type AgentStep } from '@/stores/agentStore';

export function useAgentSession() {
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const {
    sessionId, setSessionId,
    addMessage,
    setCurrentStep,
    appendRationale, clearRationale,
    setSlotQuestion,
    setReadyToExecute,
  } = useAgentStore();

  const send = async (text: string) => {
    if (!text.trim() || streaming) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    addMessage({ id: `m${Date.now()}`, role: 'user', content: text, timestamp: Date.now() });
    setStreaming(true);
    setCurrentStep(null);
    clearRationale();

    try {
      await streamCreateSession(
        { message: text, session_id: sessionId ?? undefined },
        (frame) => {
          switch (frame.frame_type) {
            case 'session':
              setSessionId(frame.session_id as string);
              break;
            case 'agent_node':
              setCurrentStep(frame.agent_node_name as AgentStep);
              break;
            case 'rationale_delta':
              appendRationale(frame.delta as string);
              break;
            case 'slot_fill_question':
              setSlotQuestion({
                fieldName: frame.field_name as string,
                question: frame.question as string,
              });
              break;
            case 'result': {
              const payload = frame.payload as Record<string, unknown> | undefined;
              if (payload?.status === 'ready_to_execute') {
                setReadyToExecute({
                  workflowId: payload.workflow_id as string,
                  message: (payload.message as string) ?? '워크플로우가 완성됐습니다.',
                });
              }
              const msg = payload?.message;
              if (typeof msg === 'string') {
                addMessage({ id: `a${Date.now()}`, role: 'agent', content: msg, timestamp: Date.now() });
              }
              break;
            }
            case 'error':
              addMessage({
                id: `e${Date.now()}`,
                role: 'agent',
                content: `오류가 발생했습니다: ${(frame.message as string) ?? '알 수 없는 오류'}`,
                timestamp: Date.now(),
              });
              break;
          }
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      addMessage({
        id: `e${Date.now()}`,
        role: 'agent',
        content: `연결 오류: ${err instanceof Error ? err.message : '서버에 연결할 수 없습니다.'}`,
        timestamp: Date.now(),
      });
    } finally {
      setStreaming(false);
    }
  };

  const submitSlot = async (fieldName: string, value: string) => {
    if (!sessionId) return;
    setSlotQuestion(null);
    try {
      await sendSlotAnswer(sessionId, fieldName, value);
    } catch {
      // 슬롯 전송 실패는 조용히 처리
    }
  };

  const abort = () => {
    abortRef.current?.abort();
  };

  return { streaming, send, submitSlot, abort };
}
