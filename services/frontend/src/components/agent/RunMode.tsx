'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Icon from '@/components/common/Icon';
import { useWorkflowStore } from '@/stores/workflowStore';
import { getCatalog } from '@/lib/api/nodeApi';
import {
  executeWorkflow,
  cancelExecution,
  pauseExecution,
  resumeExecution,
  getLatestExecution,
  type WorkflowLatestExecution,
} from '@/lib/api/workflowApi';
import { ExecutionStatus, RiskLevel } from '@common/generated';
import type { NodeConfig } from '@common/generated';

/**
 * AI 채팅 실행 모드 — execution_engine의 실제 실행 상태를 표시한다.
 *
 * execution 진행 상황 전용 SSE는 없으므로 `getLatestExecution(workflowId)`를 2.5초
 * 간격으로 polling한다(status가 pending/running/paused인 동안). 노드 카드 상태는
 * node_results(node_instance_id → status)를, 노드 메타(이름/리스크/서비스)는 노드
 * 카탈로그를 워크플로우 정의와 대조해 만든다. 컨트롤(실행/일시정지/취소/재개)은 모두 실제 API.
 *
 * 일시정지는 협조적 — worker가 다음 step 경계에서 PAUSED를 감지해 멈추고, 재개는
 * 완료된 step을 건너뛰고 이어 실행한다(ADR-0025, REQ-007).
 */

type NodeState = 'pending' | 'running' | 'succeeded' | 'failed' | 'retrying' | 'cancelled' | 'skipped';

interface DisplayNode {
  instanceId: string;
  name: string;
  nodeType: string;
  priority: RiskLevel;
  service: string;
  state: NodeState;
  error?: string | null;
}

interface LogLine {
  ts: string;
  msg: string;
  cls: string;
}

const ACTIVE_STATUSES = new Set<string>([
  ExecutionStatus.PENDING,
  ExecutionStatus.RUNNING,
  ExecutionStatus.PAUSED,
]);

/** execution status → [라벨, 점/글자색, 배지 className, 글자 className] */
const STATUS_MAP: Record<string, [string, string, string, string]> = {
  preparing: ['실행 준비 중', '#E8945C', 'bg-coral-light border-accent-coral/30', 'text-accent'],
  [ExecutionStatus.PENDING]: ['대기 중', '#E8945C', 'bg-coral-light border-accent-coral/30', 'text-accent'],
  [ExecutionStatus.RUNNING]: ['진행중', '#E8945C', 'bg-coral-light border-accent-coral/30', 'text-accent'],
  [ExecutionStatus.PAUSED]: ['일시정지됨', '#A2917F', 'bg-paper2 border-line-soft', 'text-ink3'],
  [ExecutionStatus.COMPLETED]: ['완료', '#10B981', 'bg-[#E7F6EF] border-[#10B981]/30', 'text-[#10B981]'],
  [ExecutionStatus.FAILED]: ['실패', '#C75146', 'bg-danger-soft border-danger/30', 'text-danger'],
  [ExecutionStatus.CANCELLED]: ['취소됨', '#C75146', 'bg-danger-soft border-danger/30', 'text-danger'],
  idle: ['실행 전', '#A2917F', 'bg-paper2 border-line-soft', 'text-ink3'],
};

function nodeIcon(node: DisplayNode) {
  if (node.service === 'slack') return <Icon name="message-square" className="w-4 h-4 text-[#4A154B]" />;
  if (node.service === 'google_workspace') return <Icon name="sheet" className="w-4 h-4 text-[#0F9D58]" />;
  if (node.nodeType.startsWith('it_ops_')) return <Icon name="server-cog" className="w-4 h-4 text-accent" />;
  if (node.nodeType === 'text_template') return <Icon name="type" className="w-4 h-4 text-accent" />;
  return <Icon name="zap" className="w-4 h-4 text-accent" />;
}

function RiskMark({ priority }: { priority: DisplayNode['priority'] }) {
  if (priority === RiskLevel.HIGH) {
    return <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-orange-500 shadow-sm" title="High" />;
  }
  if (priority === RiskLevel.RESTRICTED) {
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
    case 'retrying':
      return { boxShadow: '0 0 8px #E8945C', borderColor: '#E8945C', opacity: 0.85 };
    case 'failed':
      return { boxShadow: '0 0 0 2px #C75146', borderColor: '#C75146' };
    case 'cancelled':
      return { borderColor: '#C75146', opacity: 0.55 };
    case 'skipped':
      // L2 조건 분기에서 안 탄 가지 — 흐릿하게 비활성 표시(실패 아님).
      return { borderColor: '#D8CBB8', opacity: 0.4, borderStyle: 'dashed' };
    default:
      return { borderColor: '#ECE3D6', opacity: 0.7 };
  }
}

