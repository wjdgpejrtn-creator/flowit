'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AppBar from '@/components/common/AppBar';
import StatusPill from '@/components/common/StatusPill';
import ErrorBanner from '@/components/common/ErrorBanner';
import Btn from '@/components/common/Btn';
import Skel from '@/components/common/Skel';
import { useWorkflow } from '@/hooks/useWorkflow';
import { useWorkflowStore } from '@/stores/workflowStore';
import WorkflowEditPane from '@/components/workflow/WorkflowEditPane';
import {
  getLatestExecution,
  cancelExecution,
  pauseExecution,
  resumeExecution,
  type WorkflowLatestExecution,
  type NodeResultEntry,
} from '@/lib/api/workflowApi';
import {
  ReactFlow,
  Background,
  Controls,
  type Node as RFNode,
  type Edge as RFEdge,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const POLL_INTERVAL_MS = 2000;
const ACTIVE_STATUSES = new Set(['pending', 'running', 'paused']);

function fmtElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s}s`;
}

function fmtClock(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('ko-KR', { hour12: false });
}

function nodeStatusLookup(results: NodeResultEntry[]): Map<string, NodeResultEntry['status']> {
  const m = new Map<string, NodeResultEntry['status']>();
  for (const r of results) m.set(r.node_instance_id, r.status);
  return m;
}

type Mode = 'view' | 'edit';

export default function WorkflowDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { workflow, loading: wfLoading, error: wfError, load: loadWorkflow } = useWorkflow();
  const setStoreWorkflow = useWorkflowStore((s) => s.setWorkflow);
  const storeDirty = useWorkflowStore((s) => s.dirty);

  const [mode, setMode] = useState<Mode>('view');
  const [execution, setExecution] = useState<WorkflowLatestExecution | null>(null);
  const [execError, setExecError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());
  const [controlBusy, setControlBusy] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    void loadWorkflow(id);
  }, [id, loadWorkflow]);

  // edit 모드 진입 시 store에 workflow 푸시. 종료 시 정리.
  useEffect(() => {
    if (mode === 'edit') {
      if (workflow) setStoreWorkflow(workflow);
    } else {
      setStoreWorkflow(null);
    }
    return () => {
      // 페이지 unmount 시 정리
      setStoreWorkflow(null);
    };
  }, [mode, workflow, setStoreWorkflow]);

  const fetchExecution = useCallback(async () => {
    try {
      const data = await getLatestExecution(id);
      setExecution(data);
      setExecError(null);
    } catch (e) {
      setExecError(e instanceof Error ? e.message : '실행 상태 조회 실패');
    }
  }, [id]);

  useEffect(() => {
    if (mode === 'edit') return;
    void fetchExecution();
  }, [fetchExecution, mode]);

  // active 상태일 때만 polling (view 모드일 때만)
  useEffect(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
    if (mode === 'edit') return;
    if (execution && ACTIVE_STATUSES.has(execution.status)) {
      pollRef.current = setTimeout(() => void fetchExecution(), POLL_INTERVAL_MS);
    }
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [execution, fetchExecution, mode]);

  // live 경과 시간
  useEffect(() => {
    if (mode === 'edit') return;
    if (!execution || !ACTIVE_STATUSES.has(execution.status)) return;
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [execution, mode]);

  const handleCancel = async () => {
    if (!execution) return;
    setControlBusy(true);
    setControlError(null);
    try {
      await cancelExecution(execution.execution_id);
      void fetchExecution();
    } catch (e) {
      setControlError(e instanceof Error ? e.message : '취소 실패');
    } finally {
      setControlBusy(false);
    }
  };

  const handlePause = async () => {
    if (!execution) return;
    setControlBusy(true);
    setControlError(null);
    try {
      await pauseExecution(execution.execution_id);
      void fetchExecution();
    } catch (e) {
      setControlError(e instanceof Error ? e.message : '일시정지 실패');
    } finally {
      setControlBusy(false);
    }
  };

  const handleResume = async () => {
    if (!execution) return;
    setControlBusy(true);
    setControlError(null);
    try {
      await resumeExecution(execution.execution_id);
      void fetchExecution();
    } catch (e) {
      setControlError(e instanceof Error ? e.message : '재개 실패');
    } finally {
      setControlBusy(false);
    }
  };

  const handleToggleMode = () => {
    if (mode === 'edit' && storeDirty) {
      const ok = window.confirm('미저장 변경이 있습니다. 변경을 버리고 보기 모드로 돌아갈까요?');
      if (!ok) return;
    }
    const next: Mode = mode === 'view' ? 'edit' : 'view';
    setMode(next);
    if (next === 'view') {
      // edit 모드에서 저장된 최신 노드/엣지가 view 모드 ReactFlow에 반영되도록 hook reload
      void loadWorkflow(id);
    }
  };

  const handleExecuted = () => {
    // 실행 후 view 모드로 전환 + hook reload (edit 모드에서 저장된 최신 그래프 반영)
    setMode('view');
    void loadWorkflow(id);
    void fetchExecution();
  };

  // 경과 시간 계산
  const elapsedSec = useMemo(() => {
    if (!execution) return 0;
    const start = new Date(execution.started_at).getTime();
    const end = execution.finished_at ? new Date(execution.finished_at).getTime() : nowMs;
    return Math.max(0, (end - start) / 1000);
  }, [execution, nowMs]);

  // progress 계산
  const totalNodes = workflow?.nodes.length ?? 0;
  const summary = execution?.node_states_summary ?? {};
  const completedCount =
    (summary.succeeded ?? 0) + (summary.failed ?? 0) + (summary.cancelled ?? 0);
  const progressPct = totalNodes > 0 ? Math.round((completedCount / totalNodes) * 100) : 0;

  // view 모드 ReactFlow node/edge 변환
  const statusMap = execution ? nodeStatusLookup(execution.node_results) : new Map();
  const rfNodes: RFNode[] = useMemo(() => {
    if (!workflow) return [];
    return workflow.nodes.map((n) => {
      const status = statusMap.get(n.instance_id) ?? 'pending';
      const colorByStatus: Record<string, string> = {
        succeeded: 'var(--color-status-succeeded)',
        running: 'var(--color-status-running)',
        failed: 'var(--color-status-failed)',
        retrying: 'var(--color-status-retrying)',
        pending: 'var(--color-ink4)',
        cancelled: 'var(--color-ink4)',
      };
      return {
        id: String(n.instance_id),
        position: { x: n.position.x, y: n.position.y },
        data: { label: `${n.instance_id.slice(0, 8)}… [${status}]` },
        style: {
          border: `2px solid ${colorByStatus[status]}`,
          background: 'var(--color-surface)',
          fontSize: 11,
          padding: 6,
        },
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow, execution]);

  const rfEdges: RFEdge[] = useMemo(() => {
    if (!workflow) return [];
    return workflow.connections.map((e, i) => ({
      id: `e${i}`,
      source: String(e.from_instance_id),
      target: String(e.to_instance_id),
    }));
  }, [workflow]);

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  useEffect(() => {
    setNodes(rfNodes);
  }, [rfNodes, setNodes]);
  useEffect(() => {
    setEdges(rfEdges);
  }, [rfEdges, setEdges]);

  const workflowName = workflow?.name ?? (wfLoading ? '' : '워크플로우');
  const execStatus = execution?.status ?? 'pending';
  const isActive = execution && ACTIVE_STATUSES.has(execution.status);
  const isRunning = execution?.status === 'running';
  const isPaused = execution?.status === 'paused';

  // 버튼 disabled 사유 툴팁 — 무반응처럼 보이지 않도록 이유를 명시 (#364).
  const pauseTitle = !execution
    ? '실행 중인 워크플로우가 없습니다'
    : isRunning
      ? '실행을 일시정지합니다 (현재 단계 완료 후 멈춤)'
      : isPaused
        ? '이미 일시정지 상태입니다'
        : '실행 중일 때만 일시정지할 수 있습니다';
  const resumeTitle = !execution
    ? '실행 중인 워크플로우가 없습니다'
    : isPaused
      ? '완료된 단계는 건너뛰고 이어서 실행합니다'
      : '일시정지 상태일 때만 재개할 수 있습니다';
  const cancelTitle = !execution
    ? '실행 중인 워크플로우가 없습니다'
    : isActive
      ? '실행을 취소합니다'
      : '진행 중인 실행이 없습니다';

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* Header bar */}
      <div className="flex items-center gap-[10px] px-3 py-2 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)]">
        {wfLoading ? (
          <Skel className="w-40 h-4" />
        ) : (
          <span className="font-bold text-[14px]">{workflowName}</span>
        )}
        {mode === 'view' && execution && (
          <>
            <StatusPill status={execStatus} />
            <span className="text-[13px] text-[var(--color-ink3)]">
              시작 {fmtClock(execution.started_at)} · 경과{' '}
              <span className="bg-[var(--color-hl)] px-[3px] font-mono">{fmtElapsed(elapsedSec)}</span>
            </span>
            <span className="text-[11px] border border-[var(--color-ink4)] rounded px-[6px] py-0 text-[var(--color-ink3)] font-mono">
              exec {execution.execution_id.slice(0, 8)}…
            </span>
          </>
        )}
        {mode === 'view' && !execution && (
          <span className="text-[13px] text-[var(--color-ink4)] italic">아직 실행된 적이 없습니다.</span>
        )}
        <div className="flex-1" />

        {mode === 'view' ? (
          <>
            <Btn ghost onClick={handlePause} disabled={!isRunning || controlBusy} title={pauseTitle}>
              ⏸ 일시정지
            </Btn>
            <Btn ghost onClick={handleResume} disabled={!isPaused || controlBusy} title={resumeTitle}>
              ▶ 재개
            </Btn>
            <Btn danger onClick={handleCancel} disabled={!isActive || controlBusy} title={cancelTitle}>
              ⏹ 취소
            </Btn>
            <Btn primary onClick={handleToggleMode} disabled={!workflow}>
              ✎ 편집
            </Btn>
          </>
        ) : (
          <Btn ghost onClick={handleToggleMode}>
            👁 보기로 돌아가기
          </Btn>
        )}
      </div>

      {mode === 'view' && (wfError || execError || controlError) && (
        <div className="px-3 pt-2 flex flex-col gap-1">
          {wfError && <ErrorBanner><span>⚠ 워크플로우: {wfError}</span></ErrorBanner>}
          {execError && <ErrorBanner><span>⚠ 실행 상태: {execError}</span></ErrorBanner>}
          {controlError && <ErrorBanner><span>⚠ 제어: {controlError}</span></ErrorBanner>}
        </div>
      )}

      {mode === 'edit' ? (
        <WorkflowEditPane onExecuted={handleExecuted} />
      ) : (
        <>
          {/* Progress bar */}
          <div
            className="px-3 py-[6px] border-b-[1.5px] border-[var(--color-line-soft)] flex items-center gap-3 text-[13px]"
            style={{ background: 'var(--color-paper2)' }}
          >
            <span>
              {completedCount} / {totalNodes} 완료
            </span>
            <div className="flex-1 h-[10px] border-[1.5px] border-[var(--color-ink)] rounded-full bg-[var(--color-paper)] overflow-hidden relative">
              <div
                className="absolute left-0 top-0 h-full border-r-[1.5px] border-[var(--color-ink)]"
                style={{ width: `${progressPct}%`, background: 'var(--color-status-succeeded)' }}
              />
            </div>
            <span className="font-mono text-[12px]">{progressPct}%</span>
          </div>

          <div className="flex-1 flex min-h-0">
            {/* Canvas — ReactFlow (read-only) */}
            <div
              className="flex-1 border-r-[1.5px] border-[var(--color-ink)]"
              style={{ background: 'var(--color-paper2)', minHeight: 400 }}
            >
              {workflow && workflow.nodes.length > 0 ? (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  fitView
                  style={{ background: 'var(--color-paper2)' }}
                >
                  <Background color="var(--color-line-soft)" />
                  <Controls />
                </ReactFlow>
              ) : (
                <div className="h-full flex items-center justify-center text-[13px] text-[var(--color-ink4)]">
                  {wfLoading ? '로딩 중…' : '노드가 없는 워크플로우입니다. ✎ 편집 버튼으로 추가하세요.'}
                </div>
              )}
            </div>

            {/* Status summary panel */}
            <div
              className="overflow-auto p-2 flex flex-col flex-shrink-0"
              style={{ width: 280, background: 'var(--color-paper2)' }}
            >
              <div className="font-bold text-[13px] mb-[6px]">노드 상태 집계</div>
              <div className="h-[1.5px] bg-[var(--color-ink3)] rounded mb-3" />
              {execution ? (
                <div className="flex flex-col gap-2">
                  {Object.keys(summary).length === 0 ? (
                    <p className="text-[12px] text-[var(--color-ink4)] italic">
                      아직 노드 실행 정보가 없습니다.
                    </p>
                  ) : (
                    Object.entries(summary).map(([status, count]) => (
                      <div
                        key={status}
                        className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[6px] flex items-center justify-between"
                      >
                        <span className="font-bold text-[13px]">{status}</span>
                        <span className="font-mono text-[12px] text-[var(--color-ink3)]">{count}</span>
                      </div>
                    ))
                  )}
                  {execution.error && (
                    <div className="border-[1.5px] border-[var(--color-status-failed)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[6px]">
                      <div className="font-bold text-[12px] text-[var(--color-status-failed)] mb-[2px]">에러</div>
                      <div className="font-mono text-[10px] text-[var(--color-ink3)] break-all">
                        {execution.error}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-[12px] text-[var(--color-ink4)] italic">
                  실행 이력이 없습니다. /agent에서 워크플로우를 생성하거나 ✎ 편집으로 직접 만들어보세요.
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
