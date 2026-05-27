'use client';

import { useRef, useEffect, useState } from 'react';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import Steps from '@/components/common/Steps';
import RiskPill from '@/components/common/RiskPill';
import StatusPill from '@/components/common/StatusPill';
import NodeCard from '@/components/common/NodeCard';
import { useAgentStore, WorkspaceMode, AgentStep, ChatMessage } from '@/stores/agentStore';
import { useSSEStream } from '@/hooks/useSSEStream';
import { streamCreateSession } from '@/lib/api/agentApi';
import { ReactFlow, Background, Controls, Node, Edge, useNodesState, useEdgesState } from '@xyflow/react';
import { RiskLevel } from '@common/generated';
import type { NodeStatus } from '@/types';
import { executeWorkflow } from '@/lib/api/workflowApi';
import '@xyflow/react/dist/style.css';

// ─── Constants ─────────────────────────────────────────────────────────────────

const STEP_ORDER: AgentStep[] = [
  'security', 'intent', 'retriever', 'drafter', 'validator', 'qa_eval', 'promote',
];

const STEP_LABELS: Record<AgentStep, string> = {
  security:  '보안 검토',
  intent:    '의도 분류',
  retriever: '노드 검색',
  drafter:   '초안 생성',
  validator: '그래프 검증',
  qa_eval:   '품질 평가',
  promote:   '워크플로우 확정',
};

const DUMMY_SESSIONS = [
  { id: 's1', title: '주간 회의록 요약 자동화' },
  { id: 's2', title: '고객 피드백 분류 워크플로우' },
  { id: 's3', title: '마케팅 리포트 생성' },
];

const DUMMY_MESSAGES: ChatMessage[] = [
  {
    id: 'm1',
    role: 'user',
    content: '매주 월요일 오전 9시에 Google Sheets에서 데이터를 읽어서 Drive에 저장하고 Slack으로 알림을 보내는 워크플로우를 만들어줘.',
    timestamp: Date.now() - 300000,
  },
  {
    id: 'm2',
    role: 'agent',
    content: '보안 검토를 완료했습니다. 요청하신 워크플로우는 Google Sheets Read (저위험), Drive Save (중위험), Slack Post (고위험) 노드로 구성됩니다. 계속 진행할까요?',
    timestamp: Date.now() - 290000,
  },
  {
    id: 'm3',
    role: 'user',
    content: '네, 진행해주세요.',
    timestamp: Date.now() - 280000,
  },
  {
    id: 'm4',
    role: 'agent',
    content: '워크플로우 초안이 생성되었습니다. Cron Trigger → Sheets Read → Aggregate → Drive Save + Slack Post, 총 5개 노드로 구성됩니다. 편집 모드에서 확인하시겠습니까?',
    timestamp: Date.now() - 200000,
  },
];

// ─── FlowEditor (edit mode) ────────────────────────────────────────────────────

const FLOW_NODES: Node[] = [
  { id: '1', position: { x: 50,  y: 120 }, data: { label: '⏰ Cron Trigger' } },
  { id: '2', position: { x: 220, y: 120 }, data: { label: '📊 Sheets Read' } },
  { id: '3', position: { x: 390, y: 120 }, data: { label: 'Σ Aggregate' } },
  { id: '4', position: { x: 390, y: 260 }, data: { label: '📦 Drive Save' } },
  { id: '5', position: { x: 560, y: 120 }, data: { label: '# Slack Post' } },
];

const FLOW_EDGES: Edge[] = [
  { id: 'e1-2', source: '1', target: '2' },
  { id: 'e2-3', source: '2', target: '3' },
  { id: 'e3-4', source: '3', target: '4' },
  { id: 'e3-5', source: '3', target: '5' },
];

function FlowEditor() {
  const [nodes, , onNodesChange] = useNodesState(FLOW_NODES);
  const [edges, , onEdgesChange] = useEdgesState(FLOW_EDGES);

  return (
    <div className="w-full h-full">
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
    </div>
  );
}

// ─── ExecutionView (run mode) ──────────────────────────────────────────────────

