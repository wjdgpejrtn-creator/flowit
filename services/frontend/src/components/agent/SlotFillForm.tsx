'use client';

import { useState } from 'react';
import Btn from '@/components/common/Btn';
import type { SlotFillQuestion } from '@/stores/agentStore';

interface Props {
  question: SlotFillQuestion;
  onSubmit: (fieldName: string, value: string) => void;
  disabled?: boolean;
}

export default function SlotFillForm({ question, onSubmit, disabled }: Props) {
  const [value, setValue] = useState('');

  const handleSubmit = () => {
    if (!value.trim()) return;
    onSubmit(question.fieldName, value.trim());
    setValue('');
  };

  return (
    <div className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] p-[10px] bg-[var(--color-surface)]">
      <div className="text-[12px] font-bold mb-2">{question.question}</div>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
        placeholder="답변 입력…"
        disabled={disabled}
        className="w-full border-[1.5px] border-[var(--color-ink)] rounded px-[8px] py-[4px] text-[12px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
      />
      <div className="mt-2 flex justify-end">
        <Btn ghost className="text-[11px]" onClick={handleSubmit} disabled={disabled || !value.trim()}>
          확인
        </Btn>
      </div>
    </div>
  );
}
