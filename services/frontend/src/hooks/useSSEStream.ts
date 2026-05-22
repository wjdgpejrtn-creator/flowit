'use client';

import { useEffect, useRef } from 'react';

// frame_type 기반 discriminated union 핸들러 타입
export interface SSEHandlers {
  onSession?: (frame: Record<string, unknown>) => void;
  onAgentNode?: (frame: Record<string, unknown>) => void;
  onRationaleDelta?: (frame: Record<string, unknown>) => void;
  onSlotFillQuestion?: (frame: Record<string, unknown>) => void;
  onDraftSpecDelta?: (frame: Record<string, unknown>) => void;
  onResult?: (frame: Record<string, unknown>) => void;
  onError?: (frame: Record<string, unknown>) => void;
  onClose?: () => void;
}

export function useSSEStream(
  sessionId: string | null,
  handlers: SSEHandlers,
) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!sessionId) return;

    const url = `/api/v1/ai/sessions/${sessionId}/stream`;
    const es = new EventSource(url);

    es.onmessage = (e) => {
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(e.data as string) as Record<string, unknown>;
      } catch {
        return;
      }
      const h = handlersRef.current;
      switch (frame.frame_type) {
        case 'session':            h.onSession?.(frame); break;
        case 'agent_node':         h.onAgentNode?.(frame); break;
        case 'rationale_delta':    h.onRationaleDelta?.(frame); break;
        case 'slot_fill_question': h.onSlotFillQuestion?.(frame); break;
        case 'draft_spec_delta':   h.onDraftSpecDelta?.(frame); break;
        case 'result':             h.onResult?.(frame); break;
        case 'error':              h.onError?.(frame); break;
        default:                   break;
      }
    };

    es.onerror = () => {
      es.close();
      handlersRef.current.onClose?.();
    };

    return () => {
      es.close();
    };
  }, [sessionId]);
}
