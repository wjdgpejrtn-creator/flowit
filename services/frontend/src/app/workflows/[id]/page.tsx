import AppBar from '@/components/common/AppBar';
import StatusPill from '@/components/common/StatusPill';
import NodeCard from '@/components/common/NodeCard';
import ErrorBanner from '@/components/common/ErrorBanner';
import Btn from '@/components/common/Btn';

const TIMELINE = [
  { time: '09:00:00.124', name: 'Cron Trigger', status: 'succeeded' as const, elapsed: '+12ms' },
  { time: '09:00:00.236', name: 'Sheets Read',  status: 'succeeded' as const, elapsed: '+842ms' },
  { time: '09:00:01.078', name: 'Aggregate',    status: 'running'   as const, elapsed: '…' },
  { time: '09:00:??',     name: 'Drive Save',   status: 'pending'   as const, elapsed: '—' },
  { time: '09:00:??',     name: 'Slack Post',   status: 'pending'   as const, elapsed: '—' },
];

const CANVAS_NODES = [
  { icon: '⏰', name: 'Cron',      risk: 'low'  as const, status: 'succeeded' as const, x: 24,  y: 80 },
  { icon: '📊', name: 'Sheets',   risk: 'low'  as const, status: 'succeeded' as const, x: 160, y: 80 },
  { icon: 'Σ',  name: 'Aggregate',risk: 'low'  as const, status: 'running'   as const, x: 296, y: 80 },
  { icon: '📦', name: 'Drive',    risk: 'med'  as const, status: 'pending'   as const, x: 296, y: 190 },
  { icon: '#',  name: 'Slack',    risk: 'high' as const, status: 'pending'   as const, x: 432, y: 80 },
];

export default function WorkflowDetailPage({ params }: { params: { id: string } }) {
  void params;

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* Header bar */}
      <div
        className="flex items-center gap-[10px] px-3 py-2 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)]"
      >
        <span className="font-bold text-[14px]">주간 회의록 요약 ▶</span>
        <StatusPill status="running" />
        <span className="text-[13px] text-[var(--color-ink3)]">
          시작 09:00:00 · 경과 <span className="bg-[var(--color-hl)] px-[3px]">2.4s</span>
        </span>
        <span className="text-[11px] border border-[var(--color-ink4)] rounded px-[6px] py-0 text-[var(--color-ink3)]">
          trigger: cron
        </span>
        <div className="flex-1" />
        <Btn ghost>⏸ 일시정지</Btn>
        <Btn danger>⏹ 취소</Btn>
      </div>

      {/* Progress bar */}
      <div
        className="px-3 py-[6px] border-b-[1.5px] border-[var(--color-line-soft)] flex items-center gap-3 text-[13px]"
        style={{ background: 'var(--color-paper2)' }}
      >
        <span>2 / 5 완료</span>
        <div className="flex-1 h-[10px] border-[1.5px] border-[var(--color-ink)] rounded-full bg-[var(--color-paper)] overflow-hidden relative">
          <div
            className="absolute left-0 top-0 h-full border-r-[1.5px] border-[var(--color-ink)]"
            style={{ width: '40%', background: 'var(--color-status-succeeded)' }}
          />
          <div
            className="absolute top-0 h-full animate-shimmer"
            style={{ left: '40%', width: '15%' }}
          />
        </div>
        <span className="font-mono text-[12px]">2.4s · ETA 8s</span>
      </div>

      <div className="flex-1 flex min-h-0">
        {/* Canvas area */}
        <div
          className="flex-1 relative border-r-[1.5px] border-[var(--color-ink)] overflow-hidden"
          style={{ background: 'var(--color-paper2)', minHeight: 400 }}
        >
          {/* SVG edges */}
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox="0 0 600 320"
            preserveAspectRatio="xMidYMid meet"
          >
            <defs>
              <marker id="arr" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,0 L8,4 L0,8 z" fill="var(--color-ink)" />
              </marker>
            </defs>
            {/* Cron → Sheets */}
            <path d="M 134 112 C 175 112, 165 112, 160 112" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" markerEnd="url(#arr)" />
            {/* Sheets → Aggregate */}
            <path d="M 272 112 C 310 112, 296 112, 296 112" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" markerEnd="url(#arr)" />
            {/* Aggregate → Slack (dashed) */}
            <path d="M 410 112 C 450 112, 432 112, 432 112" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" strokeDasharray="4 3" markerEnd="url(#arr)" />
            {/* Aggregate → Drive (dashed) */}
            <path d="M 370 140 C 370 175, 360 190, 296 222" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" strokeDasharray="4 3" markerEnd="url(#arr)" />
          </svg>

          {/* Nodes */}
          {CANVAS_NODES.map((node) => (
            <div
              key={node.name}
              className="absolute"
              style={{ left: node.x, top: node.y }}
            >
              <NodeCard
                icon={node.icon}
                name={node.name}
                risk={node.risk}
                status={node.status}
              />
            </div>
          ))}
        </div>

        {/* Timeline panel */}
        <div
          className="overflow-auto p-2 flex flex-col gap-0"
          style={{ width: 280, background: 'var(--color-paper2)' }}
        >
          <div className="font-bold text-[13px] mb-[6px]">노드 이벤트 타임라인</div>
          <div className="h-[1.5px] bg-[var(--color-ink3)] rounded mb-3" />
          <div className="flex flex-col gap-2">
            {TIMELINE.map((item, i) => (
              <div
                key={i}
                className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[6px]"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] text-[var(--color-ink3)]">{item.time}</span>
                  <StatusPill status={item.status} />
                </div>
                <div className="flex items-center justify-between mt-[6px]">
                  <span className="font-bold text-[13px]">{item.name}</span>
                  <span className="font-mono text-[11px] text-[var(--color-ink3)]">{item.elapsed}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
