interface StepsProps {
  items: string[];
  current?: number;
}

export default function Steps({ items, current = 0 }: StepsProps) {
  return (
    <div className="flex flex-col gap-1 text-[12px]">
      {items.map((item, i) => {
        const state = i < current ? 'done' : i === current ? 'cur' : 'todo';
        return (
          <div key={i} className="flex items-center gap-[6px]">
            <span
              className={[
                'w-[14px] h-[14px] rounded-full border-[1.5px] flex items-center justify-center text-[9px] flex-shrink-0',
                state === 'done'
                  ? 'bg-[var(--color-ink)] border-[var(--color-ink)] text-[var(--color-paper)]'
                  : state === 'cur'
                  ? 'bg-[var(--color-agent)] border-[var(--color-agent)] text-[var(--color-paper)] animate-pulse-dot'
                  : 'bg-[var(--color-paper)] border-[var(--color-ink)] text-[var(--color-ink4)]',
              ].join(' ')}
            >
              {state === 'done' ? '✓' : i + 1}
            </span>
            <span
              className={[
                'font-bold',
                state === 'todo' ? 'text-[var(--color-ink4)]' : 'text-[var(--color-ink)]',
              ].join(' ')}
            >
              {item}
            </span>
          </div>
        );
      })}
    </div>
  );
}
