'use client';

import { useCallback, useState } from 'react';
import { useAgentStore, AgentStep } from '@/stores/agentStore';
import { streamCreateSession, sendSlotAnswer } from '@/lib/api/agentApi';
import { RiskLevel } from '@common/generated';

export function useAgentSession() {
  const {
    sessionId, setSessionId,
    addSession, addMessage,
    setCurrentStep, appendRationale, clearRationale,
    setSlotQuestion, setReadyToExecute, clearMessages,
  } = useAgentStore();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startSession = useCallback(async (message: string): Promise<string | null> => {
    setLoading(true);
    setError(null);
    clearMessages();
    clearRationale();
    setCurrentStep(null);

    addMessage({ id: `u-${Date.now()}`, role: 'user', content: message, timestamp: Date.now() });

    let resolvedSessionId: string | null = null;

    try {
      await streamCreateSession(
        { message, session_id: sessionId ?? undefined },
        (frame) => {
          switch (frame.frame_type) {
            case 'session':
              resolvedSessionId = frame.session_id as string;
              setSessionId(resolvedSessionId);
              addSession({ id: resolvedSessionId, title: message.slice(0, 40), createdAt: Date.now() });
              break;
            case 'agent_node':
              setCurrentStep(frame.node_name as AgentStep);
              break;
            case 'rationale_delta':
              appendRationale(frame.delta as string);
              break;
            case 'slot_fill_question':
              setSlotQuestion({
                fieldName: frame.field_name as string,
                label: frame.label as string,
                risk: (frame.risk as RiskLevel) ?? RiskLevel.LOW,
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
              if (typeof frame.message === 'string') {
                addMessage({ id: `a${Date.now()}`, role: 'agent', content: frame.message, timestamp: Date.now() });
              }
              break;
            }
            case 'error':
              setError((frame.message as string) ?? '알 수 없는 오류');
              break;
          }
        },
      );
      return resolvedSessionId;
    } catch (e) {
      setError(e instanceof Error ? e.message : '세션 생성 실패');
      return null;
    } finally {
      setLoading(false);
    }
  }, [sessionId, setSessionId, addSession, addMessage, clearMessages, clearRationale, setCurrentStep, appendRationale, setSlotQuestion, setReadyToExecute]);

  const answerSlot = useCallback(async (fieldName: string, value: string) => {
    if (!sessionId) return;
    setSlotQuestion(null);
    try {
      await sendSlotAnswer(sessionId, fieldName, value);
    } catch (e) {
      setError(e instanceof Error ? e.message : '슬롯 응답 전송 실패');
    }
  }, [sessionId, setSlotQuestion]);

  return { sessionId, loading, error, startSession, answerSlot, setCurrentStep };
}