function StatusTag({ state }: { state: NodeState }) {
  if (state === 'succeeded') return <Icon name="check" className="w-3.5 h-3.5 text-emerald-600" />;
  if (state === 'running') return <span className="w-1.5 h-1.5 rounded-full bg-accent-coral animate-pulse-dot" />;
  if (state === 'retrying') return <Icon name="refresh-cw" className="w-3.5 h-3.5 text-accent animate-spin" />;
  if (state === 'failed') return <Icon name="alert-triangle" className="w-3.5 h-3.5 text-danger" />;
  if (state === 'cancelled') return <Icon name="x" className="w-3.5 h-3.5 text-danger" />;
  if (state === 'skipped') return <Icon name="skip-forward" className="w-3.5 h-3.5 text-ink4" />;
  return <Icon name="clock" className="w-3 h-3 text-ink4" />;
}

function nowTs(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const NODE_STATE_LOG: Partial<Record<NodeState, [string, string]>> = {
  running: ['◑ Node "%s" 실행 중...', 'text-hl'],
  succeeded: ['✓ Node "%s" 실행 완료 (succeeded)', 'text-emerald-400'],
  failed: ['✗ Node "%s" 실행 실패 (failed)', 'text-danger'],
  retrying: ['↻ Node "%s" 재시도 중 (retrying)', 'text-hl'],
  cancelled: ['⏹ Node "%s" 취소됨', 'text-danger'],
  skipped: ['⊘ Node "%s" 건너뜀 (조건 분기 미선택)', 'text-ink4'],
};

const EXEC_STATE_LOG: Record<string, [string, string]> = {
  [ExecutionStatus.COMPLETED]: ['✓ 모든 노드 실행 완료. 워크플로우가 성공적으로 종료되었습니다.', 'text-emerald-400'],
  [ExecutionStatus.FAILED]: ['✗ 워크플로우 실행이 실패했습니다.', 'text-danger'],
  [ExecutionStatus.CANCELLED]: ['⏹ 실행이 취소되었습니다.', 'text-danger'],
  [ExecutionStatus.PAUSED]: ['⏸ 실행이 일시정지되었습니다.', 'text-ink3'],
};

export default function RunMode() {
  const workflow = useWorkflowStore((s) => s.workflow);
  const activeExecutionId = useWorkflowStore((s) => s.activeExecutionId);
  const setActiveExecutionId = useWorkflowStore((s) => s.setActiveExecutionId);
  const workflowId = workflow ? String(workflow.workflow_id) : null;

  const [catalog, setCatalog] = useState<NodeConfig[] | null>(null);
  const [latest, setLatest] = useState<WorkflowLatestExecution | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  // polling을 즉시 재가동시키는 트리거 — cancel/resume/실행 후 다음 tick을 기다리지 않게.
  const [pollTrigger, setPollTrigger] = useState(0);

  const logBoxRef = useRef<HTMLDivElement>(null);
  // 노드 status 전이 로그를 위한 직전 스냅샷.
  const prevSnapRef = useRef<{ execId: string | null; nodes: Record<string, string>; status: string | null }>({
    execId: null,
    nodes: {},
    status: null,
  });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getCatalog();
        if (!cancelled) setCatalog(data);
      } catch {
        // 카탈로그 실패 시 노드 메타는 fallback(node_id 슬라이스)로 표시 — 치명적 아님.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 노드 메타 lookup: catalog(node_id → NodeConfig) + workflow.nodes(instance_id → node_id).
  const metaByInstanceId = useMemo(() => {
    const map = new Map<string, { name: string; nodeType: string; priority: NodeConfig['risk_level']; service: string }>();
    if (!workflow) return map;
    const byNodeId = new Map((catalog ?? []).map((c) => [String(c.node_id), c]));
    for (const node of workflow.nodes) {
      const cfg = byNodeId.get(String(node.node_id));
      map.set(node.instance_id, {
        name: cfg?.name ?? node.instance_id.slice(0, 8),
        nodeType: cfg?.node_type ?? 'unknown',
        priority: cfg?.risk_level ?? RiskLevel.LOW,
        service: cfg?.required_connections?.[0] ?? 'none',
      });
    }
    return map;
  }, [workflow, catalog]);

  const metaRef = useRef(metaByInstanceId);
  metaRef.current = metaByInstanceId;

  const appendLogDelta = useCallback((result: WorkflowLatestExecution) => {
    const prev = prevSnapRef.current;
    const lines: LogLine[] = [];
    const meta = metaRef.current;
    const nameOf = (id: string) => meta.get(id)?.name ?? id.slice(0, 8);

    let freshExecution = false;
    if (prev.execId !== result.execution_id) {
      freshExecution = true;
      prev.nodes = {};
      prev.status = null;
      lines.push({ ts: nowTs(), msg: `실행 시작 (ID: ${result.execution_id.slice(0, 8)}…)`, cls: 'text-hl' });
    }

    const curNodes: Record<string, string> = {};
    for (const nr of result.node_results) {
      curNodes[nr.node_instance_id] = nr.status;
      if (prev.nodes[nr.node_instance_id] !== nr.status) {
        const tmpl = NODE_STATE_LOG[nr.status as NodeState];
        if (tmpl) {
          let msg = tmpl[0].replace('%s', nameOf(nr.node_instance_id));
          if (nr.status === 'failed' && nr.last_error) msg += ` — ${nr.last_error}`;
          lines.push({ ts: nowTs(), msg, cls: tmpl[1] });
        }
      }
    }

    if (prev.status !== result.status) {
      const tmpl = EXEC_STATE_LOG[result.status];
      if (tmpl) lines.push({ ts: nowTs(), msg: tmpl[0], cls: tmpl[1] });
    }

    prevSnapRef.current = { execId: result.execution_id, nodes: curNodes, status: result.status };
    if (freshExecution) setLogs(lines);
    else if (lines.length) setLogs((l) => [...l, ...lines]);
  }, []);

  // execution 상태 polling.
  useEffect(() => {
    if (!workflowId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      let result: WorkflowLatestExecution | null;
      try {
        result = await getLatestExecution(workflowId);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : '실행 상태 조회 실패');
        setLoading(false);
        return;
      }
      if (cancelled) return;
      setError(null);
      setLoading(false);

      // race 가드: 방금 트리거한 execution(activeExecutionId)을 worker가 아직 INSERT하지
      // 않아 latest가 그 id가 아니면 "준비 중"으로 취급하고 계속 polling.
      const waitingForNew =
        activeExecutionId != null && (result === null || result.execution_id !== activeExecutionId);

      setPreparing(waitingForNew);
      if (waitingForNew) {
        // 직전 완료 실행의 node_results가 남아 카드가 succeeded로 보이지 않도록 리셋.
        setLatest(null);
      } else {
        setLatest(result);
        if (result) appendLogDelta(result);
      }

      const status = waitingForNew ? ExecutionStatus.PENDING : result?.status ?? null;
      const keepPolling = waitingForNew || (status != null && ACTIVE_STATUSES.has(status));
      if (keepPolling && !cancelled) {
        timer = setTimeout(() => void tick(), 2500);
      }
    };

    setLoading(true);
    void tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [workflowId, activeExecutionId, pollTrigger, appendLogDelta]);

  useEffect(() => {
    if (logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
  }, [logs]);

  const execId = latest?.execution_id ?? activeExecutionId ?? null;
  const execStatus = preparing ? 'preparing' : latest?.status ?? (activeExecutionId ? 'preparing' : 'idle');
  const isActive = execStatus === 'preparing' || ACTIVE_STATUSES.has(execStatus);
  const isRunning = execStatus === ExecutionStatus.RUNNING;
  const isPaused = execStatus === ExecutionStatus.PAUSED;
  const isFinished = !isActive && execStatus !== 'idle';

  const statusByInstanceId = useMemo(() => {
    const map = new Map<string, { status: NodeState; error?: string | null }>();
    for (const nr of latest?.node_results ?? []) {
      map.set(nr.node_instance_id, { status: nr.status as NodeState, error: nr.last_error });
    }
    return map;
  }, [latest]);

  const nodes: DisplayNode[] = useMemo(() => {
    if (!workflow) return [];
    return workflow.nodes.map((n) => {
      const meta = metaByInstanceId.get(n.instance_id);
      const st = statusByInstanceId.get(n.instance_id);
      return {
        instanceId: n.instance_id,
        name: meta?.name ?? n.instance_id.slice(0, 8),
        nodeType: meta?.nodeType ?? 'unknown',
        priority: meta?.priority ?? RiskLevel.LOW,
        service: meta?.service ?? 'none',
        state: st?.status ?? 'pending',
        error: st?.error,
      };
    });
  }, [workflow, metaByInstanceId, statusByInstanceId]);

  const doneCount = nodes.filter((n) => n.state === 'succeeded').length;

  const handleStart = useCallback(async () => {
    if (!workflowId) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await executeWorkflow(workflowId);
      setActiveExecutionId(resp.execution_id);
      setPollTrigger((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : '실행 요청 실패');
    } finally {
      setBusy(false);
    }
  }, [workflowId, setActiveExecutionId]);

  const handleCancel = useCallback(async () => {
    if (!execId) return;
    setBusy(true);
    setError(null);
    try {
      await cancelExecution(execId);
      setPollTrigger((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : '취소 요청 실패');
    } finally {
      setBusy(false);
    }
  }, [execId]);

  const handlePause = useCallback(async () => {
    if (!execId) return;
    setBusy(true);
    setError(null);
    try {
      await pauseExecution(execId);
      setPollTrigger((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : '일시정지 요청 실패');
    } finally {
      setBusy(false);
    }
  }, [execId]);

  const handleResume = useCallback(async () => {
    if (!execId) return;
    setBusy(true);
    setError(null);
    try {
      await resumeExecution(execId);
      setPollTrigger((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : '재개 요청 실패');
    } finally {
      setBusy(false);
    }
  }, [execId]);

  if (!workflow) {
    return (
      <div className="flex-1 flex items-center justify-center text-[13px] text-ink3">
        실행할 워크플로우가 없습니다. 먼저 워크플로우를 생성하거나 불러오세요.
      </div>
    );
  }

  const [statusLabel, statusColor, badgeClass, textClass] = STATUS_MAP[execStatus] ?? STATUS_MAP.idle;

  return (
    <div className="space-y-4">
      {/* 상단 컨트롤 바 */}
      <div className="bg-white border border-line-soft rounded-2xl p-4 flex items-center justify-between gap-4 shadow-sm overflow-x-auto whitespace-nowrap">
        <div className="flex items-center space-x-4">
          <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-full flex-shrink-0 border ${badgeClass}`}>
            <span
              className={`w-2.5 h-2.5 rounded-full${isActive ? ' animate-pulse' : ''}`}
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
          {isRunning && (
            <button
              type="button"
              onClick={() => void handlePause()}
              disabled={busy || !execId}
              title="실행을 일시정지합니다 (현재 단계 완료 후 멈춤)"
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-ink3 border border-line-soft hover:bg-paper disabled:opacity-50"
            >
              ⏸ 일시정지
            </button>
          )}
          {isPaused && (
            <button
              type="button"
              onClick={() => void handleResume()}
              disabled={busy}
              title="완료된 단계는 건너뛰고 이어서 실행합니다"
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-ink3 border border-line-soft hover:bg-paper disabled:opacity-50"
            >
              ▶ 재개
            </button>
          )}
          {(isActive || isPaused) && (
            <button
              type="button"
              onClick={() => void handleCancel()}
              disabled={busy || !execId}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-red-600 border border-red-200 hover:bg-red-50 disabled:opacity-50"
            >
              ⏹ 취소
            </button>
          )}
          {(isFinished || execStatus === 'idle') && (
            <button
              type="button"
              onClick={() => void handleStart()}
              disabled={busy}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-accent hover:bg-accent3 shadow-sm disabled:opacity-50"
            >
              {execStatus === 'idle' ? '▶ 실행' : '↻ 다시 실행'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-danger-soft border border-danger/30 rounded-xl px-4 py-2 text-xs text-danger font-bold">
          ⚠ {error}
        </div>
      )}

      {/* 노드 캔버스 */}
      <div
        className="h-[260px] bg-white border border-line-soft rounded-2xl relative overflow-hidden shadow-sm"
        style={{ backgroundImage: 'radial-gradient(#D8CBB8 1.3px, transparent 1.3px)', backgroundSize: '18px 18px' }}
      >
        <div className="absolute inset-0 flex items-center justify-around px-6 flex-wrap gap-3">
          {nodes.map((node) => (
            <div
              key={node.instanceId}
              className="w-[200px] h-[56px] bg-white border rounded-xl p-2 relative shadow-sm flex items-center space-x-2.5 transition-all"
              style={nodeCardStyle(node.state)}
              title={node.error ?? undefined}
            >
              <div className="w-8 h-8 rounded-lg bg-[#F7F1E8] flex items-center justify-center border border-line-soft flex-shrink-0">
                {nodeIcon(node)}
              </div>
              <div>
                <span className="text-xs font-bold text-ink block truncate max-w-[110px]">{node.name}</span>
                <span className="text-[9px] font-mono text-ink3 block">{node.nodeType}</span>
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
        {logs.length === 0 ? (
          <p className="text-ink4">
            {loading
              ? '실행 상태를 불러오는 중…'
              : execStatus === 'idle'
                ? '아직 실행되지 않았습니다. 실행 버튼을 눌러 시작하세요.'
                : '실행 로그를 기다리는 중…'}
          </p>
        ) : (
          logs.map((line, i) => (
            <p key={i} className={line.cls}>
              <span className="text-accent-coral">[{line.ts}]</span> {line.msg}
            </p>
          ))
        )}
      </div>
    </div>
  );
}
