'use client';

import { Suspense, useRef, useEffect, useState, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import Steps from '@/components/common/Steps';
import RunMode from '@/components/agent/RunMode';
import { useAgentStore, WorkspaceMode, ChatMessage } from '@/stores/agentStore';
import { useSSEStream } from '@/hooks/useSSEStream';
import { streamCreateSession, streamSlotAnswer } from '@/lib/api/agentApi';
import { executeWorkflow } from '@/lib/api/workflowApi';
import { ReactFlow, Background, BackgroundVariant, Controls, ConnectionMode, useNodesState, useEdgesState, addEdge as rfAddEdge, type ReactFlowInstance, type Node as RFNode, type Edge as RFEdge, type Connection, type NodeMouseHandler } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { getCatalog } from '@/lib/api/nodeApi';
import type { NodeConfig, WorkflowExplanation } from '@common/generated';
import RiskPill from '@/components/common/RiskPill';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import NodePalette, { readPaletteDragPayload } from '@/components/workflow/NodePalette';
import CustomNode from '@/components/workflow/CustomNode';
import ConfirmCard from '@/components/agent/ConfirmCard';
import { STEP_ORDER, STEP_LABELS, nextMonotonicStep } from '@/lib/agentSteps';

// ─── Constants ─────────────────────────────────────────────────────────────────

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
      className="flex-shrink-0 flex flex-col border-l border-[var(--color-line-soft)] overflow-auto"
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
                  className="text-[12px] px-2 py-1 border border-[var(--color-line-soft)] rounded bg-[var(--color-paper)]"
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
                  className="text-[12px] px-2 py-1 border border-[var(--color-line-soft)] rounded bg-[var(--color-paper)]"
                >
                  <option value="">(미지정)</option>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : f.type === 'object' || f.type === 'array' ? (
                <textarea
                  value={value}
                  onChange={(e) => updateDraftField(f.name, e.target.value, f.type)}
                  className="text-[11px] font-mono px-2 py-1 border border-[var(--color-line-soft)] rounded bg-[var(--color-paper)]"
                  rows={4}
                  spellCheck={false}
                />
              ) : (f.type === 'number' || f.type === 'integer') ? (
                <input
                  type="text"
                  inputMode="decimal"
                  value={value}
                  onChange={(e) => updateDraftField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border border-[var(--color-line-soft)] rounded bg-[var(--color-paper)]"
                />
              ) : (
                <input
                  type="text"
                  value={value}
                  onChange={(e) => updateField(f.name, e.target.value, f.type)}
                  className="text-[12px] px-2 py-1 border border-[var(--color-line-soft)] rounded bg-[var(--color-paper)]"
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

  // 시안 휴지통 존 — 노드 드래그 중 하단에 나타나고, 위에서 드롭하면 삭제
  const [draggingNode, setDraggingNode] = useState(false);
  const [trashHover, setTrashHover] = useState(false);
  const trashRef = useRef<HTMLDivElement>(null);
  const isOverTrash = (clientX: number, clientY: number) => {
    const r = trashRef.current?.getBoundingClientRect();
    return !!r && clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom;
  };

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

  // 노드 생성 공통 — 드롭/클릭 양쪽에서 사용. input_schema default 주입 + 추가 토스트(시안 addCustomNode).
  const addFlowNode = useCallback(
    (
      spec: { node_id: string; node_type: string; name: string; risk_level: NodeConfig['risk_level'] },
      position: { x: number; y: number },
    ) => {
      const nodeConfig = catalog?.find((c) => c.node_id === spec.node_id);
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
            name: spec.name,
            risk_level: spec.risk_level,
            node_type: spec.node_type,
            node_id: spec.node_id,
            category: nodeConfig?.category,
            parameters: initParams,
            onDelete: (nodeId: string) => setNodes((prev) => prev.filter((n) => n.id !== nodeId)),
          },
        },
      ]);
      showToast(`'${spec.name}' 노드를 추가했습니다.`);
    },
    [catalog, setNodes],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const payload = readPaletteDragPayload(e);
      if (!payload || !rfInstance) return;
      const position = rfInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY });
      addFlowNode(payload, position);
    },
    [rfInstance, addFlowNode],
  );

  // 시안 addCustomNode: 팔레트 클릭으로도 캔버스 중앙(노드 수만큼 약간 스태거)에 추가
  const onPalettePick = useCallback(
    (node: NodeConfig) => {
      let position = { x: 120, y: 90 };
      const wrap = wrapperRef.current;
      if (wrap && rfInstance) {
        const r = wrap.getBoundingClientRect();
        position = rfInstance.screenToFlowPosition({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
      }
      const n = nodes.length;
      position = { x: position.x + ((n * 28) % 140) - 70, y: position.y + ((n * 28) % 140) - 70 };
      addFlowNode(
        { node_id: node.node_id, node_type: node.node_type, name: node.name, risk_level: node.risk_level },
        position,
      );
    },
    [rfInstance, nodes.length, addFlowNode],
  );

  const onNodeDragStart = useCallback(() => setDraggingNode(true), []);
  const onNodeDrag = useCallback<NodeMouseHandler>((e) => {
    setTrashHover(isOverTrash(e.clientX, e.clientY));
  }, []);
  const onNodeDragStop = useCallback<NodeMouseHandler>(
    (e, node) => {
      if (isOverTrash(e.clientX, e.clientY)) {
        setNodes((nds) => nds.filter((n) => n.id !== node.id));
        setEdges((eds) => eds.filter((ed) => ed.source !== node.id && ed.target !== node.id));
        showToast('노드를 제거했습니다.');
      }
      setDraggingNode(false);
      setTrashHover(false);
    },
    [setNodes, setEdges],
  );

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
        <NodePalette catalog={catalog} onPick={onPalettePick} />
      </div>
      <div ref={wrapperRef} className="flex-1 min-w-0 min-h-0 relative">
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
          onNodeDragStart={onNodeDragStart}
          onNodeDrag={onNodeDrag}
          onNodeDragStop={onNodeDragStop}
          nodeTypes={NODE_TYPES}
          fitView
          style={{ background: 'var(--color-surface)' }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1.3} color="#D8CBB8" />
          <Controls />
        </ReactFlow>

        {/* 시안 휴지통 존 — 노드 드래그 중 나타나고 위에서 드롭하면 삭제 */}
        <div
          ref={trashRef}
          className="absolute left-1/2 bottom-5 z-30 flex items-center gap-3 px-6 py-3 rounded-2xl border-2 pointer-events-none transition-all"
          style={{
            transform: `translateX(-50%) translateY(${draggingNode ? '0' : '12px'})`,
            opacity: draggingNode ? 1 : 0,
            background: trashHover ? '#ef4444' : 'rgba(255,255,255,.9)',
            borderColor: trashHover ? '#ef4444' : 'var(--color-line-soft)',
            borderStyle: trashHover ? 'solid' : 'dashed',
            boxShadow: trashHover
              ? '0 14px 32px -8px rgba(239,68,68,.5)'
              : '0 4px 12px rgba(70,58,48,.12)',
            color: trashHover ? '#fff' : 'var(--color-ink4)',
          }}
        >
          <Icon name="trash-2" className="w-[18px] h-[18px]" />
          <span className="text-[11px] font-semibold whitespace-nowrap tracking-[.02em]">
            {trashHover ? '놓으면 삭제됩니다' : '삭제하려면 드래그하세요'}
          </span>
        </div>
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
  // two-shot 스킬 선택 카드 (skill_selection 프레임 수신 시 표시, REQ-013)
  const [skillSelection, setSkillSelection] = useState<{
    prompt: string;
    options: { skill_id: string; name: string; description?: string }[];
    allowSkip: boolean;
  } | null>(null);
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

  // round1 생성 / round2 슬롯 응답 공용 SSE 프레임 핸들러.
  const handleFrame = (frame: Record<string, unknown>) => {
    switch (frame.frame_type) {
      case 'session':
        setSessionId(frame.session_id as string);
        break;
      case 'agent_node': {
        const toolName = frame.agent_node_name as string;
        // SSE 콜백은 클로저라 구조분해된 currentStep이 stale될 수 있어 store에서 최신값을 읽는다.
        const prev = useAgentStore.getState().currentStep;
        setCurrentStep(nextMonotonicStep(prev, toolName));
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
      case 'skill_selection': {
        const options = Array.isArray(frame.options)
          ? (frame.options as { skill_id: string; name: string; description?: string }[])
          : [];
        setSkillSelection({
          prompt: (frame.prompt as string) ?? '적용할 스킬을 선택해 주세요.',
          options,
          allowSkip: frame.allow_skip !== false,
        });
        break;
      }
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
  };

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
    setSkillSelection(null);
    clearRationale();

    try {
      await streamCreateSession(
        { message: text, session_id: sessionId ?? undefined },
        handleFrame,
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

  // two-shot 2차: 스킬 선택(또는 건너뛰기) → round=2 스트림을 같은 handleFrame으로 이어 처리.
  const submitSkillSelection = async (skillId: string | null) => {
    if (!sessionId || streaming) return;
    const chosen = skillId
      ? (skillSelection?.options.find((o) => o.skill_id === skillId)?.name ?? '선택한 스킬')
      : '건너뛰기';
    addMessage({ id: `sk${Date.now()}`, role: 'user', content: `스킬: ${chosen}`, timestamp: Date.now() });
    setSkillSelection(null);
    setStreaming(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamSlotAnswer(sessionId, skillId, handleFrame, controller.signal);
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
    setSkillSelection(null);
    autoSentRef.current = false;
    setMode('wizard');
  };

  return (
    <div className="h-screen flex flex-col bg-[var(--color-paper)] overflow-hidden">
      <AppBar />

      <div className="flex flex-1 min-h-0">
        {/* ── Session Sidebar ─────────────────────────────────── */}
        <aside
          className="flex flex-col border-r border-[var(--color-line-soft)] bg-[var(--color-sidebar)] flex-shrink-0"
          style={{ width: 220 }}
        >
          <div className="px-3 py-[10px] border-b border-[var(--color-line-soft)]">
            <span className="font-bold text-[13px]">∿ 워크스페이스</span>
          </div>

          <div className="flex-1 overflow-auto py-2 flex flex-col gap-[2px] px-2">
            {sessionId ? (
              <div className="px-[8px] py-[6px] rounded-lg text-[12px] border-[1.5px] border-[var(--color-accent)] bg-[var(--color-hl)] text-[var(--color-accent)] font-bold leading-snug">
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
          <div className="flex items-center gap-2 px-3 py-2.5 border-b border-[var(--color-line-soft)] bg-[var(--color-surface)] flex-shrink-0">
            <div className="flex items-center space-x-1.5">
              {(['wizard', 'edit', 'run'] as WorkspaceMode[]).map((m) => {
                const META: Record<WorkspaceMode, { icon: string; label: string }> = {
                  wizard: { icon: 'message-circle', label: '대화' },
                  edit:   { icon: 'edit-3', label: '편집' },
                  run:    { icon: 'play', label: '실행' },
                };
                const active = mode === m;
                return (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={[
                      'px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center space-x-1',
                      active
                        ? 'bg-[var(--color-accent)] text-white shadow-sm'
                        : 'text-[var(--color-ink3)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper)]',
                    ].join(' ')}
                  >
                    <Icon name={META[m].icon} className="w-3.5 h-3.5" />
                    <span>{META[m].label}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex-1" />
            {readyToExecute && (
              <span className="text-[12px] text-[var(--color-ink3)] border border-[var(--color-line-soft)] px-[8px] py-[2px] rounded-lg whitespace-nowrap font-mono">
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
                          'max-w-[72%] px-3.5 py-2.5 text-[13px] font-medium leading-relaxed shadow-sm break-keep',
                          msg.role === 'user'
                            ? 'bg-[var(--color-accent)] text-[#FCF7EF] rounded-2xl rounded-tr-md'
                            : 'bg-[var(--color-paper2)] border border-[var(--color-line-soft)] text-[var(--color-ink)] rounded-2xl rounded-tl-md',
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
                      <div className="max-w-[72%] px-3.5 py-2.5 text-[13px] leading-relaxed border border-[var(--color-line-soft)] bg-[var(--color-paper2)] rounded-2xl rounded-tl-md text-[var(--color-ink3)] italic animate-pulse">
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
                  {skillSelection && !streaming && (
                    <div className="self-start max-w-[80%] border-[1.5px] border-[var(--color-accent)] rounded-[8px_12px_12px_4px] bg-[var(--color-surface)] p-3">
                      <div className="text-[12px] font-bold text-[var(--color-ink)] mb-2">{skillSelection.prompt}</div>
                      <div className="flex flex-col gap-1.5">
                        {skillSelection.options.map((opt) => (
                          <button
                            key={opt.skill_id}
                            onClick={() => void submitSkillSelection(opt.skill_id)}
                            className="text-left px-[10px] py-[7px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] bg-[var(--color-paper)] hover:border-[var(--color-accent)] hover:bg-[var(--color-hl)] transition-colors"
                          >
                            <div className="text-[12px] font-bold text-[var(--color-ink)]">{opt.name}</div>
                            {opt.description && (
                              <div className="text-[11px] text-[var(--color-ink3)] mt-0.5 leading-snug">{opt.description}</div>
                            )}
                          </button>
                        ))}
                      </div>
                      {skillSelection.allowSkip && (
                        <div className="mt-2 flex justify-end">
                          <button
                            onClick={() => void submitSkillSelection(null)}
                            className="text-[11px] text-[var(--color-ink3)] underline hover:text-[var(--color-ink)]"
                          >
                            건너뛰기 (스킬 없이 진행)
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                {/* Input bar */}
                <div className="border-t border-[var(--color-line-soft)] px-3 py-2 flex gap-2 bg-[var(--color-surface)] flex-shrink-0">
                  <textarea
                    className="flex-1 resize-none border border-[var(--color-line-soft)] rounded-lg px-[10px] py-[7px] text-[13px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
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
                className="flex flex-col border-l border-[var(--color-line-soft)] bg-[var(--color-paper2)] overflow-auto flex-shrink-0"
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
                  <div className="text-[12px] text-[var(--color-ink2)] leading-relaxed bg-[var(--color-surface)] border-[1.5px] border-[var(--color-line-soft)] rounded-lg p-[8px] min-h-[64px]">
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
                    <div className="border border-[var(--color-line-soft)] rounded-lg p-[10px] bg-[var(--color-surface)]">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-[12px] font-bold">{slotQuestion.question}</span>
                      </div>
                      <input
                        type="text"
                        className="w-full border border-[var(--color-line-soft)] rounded px-[8px] py-[4px] text-[12px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)]"
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
