import type { ChatMessage } from '@/stores/agentStore';

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  return (
    <div className={['flex items-end gap-2', isUser ? 'justify-end' : 'justify-start'].join(' ')}>
      {!isUser && (
        <span className="w-[26px] h-[26px] rounded-full bg-[var(--color-agent)] text-white text-[10px] flex items-center justify-center flex-shrink-0 font-bold mb-[1px]">
          AI
        </span>
      )}
      <div
        className={[
          'max-w-[72%] px-[11px] py-[8px] text-[13px] leading-relaxed border-[1.5px]',
          isUser
            ? 'bg-[var(--color-hl)] border-[var(--color-accent)] rounded-[12px_8px_4px_12px]'
            : 'bg-[var(--color-surface)] border-[var(--color-ink)] rounded-[8px_12px_12px_4px]',
        ].join(' ')}
      >
        {message.content}
      </div>
    </div>
  );
}
