'use client';

import { useEffect, useRef, useState } from 'react';
import Icon from '@/components/common/Icon';

/**
 * AI 채팅 실행 모드 — 시안(Flowit.html)의 실행 엔진 포팅.
 * 노드 순차 실행 시뮬레이션 + 진행률 + 실시간 로그 + 일시정지/재개/취소/다시실행.
 *
 * 현재는 시안과 동일한 클라이언트 시뮬레이션. 다음 단계에서 execution_engine SSE로 교체.
 */

type NodeState = 'pending' | 'running' | 'succeeded' | 'cancelled';
type RunStatus = 'idle' | 'running' | 'paused' | 'done' | 'cancelled';

interface RunNode {
  name: string;
  type: string;
  priority: 'Low' | 'Medium' | 'High' | 'Restricted';
  service: string;
  state: NodeState;
}

interface LogLine {
  ts: string;
  msg: string;
  cls: string;
}

const RUN_NODES_DEF: Omit<RunNode, 'state'>[] = [
  { name: 'Google Sheets', type: 'google_sheets_read', priority: 'Medium', service: 'google_workspace' },
  { name: 'Text Template', type: 'text_template', priority: 'Low', service: 'none' },
  { name: 'Slack 알림', type: 'slack_notify', priority: 'High', service: 'slack' },
  { name: 'IT 서버 제어', type: 'it_ops_restart', priority: 'Restricted', service: 'none' },
];

/** 시안 setRunStatus map — [라벨, 점/글자색, 배지 className, 글자 className] */
const STATUS_MAP: Record<Exclude<RunStatus, 'idle'>, [string, string, string, string]> = {
  running: ['진행중', '#E8945C', 'bg-coral-light border-accent-coral/30', 'text-accent'],
  paused: ['일시정지됨', '#A2917F', 'bg-paper2 border-line-soft', 'text-ink3'],
  done: ['완료', '#10B981', 'bg-[#E7F6EF] border-[#10B981]/30', 'text-[#10B981]'],
  cancelled: ['취소됨', '#C75146', 'bg-danger-soft border-danger/30', 'text-danger'],
};

function nodeIcon(node: RunNode) {
  if (node.service === 'slack') return <Icon name="message-square" className="w-4 h-4 text-[#4A154B]" />;
  if (node.service === 'google_workspace') return <Icon name="sheet" className="w-4 h-4 text-[#0F9D58]" />;
  if (node.type.startsWith('it_ops_')) return <Icon name="server-cog" className="w-4 h-4 text-accent" />;
  if (node.type === 'text_template') return <Icon name="type" className="w-4 h-4 text-accent" />;
  return <Icon name="zap" className="w-4 h-4 text-accent" />;
}

function RiskMark({ priority }: { priority: RunNode['priority'] }) {
  if (priority === 'High') {
    return <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-orange-500 shadow-sm" title="High" />;
  }
  if (priority === 'Restricted') {
    return (
      <span className="absolute top-1.5 right-1.5 flex items-center space-x-0.5" title="Restricted">
        <span className="w-1.5 h-1.5 rounded-full bg-red-600 shadow-sm" />
        <Icon name="lock" className="w-3 h-3 text-red-600" />
      </span>
    );
  }
  return null;
}

function nodeCardStyle(state: NodeState): React.CSSProperties {
  switch (state) {
    case 'succeeded':
      return { boxShadow: '0 0 0 2px #10B981', borderColor: '#10B981' };
    case 'running':
      return { boxShadow: '0 0 12px #E8945C', borderColor: '#E8945C' };
    case 'cancelled':
      return { borderColor: '#C75146', opacity: 0.55 };
    default:
      return { borderColor: '#ECE3D6', opacity: 0.7 };
  }
}

function StatusTag({ state }: { state: NodeState }) {
  if (state === 'succeeded') return <Icon name="check" className="w-3.5 h-3.5 text-emerald-600" />;
  if (state === 'running') return <span className="w-1.5 h-1.5 rounded-full bg-accent-coral animate-pulse-dot" />;
  if (state === 'cancelled') return <Icon name="x" className="w-3.5 h-3.5 text-danger" />;
  return <Icon name="clock" className="w-3 h-3 text-ink4" />;
}