const RUN_TIMELINE: Array<{ time: string; name: string; status: NodeStatus; elapsed: string }> = [
  { time: '09:00:00.124', name: 'Cron Trigger', status: 'succeeded', elapsed: '+12ms' },
  { time: '09:00:00.236', name: 'Sheets Read',  status: 'succeeded', elapsed: '+842ms' },
  { time: '09:00:01.078', name: 'Aggregate',    status: 'running',   elapsed: '…' },
  { time: '09:00:??',     name: 'Drive Save',   status: 'pending',   elapsed: '—' },
  { time: '09:00:??',     name: 'Slack Post',   status: 'pending',   elapsed: '—' },
];

const RUN_CANVAS_NODES: Array<{ icon: string; name: string; risk: RiskLevel; status: NodeStatus; x: number; y: number }> = [
  { icon: '⏰', name: 'Cron',       risk: RiskLevel.LOW,    status: 'succeeded', x: 24,  y: 80 },
  { icon: '📊', name: 'Sheets',    risk: RiskLevel.LOW,    status: 'succeeded', x: 160, y: 80 },
  { icon: 'Σ',  name: 'Aggregate', risk: RiskLevel.LOW,    status: 'running',   x: 296, y: 80 },
  { icon: '📦', name: 'Drive',     risk: RiskLevel.MEDIUM, status: 'pending',   x: 296, y: 190 },
  { icon: '#',  name: 'Slack',     risk: RiskLevel.HIGH,   status: 'pending',   x: 432, y: 80 },
];

