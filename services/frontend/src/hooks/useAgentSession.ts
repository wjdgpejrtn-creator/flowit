'use client';

import { useCallback, useState } from 'react';
import { useAgentStore } from '@/stores/agentStore';
import { createSession, sendSlotAnswer } from '@/lib/api/agentApi';

export function useAgentSession() {
  const {
    sessionId, setSessionId,
    addSession, addMessage,
    setCurrentStep, appendRationale, clearRationale,
    setSlotQuestion, clearMessages,
  } = useAgentStore();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startSession = useCallback(async (message: string): Promise<string | null> => {
    setLoading(true);
    setError(null);
    clearMessages();
    clearRationale();
    try {
      const session = await createSession({ message });
      setSessionId(session.session_id);
      addSession({
        id: session.session_id,
        title: message.slice(0, 40),
        createdAt: Date.now(),
      });
      addMessage({
        id: `u-${Date.now()}`,
        role: 'user',
        content: message,
        timestamp: Date.now(),
      });
      return session.session_id;
    } catch (e) {
      setError(e instanceof Error ? e.message : '세션 생성 실패');
      return null;
    } finally {
      setLoading(false);
    }
  }, [setSessionId, addSession, addMessage, clearMessages, clearRationale]);

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