function nowTs(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export default function RunMode() {
  const [nodes, setNodes] = useState<RunNode[]>([]);
  const [status, setStatus] = useState<RunStatus>('idle');
  const [logs, setLogs] = useState<LogLine[]>([]);

  const nodesRef = useRef<RunNode[]>([]);
  const idxRef = useRef(0);
  const statusRef = useRef<RunStatus>('idle');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logBoxRef = useRef<HTMLDivElement>(null);

  const setRunStatus = (s: RunStatus) => {
    statusRef.current = s;
    setStatus(s);
  };
  const syncNodes = () => setNodes(nodesRef.current.map((n) => ({ ...n })));
  const log = (msg: string, cls = 'text-hl') =>
    setLogs((prev) => [...prev, { ts: nowTs(), msg, cls }]);

  const stepRun = () => {
    if (statusRef.current !== 'running') return;
    if (idxRef.current >= nodesRef.current.length) {
      setRunStatus('done');
      log('✓ 모든 노드 실행 완료. 워크플로우가 성공적으로 종료되었습니다.', 'text-emerald-400');
      return;
    }
    const node = nodesRef.current[idxRef.current];
    node.state = 'running';
    syncNodes();
    log(`◑ Node "${node.name}" (${node.type}) 실행 중...`);
    timerRef.current = setTimeout(() => {
      if (statusRef.current !== 'running') return;
      node.state = 'succeeded';
      const ms = Math.floor(Math.random() * 400 + 90);
      log(`✓ Node "${node.name}" 실행 완료 (succeeded · ${ms}ms)`, 'text-emerald-400');
      idxRef.current += 1;
      syncNodes();
      stepRun();
    }, 1100 + Math.random() * 700);
  };

  const startRun = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    nodesRef.current = RUN_NODES_DEF.map((n) => ({ ...n, state: 'pending' }));
    idxRef.current = 0;
    setLogs([]);
    setRunStatus('running');
    syncNodes();
    log(`자동 수집 에이전트 실행 시작 (세션 ID: run-${Math.floor(Math.random() * 9000 + 1000)})`);
    stepRun();
  };

  const togglePause = () => {
    if (statusRef.current === 'running') {
      if (timerRef.current) clearTimeout(timerRef.current);
      const cur = nodesRef.current[idxRef.current];
      if (cur && cur.state === 'running') cur.state = 'pending';
      setRunStatus('paused');
      syncNodes();
      log('⏸ 실행을 일시정지했습니다.');
    } else if (statusRef.current === 'paused') {
      setRunStatus('running');
      log('▶ 실행을 재개합니다.');
      stepRun();
    }
  };

  const cancelRun = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    nodesRef.current.forEach((n) => {
      if (n.state === 'pending' || n.state === 'running') n.state = 'cancelled';
    });
    setRunStatus('cancelled');
    syncNodes();
    log('⏹ 사용자가 실행을 취소했습니다. 남은 노드를 중단합니다.', 'text-danger');
  };

  useEffect(() => {
    startRun();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      statusRef.current = 'idle';
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
  }, [logs]);

  const doneCount = nodes.filter((n) => n.state === 'succeeded').length;
  const finished = status === 'done' || status === 'cancelled';
  const [statusLabel, statusColor, badgeClass, textClass] =
    STATUS_MAP[(status === 'idle' ? 'running' : status) as Exclude<RunStatus, 'idle'>];

  return (
    <div className="space-y-4">
      {/* 상단 컨트롤 바 */}
      <div className="bg-white border border-line-soft rounded-2xl p-4 flex items-center justify-between gap-4 shadow-sm overflow-x-auto whitespace-nowrap">
        <div className="flex items-center space-x-4">
          <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-full flex-shrink-0 border ${badgeClass}`}>
            <span
              className={`w-2.5 h-2.5 rounded-full${status === 'running' ? ' animate-pulse' : ''}`}
              style={{ background: statusColor }}
            />
            <span className={`text-xs font-bold ${textClass}`}>{statusLabel}</span>
          </div>
          <div className="text-xs font-bold text-ink">
            <span>진행: </span>
            <span className="text-accent-coral font-black">
              {doneCount} / {nodes.length} 노드 완료
            </span>
          </div>
        </div>
        <div className="flex items-center space-x-2 flex-shrink-0">
          {!finished && (
            <button
              type="button"
              onClick={togglePause}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-ink3 border border-line-soft hover:bg-paper"
            >
              {status === 'paused' ? '▶ 재개' : '⏸ 일시정지'}
            </button>
          )}
          {!finished && (
            <button
              type="button"
              onClick={cancelRun}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-red-600 border border-red-200 hover:bg-red-50"
            >
              ⏹ 취소
            </button>
          )}
          {finished && (
            <button
              type="button"
              onClick={startRun}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-accent hover:bg-accent3 shadow-sm"
            >
              ↻ 다시 실행
            </button>
          )}
        </div>
      </div>

      {/* 노드 캔버스 */}
      <div
        className="h-[260px] bg-white border border-line-soft rounded-2xl relative overflow-hidden shadow-sm"
        style={{ backgroundImage: 'radial-gradient(#D8CBB8 1.3px, transparent 1.3px)', backgroundSize: '18px 18px' }}
      >
        <div className="absolute inset-0 flex items-center justify-around px-6 flex-wrap gap-3">
          {nodes.map((node, i) => (
            <div
              key={`${node.type}-${i}`}
              className="w-[200px] h-[56px] bg-white border rounded-xl p-2 relative shadow-sm flex items-center space-x-2.5 transition-all"
              style={nodeCardStyle(node.state)}
            >
              <div className="w-8 h-8 rounded-lg bg-[#F7F1E8] flex items-center justify-center border border-line-soft flex-shrink-0">
                {nodeIcon(node)}
              </div>
              <div>
                <span className="text-xs font-bold text-ink block truncate max-w-[110px]">{node.name}</span>
                <span className="text-[9px] font-mono text-ink3 block">{node.type}</span>
              </div>
              <RiskMark priority={node.priority} />
              <div className="absolute bottom-2 right-2">
                <StatusTag state={node.state} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 실시간 로그 */}
      <div
        ref={logBoxRef}
        className="bg-accent3 text-white border border-accent3 rounded-2xl p-4 font-mono text-[11px] leading-relaxed max-h-[150px] overflow-y-auto space-y-0.5"
      >
        {logs.map((line, i) => (
          <p key={i} className={line.cls}>
            <span className="text-accent-coral">[{line.ts}]</span> {line.msg}
          </p>
        ))}
      </div>
    </div>
  );
}