function ExecutionView() {
  return (
    <div className="flex-1 flex min-h-0 overflow-hidden">
      {/* Canvas */}
      <div
        className="flex-1 relative border-r-[1.5px] border-[var(--color-ink)] overflow-hidden"
        style={{ background: 'var(--color-paper2)' }}
      >
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox="0 0 600 320"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <marker id="arr-run" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" fill="var(--color-ink)" />
            </marker>
          </defs>
          <path d="M 134 112 C 160 112, 160 112, 160 112" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" markerEnd="url(#arr-run)" />
          <path d="M 272 112 C 296 112, 296 112, 296 112" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" markerEnd="url(#arr-run)" />
          <path d="M 410 112 C 432 112, 432 112, 432 112" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" strokeDasharray="4 3" markerEnd="url(#arr-run)" />
          <path d="M 370 140 C 370 190, 340 222, 296 222" stroke="var(--color-ink)" strokeWidth="1.5" fill="none" strokeDasharray="4 3" markerEnd="url(#arr-run)" />
        </svg>
        {RUN_CANVAS_NODES.map((node) => (
          <div key={node.name} className="absolute" style={{ left: node.x, top: node.y }}>
            <NodeCard icon={node.icon} name={node.name} risk={node.risk} status={node.status} />
          </div>
        ))}
      </div>

      {/* Timeline panel */}
      <div
        className="overflow-auto p-2 flex flex-col flex-shrink-0"
        style={{ width: 280, background: 'var(--color-paper2)' }}
      >
        <div className="font-bold text-[13px] mb-[6px]">노드 이벤트 타임라인</div>
        <div className="h-[1.5px] bg-[var(--color-ink3)] rounded mb-3" />
        <div className="flex flex-col gap-2">
          {RUN_TIMELINE.map((item, i) => (
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
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

export default function AgentPage() {
  const {
    mode, setMode,
    sessionId, setSessionId,
    messages, addMessage,
    rationaleText, appendRationale, clearRationale,
    slotQuestion, setSlotQuestion,
    currentStep, setCurrentStep,
    readyToExecute, setReadyToExecute,
  } = useAgentStore();

  const [input, setInput] = useState('');
  const [activeSession, setActiveSession] = useState('s1');
  const [executeLoading, setExecuteLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useSSEStream(sessionId, {
    onResult: (frame) => {
      const payload = frame.payload as Record<string, unknown> | undefined;
      if (payload?.status === 'ready_to_execute') {
        setReadyToExecute({
          workflowId: payload.workflow_id as string,
          message: (payload.message as string) ?? '워크플로우가 완성됐습니다. 실행 버튼을 클릭해 실행하세요.',
        });
      }
    },
  });

  const handleExecute = async () => {
    if (!readyToExecute) return;
    setExecuteLoading(true);
    try {
      await executeWorkflow(readyToExecute.workflowId);
      setReadyToExecute(null);
      setMode('run');
    } catch {
      // 실행 실패는 run 모드로 전환하지 않고 버튼 유지
    } finally {
      setExecuteLoading(false);
    }
  };

  const displayMessages = messages.length > 0 ? messages : DUMMY_MESSAGES;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayMessages.length]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    addMessage({ id: `m${Date.now()}`, role: 'user', content: text, timestamp: Date.now() });
    setInput('');
    setStreaming(true);
    setCurrentStep(null);
    clearRationale();

    try {
      await streamCreateSession(
        { message: text, session_id: sessionId ?? undefined },
        (frame) => {
          switch (frame.frame_type) {
            case 'session':
              setSessionId(frame.session_id as string);
              break;
            case 'agent_node':
              setCurrentStep(frame.node_name as AgentStep);
              break;
            case 'rationale_delta':
              appendRationale(frame.delta as string);
              break;
            case 'slot_fill_question':
              setSlotQuestion({
                fieldName: frame.field_name as string,
                label: frame.label as string,
                risk: (frame.risk as RiskLevel) ?? RiskLevel.LOW,
              });
              break;
            case 'result': {
              const payload = frame.payload as Record<string, unknown> | undefined;
              if (payload?.status === 'ready_to_execute') {
                setReadyToExecute({
                  workflowId: payload.workflow_id as string,
                  message: (payload.message as string) ?? '워크플로우가 완성됐습니다.',
                });
              }
              if (typeof frame.message === 'string') {
                addMessage({ id: `a${Date.now()}`, role: 'agent', content: frame.message, timestamp: Date.now() });
              }
              break;
            }
            case 'error':
              addMessage({
                id: `e${Date.now()}`,
                role: 'agent',
                content: `오류가 발생했습니다: ${(frame.message as string) ?? '알 수 없는 오류'}`,
                timestamp: Date.now(),
              });
              break;
          }
        },
      );
    } catch (err) {
      addMessage({
        id: `e${Date.now()}`,
        role: 'agent',
        content: `연결 오류: ${err instanceof Error ? err.message : '서버에 연결할 수 없습니다.'}`,
        timestamp: Date.now(),
      });
    } finally {
      setStreaming(false);
    }
  };

  const stepIndex = currentStep ? STEP_ORDER.indexOf(currentStep) + 1 : 4;

  return (
    <div className="h-screen flex flex-col bg-[var(--color-paper)] overflow-hidden">
      <AppBar />

      <div className="flex flex-1 min-h-0">
        {/* ── Session Sidebar ─────────────────────────────────── */}
        <aside
          className="flex flex-col border-r-[1.5px] border-[var(--color-ink)] bg-[var(--color-sidebar)] flex-shrink-0"
          style={{ width: 220 }}
        >
          <div className="px-3 py-[10px] border-b-[1.5px] border-[var(--color-ink)]">
            <span className="font-bold text-[13px]">∿ 워크스페이스</span>
          </div>

          <div className="flex-1 overflow-auto py-2 flex flex-col gap-[2px] px-2">
            {DUMMY_SESSIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => { setActiveSession(s.id); setReadyToExecute(null); }}
                className={[
                  'w-full text-left px-[8px] py-[6px] rounded-[4px_8px_4px_8px] text-[12px] border-[1.5px] leading-snug',
                  activeSession === s.id
                    ? 'border-[var(--color-accent)] bg-[var(--color-hl)] text-[var(--color-accent)] font-bold'
                    : 'border-transparent hover:border-[var(--color-ink4)] text-[var(--color-ink2)]',
                ].join(' ')}
              >
                📝 {s.title}
              </button>
            ))}
          </div>

          <div className="px-2 py-2 border-t-[1.5px] border-[var(--color-line-soft)]">
            <Btn className="w-full justify-center text-[12px]">+ 새 대화</Btn>
          </div>
        </aside>

        {/* ── Main Workspace ───────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">

          {/* Mode toggle bar */}
          <div className="flex items-center gap-2 px-3 py-2 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)] flex-shrink-0">
            {(['wizard', 'edit', 'run'] as WorkspaceMode[]).map((m) => {
              const LABELS: Record<WorkspaceMode, string> = {
                wizard: '💬 대화',
                edit:   '✏️ 편집',
                run:    '▶ 실행',
              };
              return (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={[
                    'px-[10px] py-[3px] text-[12px] font-bold border-[1.5px] rounded-[4px_8px_4px_8px] transition-colors',
                    mode === m
                      ? 'bg-[var(--color-ink)] border-[var(--color-ink)] text-[var(--color-surface)]'
                      : 'bg-transparent border-[var(--color-ink4)] text-[var(--color-ink3)] hover:border-[var(--color-ink)] hover:text-[var(--color-ink)]',
                  ].join(' ')}
                >
                  {LABELS[m]}
                </button>
              );
            })}
            <div className="flex-1" />
            <span className="text-[12px] text-[var(--color-ink3)] border border-[var(--color-ink4)] px-[8px] py-[2px] rounded whitespace-nowrap">
              주간 회의록 요약 자동화
            </span>
          </div>

          {/* ── Wizard Mode ─────────────────────────────────────── */}
          {mode === 'wizard' && (
            <div className="flex-1 flex min-h-0">

              {/* Chat area */}
              <div className="flex-1 flex flex-col min-w-0 min-h-0">
                {/* Message list */}
                <div className="flex-1 overflow-auto px-4 py-3 flex flex-col gap-3">
                  {displayMessages.map((msg: ChatMessage) => (
                    <div
                      key={msg.id}
                      className={['flex items-end gap-2', msg.role === 'user' ? 'justify-end' : 'justify-start'].join(' ')}
                    >
                      {msg.role === 'agent' && (
                        <span className="w-[26px] h-[26px] rounded-full bg-[var(--color-agent)] text-white text-[10px] flex items-center justify-center flex-shrink-0 font-bold mb-[1px]">
                          AI
                        </span>
                      )}
                      <div
                        className={[
                          'max-w-[72%] px-[11px] py-[8px] text-[13px] leading-relaxed border-[1.5px]',
                          msg.role === 'user'
                            ? 'bg-[var(--color-hl)] border-[var(--color-accent)] rounded-[12px_8px_4px_12px]'
                            : 'bg-[var(--color-surface)] border-[var(--color-ink)] rounded-[8px_12px_12px_4px]',
                        ].join(' ')}
                      >
                        {msg.content}
                      </div>
                    </div>
                  ))}
                  {readyToExecute && (
                    <div className="flex items-end gap-2 justify-start">
                      <span className="w-[26px] h-[26px] rounded-full bg-[var(--color-agent)] text-white text-[10px] flex items-center justify-center flex-shrink-0 font-bold mb-[1px]">
                        AI
                      </span>
                      <div className="max-w-[72%] px-[11px] py-[8px] text-[13px] leading-relaxed border-[1.5px] bg-[var(--color-surface)] border-[var(--color-ink)] rounded-[8px_12px_12px_4px]">
                        <p className="mb-[8px]">{readyToExecute.message}</p>
                        <Btn onClick={handleExecute} disabled={executeLoading} className="text-[12px]">
                          {executeLoading ? '실행 중…' : '▶ 실행'}
                        </Btn>
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                {/* Input bar */}
                <div className="border-t-[1.5px] border-[var(--color-ink)] px-3 py-2 flex gap-2 bg-[var(--color-surface)] flex-shrink-0">
                  <textarea
                    className="flex-1 resize-none border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[10px] py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
                    rows={2}
                    placeholder={streaming ? 'AI가 처리 중입니다…' : '워크플로우를 자연어로 설명하세요… (Shift+Enter 줄바꿈)'}
                    value={input}
                    disabled={streaming}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                  />
                  <Btn onClick={handleSend} disabled={streaming} className="self-end">
                    {streaming ? '처리 중…' : '전송 ↑'}
                  </Btn>
                </div>
              </div>

              {/* Right panel */}
              <aside
                className="flex flex-col border-l-[1.5px] border-[var(--color-ink)] bg-[var(--color-paper2)] overflow-auto flex-shrink-0"
                style={{ width: 280 }}
              >
                {/* Agent steps */}
                <div className="p-3 border-b-[1.5px] border-[var(--color-line-soft)]">
                  <div className="font-bold text-[11px] text-[var(--color-ink3)] uppercase tracking-wider mb-[8px]">
                    AI 처리 단계
                  </div>
                  <Steps
                    items={STEP_ORDER.map((s) => STEP_LABELS[s])}
                    current={stepIndex}
                  />
                </div>

                {/* Rationale */}
                <div className="p-3 border-b-[1.5px] border-[var(--color-line-soft)]">
                  <div className="font-bold text-[11px] text-[var(--color-ink3)] uppercase tracking-wider mb-[8px]">
                    AI 판단 근거
                  </div>
                  <div className="text-[12px] text-[var(--color-ink2)] leading-relaxed bg-[var(--color-surface)] border-[1.5px] border-[var(--color-line-soft)] rounded-[4px_8px_4px_8px] p-[8px] min-h-[64px]">
                    {rationaleText || (
                      <span className="text-[var(--color-ink4)] italic">
                        AI가 분석 중이면 여기에 판단 근거가 표시됩니다.
                        <br />
                        노드 선택 이유, 리스크 평가 등…
                      </span>
                    )}
                  </div>
                </div>

                {/* SlotFill */}
                <div className="p-3">
                  <div className="font-bold text-[11px] text-[var(--color-ink3)] uppercase tracking-wider mb-[8px]">
                    추가 정보 요청
                  </div>
                  {slotQuestion ? (
                    <div className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] p-[10px] bg-[var(--color-surface)]">
                      <div className="flex items-center gap-2 mb-2">
                        <RiskPill level={slotQuestion.risk} />
                        <span className="text-[12px] font-bold">{slotQuestion.label}</span>
                      </div>
                      <input
                        type="text"
                        className="w-full border-[1.5px] border-[var(--color-ink)] rounded px-[8px] py-[4px] text-[12px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)]"
                        placeholder="답변 입력…"
                      />
                      <div className="mt-2 flex justify-end">
                        <Btn ghost className="text-[11px]">확인</Btn>
                      </div>
                    </div>
                  ) : (
                    <p className="text-[12px] text-[var(--color-ink4)] italic">현재 추가 정보 요청 없음.</p>
                  )}
                </div>
              </aside>
            </div>
          )}

          {/* ── Edit Mode ───────────────────────────────────────── */}
          {mode === 'edit' && (
            <div className="flex-1 min-h-0">
              <FlowEditor />
            </div>
          )}

          {/* ── Run Mode ────────────────────────────────────────── */}
          {mode === 'run' && (
            <div className="flex-1 flex flex-col min-h-0">
              {/* Run header */}
              <div className="flex items-center gap-[10px] px-3 py-2 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)] flex-shrink-0">
                <span className="font-bold text-[14px]">주간 회의록 요약 ▶</span>
                <StatusPill status="running" />
                <span className="text-[13px] text-[var(--color-ink3)]">
                  시작 09:00:00 · 경과{' '}
                  <span className="bg-[var(--color-hl)] px-[3px]">2.4s</span>
                </span>
                <div className="flex-1" />
                <Btn ghost>⏸ 일시정지</Btn>
                <Btn danger>⏹ 취소</Btn>
              </div>

              {/* Progress bar */}
              <div
                className="px-3 py-[6px] border-b-[1.5px] border-[var(--color-line-soft)] flex items-center gap-3 text-[13px] flex-shrink-0"
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

              <ExecutionView />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
