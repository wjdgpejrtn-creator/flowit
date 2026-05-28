'use client';

import { useRef } from 'react';
import Btn from '@/components/common/Btn';
import MessageBubble from './MessageBubble';
import SlotFillForm from './SlotFillForm';
import type { ChatMessage, SlotFillQuestion } from '@/stores/agentStore';

interface ReadyToExecute {
  workflowId: string;
  message: string;
}

interface Props {
  messages: ChatMessage[];
  streaming: boolean;
  input: string;
  slotQuestion: SlotFillQuestion | null;
  readyToExecute: ReadyToExecute | null;
  executeLoading: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onSlotSubmit: (fieldName: string, value: string) => void;
  onExecute: () => void;
}

export default function AgentChat({
  messages,
  streaming,
  input,
  slotQuestion,
  readyToExecute,
  executeLoading,
  onInputChange,
  onSend,
  onSlotSubmit,
  onExecute,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {/* 메시지 목록 */}
      <div className="flex-1 overflow-auto px-4 py-3 flex flex-col gap-3">
        {messages.length === 0 && !streaming && (
          <div className="flex-1 flex items-center justify-center text-center px-6">
            <div className="text-[13px] text-[var(--color-ink4)] leading-relaxed max-w-[420px]">
              만들고 싶은 워크플로우를 자연어로 설명해주세요.<br />
              예: <span className="text-[var(--color-ink3)]">&ldquo;매주 월요일 9시에 광고 시트를 읽어서 요약하고 Slack으로 보내줘&rdquo;</span>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* 실행 준비 메시지 */}
        {readyToExecute && (
          <div className="flex items-end gap-2 justify-start">
            <span className="w-[26px] h-[26px] rounded-full bg-[var(--color-agent)] text-white text-[10px] flex items-center justify-center flex-shrink-0 font-bold mb-[1px]">
              AI
            </span>
            <div className="max-w-[72%] px-[11px] py-[8px] text-[13px] leading-relaxed border-[1.5px] bg-[var(--color-surface)] border-[var(--color-ink)] rounded-[8px_12px_12px_4px]">
              <p className="mb-[8px]">{readyToExecute.message}</p>
              <Btn onClick={onExecute} disabled={executeLoading} className="text-[12px]">
                {executeLoading ? '실행 중…' : '▶ 실행'}
              </Btn>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 슬롯 필링 폼 (입력창 위) */}
      {slotQuestion && (
        <div className="border-t-[1.5px] border-[var(--color-line-soft)] px-3 py-2 bg-[var(--color-paper2)]">
          <SlotFillForm
            question={slotQuestion}
            onSubmit={onSlotSubmit}
            disabled={streaming}
          />
        </div>
      )}

      {/* 입력창 */}
      <div className="border-t-[1.5px] border-[var(--color-ink)] px-3 py-2 flex gap-2 bg-[var(--color-surface)] flex-shrink-0">
        <textarea
          className="flex-1 resize-none border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[10px] py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
          rows={2}
          placeholder={streaming ? 'AI가 처리 중입니다…' : '워크플로우를 자연어로 설명하세요… (Shift+Enter 줄바꿈)'}
          value={input}
          disabled={streaming}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        <Btn onClick={onSend} disabled={streaming} className="self-end">
          {streaming ? '처리 중…' : '전송 ↑'}
        </Btn>
      </div>
    </div>
  );
}
