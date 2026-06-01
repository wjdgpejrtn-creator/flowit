'use client';

import { Suspense, useRef, useEffect, useState, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import Steps from '@/components/common/Steps';
import RunMode from '@/components/agent/RunMode';
import { useAgentStore, WorkspaceMode, AgentStep, ChatMessage } from '@/stores/agentStore';
import { useSSEStream } from '@/hooks/useSSEStream';
import { streamCreateSession } from '@/lib/api/agentApi';
import { executeWorkflow } from '@/lib/api/workflowApi';
import { ReactFlow, Background, Controls, ConnectionMode, useNodesState, useEdgesState, addEdge as rfAddEdge, type ReactFlowInstance, type Node as RFNode, type Edge as RFEdge, type Connection, type NodeMouseHandler } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { getCatalog } from '@/lib/api/nodeApi';
import type { NodeConfig, WorkflowExplanation } from '@common/generated';
import RiskPill from '@/components/common/RiskPill';
import NodePalette, { readPaletteDragPayload } from '@/components/workflow/NodePalette';
import CustomNode from '@/components/workflow/CustomNode';
import ConfirmCard from '@/components/agent/ConfirmCard';

// ─── Constants ─────────────────────────────────────────────────────────────────

const STEP_ORDER: AgentStep[] = [
  'security', 'intent', 'retriever', 'drafter', 'validator', 'qa_eval', 'promote',
];

const TOOL_TO_STEP: Record<string, AgentStep> = {
  // supervisor 노드
  load_memory:       'security',
  analyze_intent:    'intent',
  // composer fixed DAG 노드
  compress:          'security',
  security:          'security',
  intent:            'intent',
  consultant:        'intent',
  slot_fill:         'intent',
  search_nodes:      'retriever',
  draft_workflow:    'drafter',
  retry_draft:       'drafter',
  validate_workflow: 'validator',
  qa_evaluator:      'qa_eval',
  validation_failed: 'validator',
  qa_failed:         'qa_eval',
  promote:           'promote',
  save_workflow:     'promote',
  confirm_result:    'promote',
  save_memory:       'promote',
};

const STEP_LABELS: Record<AgentStep, string> = {
  security:  '보안 검토',
  intent:    '의도 분류',
  retriever: '노드 검색',
  drafter:   '초안 생성',
  validator: '그래프 검증',
  qa_eval:   '품질 평가',
  promote:   '워크플로우 확정',
};

const NODE_TYPES = { custom: CustomNode };

// ─── FlowEditor helpers ────────────────────────────────────────────────────────

interface FlowSchemaField {
  name: string;
  type: string;
  required: boolean;
  enumOptions?: unknown[];
  description?: string;
  default?: unknown;
}

function parseFlowSchema(input: unknown): FlowSchemaField[] {
  if (!input || typeof input !== 'object') return [];
  const schema = input as { properties?: Record<string, unknown>; required?: string[] };
  if (!schema.properties) return [];
  const req = new Set(schema.required ?? []);
  return Object.entries(schema.properties).map(([name, raw]) => {
    const def = (raw ?? {}) as { type?: string; enum?: unknown[]; description?: string; default?: unknown };
    return {
      name,
      type: def.type ?? 'string',
      required: req.has(name),
      enumOptions: def.enum,
      description: def.description,
      default: def.default,
    };
  });
}

function coerceFlowField(raw: string, type: string): unknown {
  if (type === 'boolean') return raw === 'true';
  return raw;
}

function stringifyFlowField(value: unknown, type: string): string {
  if (value === undefined || value === null) return '';
  if (type === 'object' || type === 'array') {
    try { return JSON.stringify(value, null, 2); } catch { return String(value); }
  }
  return String(value);
}

// ─── FlowNodeConfigPanel ───────────────────────────────────────────────────────

interface FlowNodeConfigPanelProps {
  nodeData: Record<string, unknown>;
  catalog: NodeConfig[] | null;
  onClose: () => void;
  onUpdateParams: (params: Record<string, unknown>) => void;
}

function FlowNodeConfigPanel({ nodeData, catalog, onClose, onUpdateParams }: FlowNodeConfigPanelProps) {
  const name = nodeData.name as string;
  const nodeType = nodeData.node_type as string;
  const catalogNodeId = nodeData.node_id as string | undefined;
  const params = (nodeData.parameters ?? {}) as Record<string, unknown>;
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [draftTexts, setDraftTexts] = useState<Record<string, string>>({});

  const nodeConfig = catalog?.find((c) => c.node_id === catalogNodeId) ?? null;
  const fields = parseFlowSchema(nodeConfig?.input_schema);

  const clearError = (fieldName: string) =>
    setFieldErrors((e) => { const { [fieldName]: _, ...rest } = e; return rest; });

  // Initialize draft texts for draft-managed field types when catalog first loads
  useEffect(() => {
    if (!nodeConfig) return;
    setDraftTexts((prev) => {
      const next = { ...prev };
      for (const f of parseFlowSchema(nodeConfig.input_schema)) {
        if ((f.type === 'object' || f.type === 'array' || f.type === 'number' || f.type === 'integer') && !(f.name in next)) {
          next[f.name] = stringifyFlowField(params[f.name] ?? f.default, f.type);
        }
      }
      return next;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeConfig]);

  // For string/boolean/enum: direct commit to params
  const updateField = (fieldName: string, raw: string, type: string) => {
    const next = { ...params };
    const value = coerceFlowField(raw, type);
    if (value === undefined) delete next[fieldName];
    else next[fieldName] = value;
    clearError(fieldName);
    onUpdateParams(next);
  };

  // For number/integer/object/array: store raw draft always, commit to params only when valid
  const updateDraftField = (fieldName: string, raw: string, type: string) => {
    setDraftTexts((prev) => ({ ...prev, [fieldName]: raw }));
    const next = { ...params };
    if (type === 'number' || type === 'integer') {
      if (raw === '') {
        delete next[fieldName];
        clearError(fieldName);
      } else {
        const n = Number(raw);
        if (!Number.isFinite(n)) {
          setFieldErrors((e) => ({ ...e, [fieldName]: '숫자 형식이 올바르지 않습니다.' }));
          return;
        }
        next[fieldName] = n;
        clearError(fieldName);
      }
    } else {
      if (raw.trim() === '') {
        next[fieldName] = type === 'array' ? [] : {};
        clearError(fieldName);
      } else {
        try {
          next[fieldName] = JSON.parse(raw);
          clearError(fieldName);
        } catch {
          setFieldErrors((e) => ({ ...e, [fieldName]: 'JSON 형식이 올바르지 않습니다.' }));
          return;
        }
      }
    }
    onUpdateParams(next);
  };

  return (
    <div
      className="flex-shrink-0 flex flex-col border-l-[1.5px] border-[var(--color-ink)] overflow-auto"
      style={{ width: 300, background: 'var(--color-surface)' }}
    >
      <div className="p-3 border-b-[1.5px] border-[var(--color-line-soft)]">
        <div className="flex items-center justify-between gap-2">
          <div className="font-bold text-[13px] truncate">{nodeConfig?.name ?? name}</div>
          <button
            type="button"
            onClick={onClose}
            className="text-[18px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] leading-none"
            aria-label="닫기"
          >
            ×
          </button>
        </div>
        {nodeConfig && (
          <div className="mt-1 flex items-center gap-2">
            <RiskPill level={nodeConfig.risk_level} />
            <span className="font-mono text-[10px] text-[var(--color-ink3)] truncate">{nodeType}</span>
          </div>
        )}
        {nodeConfig?.description && (
          <div className="text-[11px] text-[var(--color-ink3)] mt-2">{nodeConfig.description}</div>
        )}
      </div>

      <div className="p-3 flex-1 flex flex-col gap-3">
        {!catalog && <div className="text-[12px] text-[var(--color-ink4)] italic">카탈로그 로딩 중…</div>}
        {catalog && !nodeConfig && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">노드 정의를 찾을 수 없습니다.</div>
        )}
        {nodeConfig && fields.length === 0 && (
          <div className="text-[12px] text-[var(--color-ink4)] italic">설정 가능한 파라미터가 없습니다.</div>
        )}
        {fields.map((f) => {
          const isDraft = f.type === 'object' || f.type === 'array' || f.type === 'number' || f.type === 'integer';
          const value = isDraft
            ? (draftTexts[f.name] ?? stringifyFlowField(params[f.name] ?? f.default, f.type))
            : stringifyFlowField(params[f.name] ?? f.default, f.type);
          return (
            <label key={f.name} className="flex flex-col gap-1">
              <span className="text-[12px] font-bold flex items-center gap-1">
                {f.name}
                {f.required && <span className="text-[var(--color-status-failed)]">*</span>}
                <span className="font-mono text-[10px] text-[var(--color-ink4)] font-normal">: {f.type}</span>
              </span>
              {f.description && <span className="text-[11px] text-[var(--color-ink3)]">{f.description}</span>}
              {f.enumOptions ? (
                <select
                  value={value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                >
                  <option value="">(선택)</option>
                  {f.enumOptions.map((opt) => (
                    <option key={String(opt)} value={String(opt)}>{String(opt)}</option>
                  ))}
                </select>
              ) : f.type === 'boolean' ? (
                <select
                  value={value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                >
                  <option value="">(미지정)</option>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : f.type === 'object' || f.type === 'array' ? (
                <textarea
                  value={value}
                  onChange={(e) => updateDraftField(f.name, e.target.value, f.type)}
                  className="text-[11px] font-mono px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                  rows={4}
                  spellCheck={false}
                />
              ) : (f.type === 'number' || f.type === 'integer') ? (
                <input
                  type="text"
                  inputMode="decimal"
                  value={value}
                  onChange={(e) => updateDraftField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                />
              ) : (
                <input
                  type="text"
                  value={value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper)]"
                />
              )}
              {fieldErrors[f.name] && (
                <span className="text-[11px] text-[var(--color-status-failed)]">
                  {fieldErrors[f.name]}
                </span>
              )}
            </label>
          );
        })}
      </div>
    </div>
  );
}

// ─── FlowEditor (edit mode — NodePalette 좌측 + 드래그&드롭 중앙 배치) ─────────

function FlowEditor() {
  const [nodes, setNodes, onNodesChange] = useNodesState<RFNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<RFEdge>([]);
  const [catalog, setCatalog] = useState<NodeConfig[] | null>(null);
  const [selectedNodeIdForConfig, setSelectedNodeIdForConfig] = useState<string | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getCatalog();
        if (!cancelled) setCatalog(data);
      } catch {
        if (!cancelled) setCatalog([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Bug 1 fix: 엣지 연결 핸들러
  const onConnect = useCallback((conn: Connection) => {
    // Loose 모드에서 자기 자신 연결(self-loop) 방지
    if (conn.source === conn.target) return;
    setEdges((eds) => rfAddEdge(conn, eds));
  }, [setEdges]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const payload = readPaletteDragPayload(e);
    if (!payload || !rfInstance) return;
    const position = rfInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY });

    // input_schema default 값 자동 주입
    const nodeConfig = catalog?.find((c) => c.node_id === payload.node_id);
    const initParams: Record<string, unknown> = {};
    if (nodeConfig?.input_schema) {
      const schema = nodeConfig.input_schema as { properties?: Record<string, { default?: unknown }> };
      for (const [key, def] of Object.entries(schema.properties ?? {})) {
        if (def.default !== undefined) initParams[key] = def.default;
      }
    }

    setNodes((nds) => [
      ...nds,
      {
        id: `node-${Date.now()}`,
        type: 'custom',
        position,
        data: {
          name: payload.name,
          risk_level: payload.risk_level,
          node_type: payload.node_type,
          node_id: payload.node_id,
          parameters: initParams,
          onDelete: (nodeId: string) => setNodes((prev) => prev.filter((n) => n.id !== nodeId)),
        },
      },
    ]);
  }, [rfInstance, catalog, setNodes]);

  // Bug 2 fix: 더블클릭 → 설정 패널 열기
  const onNodeDoubleClick = useCallback<NodeMouseHandler>((_e, node) => {
    setSelectedNodeIdForConfig(node.id);
  }, []);

  const selectedNode = nodes.find((n) => n.id === selectedNodeIdForConfig) ?? null;

  const handleUpdateParams = useCallback((params: Record<string, unknown>) => {
    if (!selectedNodeIdForConfig) return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id !== selectedNodeIdForConfig ? n : { ...n, data: { ...n.data, parameters: params } },
      ),
    );
  }, [selectedNodeIdForConfig, setNodes]);

  return (
    <div className="flex h-full w-full">
      <div className="flex-shrink-0 min-h-0 flex flex-col">
        <NodePalette catalog={catalog} />
      </div>
      <div ref={wrapperRef} className="flex-1 min-w-0 min-h-0">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          connectionMode={ConnectionMode.Loose}
          onInit={setRfInstance}
          onDrop={onDrop}
          onDragOver={onDragOver}
          onNodeDoubleClick={onNodeDoubleClick}
          nodeTypes={NODE_TYPES}
          fitView
          style={{ background: 'var(--color-paper2)' }}
        >
          <Background color="var(--color-line-soft)" />
          <Controls />
        </ReactFlow>
      </div>
      {selectedNode && (
        <FlowNodeConfigPanel
          nodeData={selectedNode.data as Record<string, unknown>}
          catalog={catalog}
          onClose={() => setSelectedNodeIdForConfig(null)}
          onUpdateParams={handleUpdateParams}
        />
      )}
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

function AgentPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const {
    mode, setMode,
    sessionId, setSessionId,
    messages, addMessage, clearMessages,
    rationaleText, appendRationale, clearRationale,
    slotQuestion, setSlotQuestion,
    currentStep, setCurrentStep,
    readyToExecute, setReadyToExecute,
  } = useAgentStore();

  const [input, setInput] = useState('');
  const [executeLoading, setExecuteLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const autoSentRef = useRef(false);

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  useSSEStream(sessionId, {
    onResult: (frame) => {
      const payload = frame.payload as Record<string, unknown> | undefined;
      if (payload?.status === 'ready_to_execute') {
        setReadyToExecute({
          workflowId: payload.workflow_id as string,
          message: (payload.message as string) ?? '워크플로우가 완성됐습니다. 실행 버튼을 클릭해 실행하세요.',
          explanation: payload.explanation as WorkflowExplanation | undefined,
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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

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
            case 'agent_node': {
              const toolName = frame.agent_node_name as string;
              setCurrentStep(TOOL_TO_STEP[toolName] ?? toolName as AgentStep);
              break;
            }
            case 'rationale_delta':
              appendRationale(frame.delta as string);
              break;
            case 'slot_fill_question':
              setSlotQuestion({
                fieldName: frame.field_name as string,
                question: frame.question as string,
              });
              break;
            case 'result': {
              const payload = frame.payload as Record<string, unknown> | undefined;
              if (payload?.status === 'ready_to_execute') {
                setReadyToExecute({
                  workflowId: payload.workflow_id as string,
                  message: (payload.message as string) ?? '워크플로우가 완성됐습니다.',
                  explanation: payload.explanation as WorkflowExplanation | undefined,
                });
              }
              const msg = payload?.message;
              if (typeof msg === 'string') {
                addMessage({ id: `a${Date.now()}`, role: 'agent', content: msg, timestamp: Date.now() });
              }
              break;
            }
            case 'chat_message': {
              const chatContent = (frame.content ?? frame.message) as string | undefined;
              if (typeof chatContent === 'string') {
                addMessage({ id: `c${Date.now()}`, role: 'agent', content: chatContent, timestamp: Date.now() });
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
        controller.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
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

  // 홈에서 ?q=...&autosend=1로 진입 시 1회만 자동 전송 + URL 정리
  useEffect(() => {
    const q = searchParams.get('q');
    const autosend = searchParams.get('autosend');
    if (q && autosend === '1' && !autoSentRef.current && !streaming) {
      autoSentRef.current = true;
      setInput(q);
      void handleSend(q);
      router.replace('/agent', { scroll: false });
    }
    // handleSend는 매 렌더 새로 만들어지므로 의도적으로 dep에서 제외
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const stepIndex = currentStep ? STEP_ORDER.indexOf(currentStep) + 1 : 0;
  const handleNewChat = () => {
    abortRef.current?.abort();
    clearMessages();
    clearRationale();
    setSessionId('');
    setCurrentStep(null);
    setSlotQuestion(null);
    setReadyToExecute(null);
    autoSentRef.current = false;
    setMode('wizard');
  };

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
            {sessionId ? (
              <div className="px-[8px] py-[6px] rounded-[4px_8px_4px_8px] text-[12px] border-[1.5px] border-[var(--color-accent)] bg-[var(--color-hl)] text-[var(--color-accent)] font-bold leading-snug">
                💬 현재 대화
                <div className="font-mono text-[10px] text-[var(--color-ink3)] mt-[2px] font-normal break-all">
                  {sessionId.slice(0, 8)}…
                </div>
              </div>
            ) : (
              <p className="px-[8px] py-[10px] text-[11px] text-[var(--color-ink4)] italic leading-snug">
                새 대화를 시작하세요.
              </p>
            )}
          </div>

          <div className="px-2 py-2 border-t-[1.5px] border-[var(--color-line-soft)]">
            <Btn onClick={handleNewChat} className="w-full justify-center text-[12px]">
              + 새 대화
            </Btn>
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
            {readyToExecute && (
              <span className="text-[12px] text-[var(--color-ink3)] border border-[var(--color-ink4)] px-[8px] py-[2px] rounded whitespace-nowrap font-mono">
                {readyToExecute.workflowId.slice(0, 8)}…
              </span>
            )}
          </div>

          {/* ── Wizard Mode ─────────────────────────────────────── */}
          {mode === 'wizard' && (
            <div className="flex-1 flex min-h-0">

              {/* Chat area */}
              <div className="flex-1 flex flex-col min-w-0 min-h-0">
                {/* Message list */}
                <div className="flex-1 overflow-auto px-4 py-3 flex flex-col gap-3">
                  {messages.length === 0 && !streaming && (
                    <div className="flex-1 flex items-center justify-center text-center px-6">
                      <div className="text-[13px] text-[var(--color-ink4)] leading-relaxed max-w-[420px]">
                        만들고 싶은 워크플로우를 자연어로 설명해주세요.<br />
                        예: <span className="text-[var(--color-ink3)]">&ldquo;매주 월요일 9시에 광고 시트를 읽어서 요약하고 Slack으로 보내줘&rdquo;</span>
                      </div>
                    </div>
                  )}
                  {messages.map((msg: ChatMessage) => (
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
                  {streaming && (
                    <div className="flex items-end gap-2 justify-start">
                      <span className="w-[26px] h-[26px] rounded-full bg-[var(--color-agent)] text-white text-[10px] flex items-center justify-center flex-shrink-0 font-bold mb-[1px]">
                        AI
                      </span>
                      <div className="max-w-[72%] px-[11px] py-[8px] text-[13px] leading-relaxed border-[1.5px] bg-[var(--color-surface)] border-[var(--color-line-soft)] rounded-[8px_12px_12px_4px] text-[var(--color-ink3)] italic animate-pulse">
                        워크플로우를 분석 중입니다… (1~2분 소요)
                      </div>
                    </div>
                  )}
                  {readyToExecute && (
                    <ConfirmCard
                      message={readyToExecute.message}
                      explanation={readyToExecute.explanation}
                      onExecute={handleExecute}
                      onEdit={() => setMode('edit')}
                      loading={executeLoading}
                    />
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
                        void handleSend();
                      }
                    }}
                  />
                  <Btn onClick={() => void handleSend()} disabled={streaming} className="self-end">
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
                        <span className="text-[12px] font-bold">{slotQuestion.question}</span>
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
            <div className="flex-1 flex flex-col min-h-0 overflow-y-auto p-3">
              <RunMode />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AgentPage() {
  return (
    <Suspense fallback={<div className="h-screen flex items-center justify-center text-[13px] text-[var(--color-ink3)]">로딩 중…</div>}>
      <AgentPageContent />
    </Suspense>
  );
}
