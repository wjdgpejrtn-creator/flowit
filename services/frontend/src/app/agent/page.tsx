'use client';

import { Suspense, useRef, useEffect, useState, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import RunMode from '@/components/agent/RunMode';
import { useAgentStore, WorkspaceMode, ChatMessage, AgentSession } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';
import { useSSEStream } from '@/hooks/useSSEStream';
import { streamCreateSession, streamSlotAnswer } from '@/lib/api/agentApi';
import { getWorkflow, validateWorkflow } from '@/lib/api/workflowApi';
import { useWorkflowStore } from '@/stores/workflowStore';
import WorkflowEditPane from '@/components/workflow/WorkflowEditPane';
import { ReactFlow, Background, BackgroundVariant, Controls, ConnectionMode, useNodesState, useEdgesState, addEdge as rfAddEdge, type ReactFlowInstance, type Node as RFNode, type Edge as RFEdge, type Connection, type NodeMouseHandler } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { getCatalog } from '@/lib/api/nodeApi';
import type { NodeConfig, WorkflowExplanation } from '@common/generated';
import { RiskLevel } from '@common/generated';
import RiskDot from '@/components/common/RiskDot';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import NodePalette, { readPaletteDragPayload } from '@/components/workflow/NodePalette';
import CustomNode from '@/components/workflow/CustomNode';
import ConfirmCard from '@/components/agent/ConfirmCard';
import { UserBubble, AiTurn, AgentWorkProcess, SkillSelectionCard } from '@/components/agent/ChatTurns';
import WorkflowCanvasPanel, { type CanvasNodeChip } from '@/components/agent/WorkflowCanvasPanel';
import { nextMonotonicStep, stepIndexFor, displayLabels } from '@/lib/agentSteps';
import { computeFilledParams } from '@/lib/filledParams';
import { resolveNodeIcon } from '@/lib/nodeIcon';

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
            <RiskDot level={nodeConfig.risk_level} />
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

// 문서(탭) 단위 1회성 플래그 — 모듈 스코프라 전체 새로고침(JS 컨텍스트 재생성) 때만 false로
// 초기화되고, SPA 클라이언트 네비게이션(대시보드→AI채팅 재진입)에서는 값이 유지된다.
// 이를 이용해 "새로고침/첫 진입(=persist 복원 대화 이어가기)"과 "재진입(=새 대화로 시작)"을 구분.
let agentDocumentLoadConsumed = false;

function AgentPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const {
    mode, setMode,
    sessionId, setSessionId,
    sessions, addSession, restoreSession,
    viewingSession, setViewingSession,
    messages, addMessage, clearMessages,
    rationaleText, appendRationale, clearRationale,
    slotQuestion, setSlotQuestion,
    currentStep, setCurrentStep,
    compositeFlow, setCompositeFlow,
    readyToExecute, setReadyToExecute,
  } = useAgentStore();

  const userName = useAuthStore().userName || '사용자';
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [canvasOpen, setCanvasOpen] = useState(false);
  // 컨펌 게이트 저장 검증 실패 피드백 — messages에 넣으면 ConfirmCard보다 먼저 렌더돼
  // 카드 위에 표시되는 버그(#368). 별도 상태로 분리해 ConfirmCard '아래'에 렌더한다.
  const [saveError, setSaveError] = useState<string | null>(null);
  // two-shot 스킬 선택 카드 (skill_selection 프레임 수신 시 표시, REQ-013)
  const [skillSelection, setSkillSelection] = useState<{
    prompt: string;
    options: { skill_id: string; name: string; description?: string }[];
    allowSkip: boolean;
  } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const autoSentRef = useRef(false);
  // StrictMode(dev)의 effect 더블 invoke가 같은 마운트에서 두 번 실행되지 않도록 인스턴스 가드.
  const didMountResetRef = useRef(false);

  // 완성된 워크플로우를 편집 캔버스에 로드 — useWorkflowStore(WorkflowEditPane이 읽음).
  const setLoadedWorkflow = useWorkflowStore((s) => s.setWorkflow);
  const loadedWorkflow = useWorkflowStore((s) => s.workflow);
  const [editCatalog, setEditCatalog] = useState<NodeConfig[] | null>(null);
  // refine(편집)은 같은 workflow_id를 유지(버전 업데이트)하므로 workflowId만으론 캔버스 재로드
  // effect가 재발화하지 않는다 → 수정본이 안 그려지고 이전 워크플로우가 stale로 남는다. 결과
  // 프레임이 올 때마다 증가하는 nonce를 effect 의존성에 넣어 id 불변이어도 재로드를 강제한다.
  const [canvasReloadKey, setCanvasReloadKey] = useState(0);

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  // 페이지 진입 시 이전 세션 정리.
  // Zustand 싱글턴은 페이지 이동 후 재진입해도 상태가 남아있으므로
  // 대시보드 → AI 채팅 재진입 시 빈 대화창으로 시작하도록 초기화.
  // 단, 두 경우엔 초기화를 건너뛰어 대화를 이어간다:
  //  ① readyToExecute가 있으면 워크플로우 완성 후 이탈→복귀 흐름.
  //  ② 문서 최초 로드(새로고침/첫 진입) — persist로 복원된 대화를 그대로 유지(버그 C).
  //     SPA 재진입에서만 아카이브+초기화가 동작하도록 모듈 플래그로 구분한다.
  useEffect(() => {
    if (didMountResetRef.current) return;  // StrictMode 더블 invoke 가드(동일 인스턴스)
    didMountResetRef.current = true;
    if (!agentDocumentLoadConsumed) {
      // 새로고침/첫 진입 — 복원 대화 유지, 아카이브/초기화 건너뜀.
      agentDocumentLoadConsumed = true;
      return;
    }
    const state = useAgentStore.getState();
    if (state.readyToExecute) return;
    const { sessionId: sid, messages: msgs } = state;
    if (msgs.length > 0) {
      const title = msgs.find((m) => m.role === 'user')?.content?.slice(0, 28) ?? '대화';
      state.addSession({
        id: sid || `local-${Date.now()}`, title, createdAt: Date.now(), messages: [...msgs],
        readyToExecute: state.readyToExecute, rationaleText: state.rationaleText,
        currentStep: state.currentStep, compositeFlow: state.compositeFlow,
      });
    }
    state.clearMessages();
    state.clearRationale();
    state.setSessionId('');
    state.setCurrentStep(null);
    state.setCompositeFlow(false);
    state.setSlotQuestion(null);
    state.setViewingSession(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 노드 카탈로그 1회 로드 (편집 캔버스 노드 라벨/리스크 표시용).
  useEffect(() => {
    let cancelled = false;
    getCatalog().then((c) => { if (!cancelled) setEditCatalog(c); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // 워크플로우 완성(readyToExecute) 시 DB에서 로드해 편집 캔버스에 반영.
  // 로딩 실패(404 등)는 곧 workflow_id가 유효 저장본이 아니라는 신호 → 사용자에게 노출.
  useEffect(() => {
    const wfId = readyToExecute?.workflowId;
    if (!wfId) return;
    let cancelled = false;
    getWorkflow(wfId)
      .then((wf) => { if (!cancelled) setLoadedWorkflow(wf); })
      .catch((err) => {
        showToast(`워크플로우 불러오기 실패: ${err instanceof Error ? err.message : '저장본을 찾을 수 없습니다'}`);
      });
    return () => { cancelled = true; };
    // canvasReloadKey: refine이 같은 workflowId로 편집을 반환해도(버전 업데이트) 재로드되게 한다.
  }, [readyToExecute?.workflowId, canvasReloadKey, setLoadedWorkflow]);

  useSSEStream(sessionId, {
    onResult: (frame) => {
      const payload = frame.payload as Record<string, unknown> | undefined;
      if (payload?.status === 'ready_to_execute') {
        setReadyToExecute({
          workflowId: payload.workflow_id as string,
          message: (payload.message as string) ?? '워크플로우가 완성됐습니다. 실행 버튼을 클릭해 실행하세요.',
          explanation: payload.explanation as WorkflowExplanation | undefined,
        });
        // 결과가 올 때마다 캔버스 재로드 강제 — refine의 동일 workflow_id 편집도 반영(버전 업데이트).
        setCanvasReloadKey((k) => k + 1);
      }
    },
  });

  const handleSave = async () => {
    if (!readyToExecute) return;
    setSaveError(null);
    try {
      const result = await validateWorkflow(readyToExecute.workflowId);
      if (result.validation_status === 'passed') {
        showToast('워크플로우가 저장됐습니다.');
        setMode('run');
      } else {
        const errorList = result.errors
          .map((e) => e.hint ?? e.message)
          .filter(Boolean)
          .join(', ');
        setSaveError(
          `워크플로우가 저장되었습니다. 실행하기 위해서는 편집 탭에서 ${errorList || '검증 오류'} 부분 수정이 필요합니다.`,
        );
      }
    } catch {
      setSaveError('워크플로우 검증 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
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
        const next = nextMonotonicStep(prev, toolName);
        // 복합(skill_then_compose) 흐름 — 스킬 빌드 단계 진입 시 '스킬 생성' 선두 단계를 노출.
        // 한 번 켜지면 이후 컴포저 파이프라인 동안에도 유지(단계가 done으로 남도록), 리셋은 새 턴에서만.
        if (next === 'skill') setCompositeFlow(true);
        setCurrentStep(next);
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

    // Bug 6/7: setSessionId('')는 다음 렌더에 반영될 뿐, 현재 클로저의 sessionId는 그대로다.
    // store에서 최신값을 직접 읽어 로컬 변수로 페이로드를 결정한다.
    // — Bug 6: autosend 경로에서 handleNewChat() 직후 호출 시 store는 이미 ''로 갱신됨
    // — Bug 7: readyToExecute 상태에서 sid를 ''로 덮어쓰고 store도 동기 갱신
    const sid = useAgentStore.getState().sessionId;
    if (readyToExecute) {
      // 컨펌(완성) 상태에서 후속 메시지 = **같은 세션 이어가기**(대화형 refine 가능).
      // 이전엔 새 세션으로 리셋해 refine 메시지가 새 채팅으로 떨어져 composer가 이전
      // 워크플로우를 못 불러왔다(같은 session_id라야 draft_store.load_draft 가능). 완전히
      // 새 워크플로우를 시작하려면 "새 대화" 버튼(handleNewChat)을 쓴다.
      //
      // ⚠️ loadedWorkflow(캔버스 본문)는 **지우지 않는다**. refine은 기존 워크플로우 편집이므로
      // 스트리밍 중에도 캔버스에 현재 워크플로우가 보여야 한다. 이전엔 여기서 null로 비워
      // refine이 에러(편집 실패)나면 캔버스가 빈 채로 남아 "워크플로우가 다 날아간 것"처럼 보였다.
      // 편집 성공 시 새 readyToExecute가 와서 loadedWorkflow를 교체(아래 effect, line 574)하므로
      // 지울 필요 없다. ConfirmCard만 숨겨 스트리밍 중 중복 실행 버튼을 막는다.
      setReadyToExecute(null);
      setSaveError(null);  // 카드가 사라지므로 이전 저장 검증 피드백도 함께 해제
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    addMessage({ id: `m${Date.now()}`, role: 'user', content: text, timestamp: Date.now() });
    setInput('');
    setStreaming(true);
    setCurrentStep(null);
    setCompositeFlow(false);  // 새 턴 — 복합 흐름 플래그 리셋 (라운드2 resume은 별도 경로라 미리셋)
    setSkillSelection(null);
    clearRationale();

    try {
      await streamCreateSession(
        { message: text, session_id: sid || undefined },
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
    // round2 resume은 백엔드가 "작성을 시작할게요" 진행 안내를 침묵 처리(composer 노드만 재개)한다.
    // 빈 단계처럼 보이지 않도록 프론트가 이어가기 안내를 즉시 표시한다(composer/resume/bind_skill
    // 프레임이 도착해 스테퍼가 노드 검색→초안 생성으로 전진하기까지의 공백 보완).
    addMessage({
      id: `ack${Date.now()}`,
      role: 'agent',
      content: skillId
        ? '선택하신 스킬을 적용해 워크플로우 작성을 이어갈게요.'
        : '스킬 없이 워크플로우 작성을 이어갈게요.',
      timestamp: Date.now(),
    });
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
      // Bug 6: 대시보드에서 새 워크플로우 요청으로 진입 시 이전 세션 상태를 초기화.
      // 초기화 없이 전송하면 기존 메시지·캔버스가 새 대화에 겹쳐 표시된다.
      handleNewChat();
      autoSentRef.current = true; // handleNewChat이 false로 리셋하므로 재설정
      setInput(q);
      void handleSend(q);
      router.replace('/agent', { scroll: false });
    }
    // handleSend/handleNewChat는 매 렌더 새로 만들어지므로 의도적으로 dep에서 제외
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const stepLabels = displayLabels(compositeFlow);
  const stepIndex = stepIndexFor(currentStep, compositeFlow);
  // 컨펌 게이트 "실행 전 확인할 입력값" — AI가 자동으로 채운 노드 파라미터를 노드 안 들어가도
  // 보이게. loadedWorkflow(저장본)×editCatalog(input_schema)로 프론트 계산(백엔드 변경 0).
  const filledParams = computeFilledParams(loadedWorkflow, editCatalog);
  // 우측 캔버스 노드 칩 — loadedWorkflow.nodes × editCatalog(이름/타입/리스크/아이콘). 백엔드 변경 0.
  const canvasChips: CanvasNodeChip[] = (loadedWorkflow?.nodes ?? []).map((node, i) => {
    const cfg = editCatalog?.find((c) => c.node_id === node.node_id);
    const { icon, color } = resolveNodeIcon(cfg?.node_type, cfg?.category);
    return {
      key: node.instance_id || `chip-${i}`,
      name: cfg?.name ?? node.node_id,
      nodeType: cfg?.node_type ?? node.node_id,
      risk: cfg?.risk_level ?? RiskLevel.LOW,
      icon,
      color,
    };
  });
  // 현재 active 대화를 전체 상태 스냅샷으로 아카이브(복원 가능하게). 내용 없으면 no-op.
  const archiveCurrent = () => {
    const s = useAgentStore.getState();
    if (s.messages.length === 0) return;
    const title = s.messages.find((m) => m.role === 'user')?.content?.slice(0, 28) ?? '대화';
    s.addSession({
      id: s.sessionId || `local-${Date.now()}`, title, createdAt: Date.now(), messages: [...s.messages],
      readyToExecute: s.readyToExecute, rationaleText: s.rationaleText,
      currentStep: s.currentStep, compositeFlow: s.compositeFlow,
    });
  };
  // 이전 대화 클릭 → 현재 보존 후 그 세션을 active로 복원(워크플로우/ConfirmCard/판단근거 포함).
  const handleOpenSession = (s: AgentSession) => {
    if (s.id === sessionId) { setViewingSession(null); return; }
    archiveCurrent();
    restoreSession(s);
    setMode('wizard');
  };
  const handleNewChat = () => {
    // 테스트 3: sessionId가 비어있어도 메시지가 있으면 히스토리에 저장(전체 스냅샷)
    archiveCurrent();
    abortRef.current?.abort();
    clearMessages();
    clearRationale();
    setSessionId('');
    setCurrentStep(null);
    setCompositeFlow(false);
    setSlotQuestion(null);
    setReadyToExecute(null);
    setSkillSelection(null);
    setLoadedWorkflow(null);
    setViewingSession(null);
    setSaveError(null);
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
            <span className="font-bold text-[13px] flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent-coral)]" />
              대화 세션
            </span>
          </div>

          <div className="flex-1 overflow-auto py-2 flex flex-col gap-[2px] px-2">
            {/* 현재 대화 */}
            {sessionId ? (
              <button
                type="button"
                onClick={() => setViewingSession(null)}
                className={[
                  'w-full text-left px-[8px] py-[6px] rounded-lg text-[12px] border-[1.5px] leading-snug',
                  !viewingSession
                    ? 'border-[var(--color-accent)] bg-[var(--color-hl)] text-[var(--color-accent)] font-bold'
                    : 'border-[var(--color-line-soft)] text-[var(--color-ink3)] hover:bg-[var(--color-paper)]',
                ].join(' ')}
              >
                💬 현재 대화
                <div className="font-mono text-[10px] mt-[2px] font-normal break-all opacity-60">
                  {sessionId.slice(0, 8)}…
                </div>
              </button>
            ) : (
              <p className="px-[8px] py-[10px] text-[11px] text-[var(--color-ink4)] italic leading-snug">
                대화를 시작하면<br />세션이 여기 쌓여요.
              </p>
            )}

            {/* 이전 대화 목록 */}
            {sessions.length > 0 && (
              <>
                <div className="px-[8px] pt-3 pb-1 text-[10px] font-bold text-[var(--color-ink4)] uppercase tracking-wider">
                  이전 대화
                </div>
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => handleOpenSession(s)}
                    className={[
                      'w-full text-left px-[8px] py-[6px] rounded-lg text-[12px] border-[1.5px] leading-snug truncate',
                      viewingSession?.id === s.id
                        ? 'border-[var(--color-accent)] bg-[var(--color-hl)] text-[var(--color-accent)] font-bold'
                        : 'border-transparent text-[var(--color-ink3)] hover:bg-[var(--color-paper)] hover:border-[var(--color-line-soft)]',
                    ].join(' ')}
                  >
                    📋 {s.title}{s.title.length >= 28 ? '…' : ''}
                    <div className="text-[10px] mt-[2px] opacity-50 font-normal">
                      {new Date(s.createdAt).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })}
                    </div>
                  </button>
                ))}
              </>
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

          {/* 헤더 — 세션 타이틀(좌) + 모드 pill(우) (디자인 상단 헤더) */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-line-soft)] bg-[var(--color-surface)] flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-[14px] font-bold text-[var(--color-ink)] truncate">{userName}님의 Flowit</span>
              {readyToExecute && (
                <span className="text-[11px] text-[var(--color-ink3)] border border-[var(--color-line-soft)] px-[8px] py-[2px] rounded-lg whitespace-nowrap font-mono flex-shrink-0">
                  {readyToExecute.workflowId.slice(0, 8)}…
                </span>
              )}
            </div>
            <div className="flex-1" />
            <div className="flex items-center gap-1.5">
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
                      'px-3 py-1.5 rounded-full text-xs font-bold transition-all flex items-center gap-1',
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
          </div>

          {/* ── Wizard Mode ─────────────────────────────────────── */}
          {mode === 'wizard' && (
            <div className="flex-1 flex min-h-0">

              {/* Chat area */}
              <div className="flex-1 flex flex-col min-w-0 min-h-0">
                {/* 이전 대화 보기 배너 */}
                {viewingSession && (
                  <div className="flex items-center justify-between px-4 py-2 bg-[var(--color-hl)] border-b border-[var(--color-accent)] flex-shrink-0">
                    <span className="text-[12px] text-[var(--color-accent)] font-bold">
                      📋 이전 대화 보는 중 — {viewingSession.title}
                    </span>
                    <button
                      type="button"
                      onClick={() => setViewingSession(null)}
                      className="text-[11px] text-[var(--color-accent)] underline hover:opacity-70"
                    >
                      현재 대화로 돌아가기
                    </button>
                  </div>
                )}

                {/* Message list — 디자인 3: 720px 가운데, 유저만 말풍선, AI는 본문 텍스트 */}
                <div className="flex-1 overflow-auto">
                  {(viewingSession ? viewingSession.messages : messages).length === 0 && !streaming ? (
                    <div className="h-full flex items-center justify-center text-center px-6">
                      <div className="text-[13px] text-[var(--color-ink4)] leading-relaxed max-w-[420px]">
                        만들고 싶은 워크플로우를 자연어로 설명해주세요.<br />
                        예: <span className="text-[var(--color-ink3)]">&ldquo;매주 월요일 9시에 광고 시트를 읽어서 요약하고 Slack으로 보내줘&rdquo;</span>
                      </div>
                    </div>
                  ) : (
                    <div className="max-w-[720px] mx-auto px-6 py-8 space-y-9">
                      {(viewingSession ? viewingSession.messages : messages).map((msg: ChatMessage) =>
                        msg.role === 'user' ? (
                          <UserBubble key={msg.id}>{msg.content}</UserBubble>
                        ) : (
                          <AiTurn key={msg.id}>
                            <p>{msg.content}</p>
                          </AiTurn>
                        ),
                      )}
                      {streaming && (
                        <AgentWorkProcess
                          labels={stepLabels}
                          currentIndex={stepIndex}
                          rationale={rationaleText}
                        />
                      )}
                      {slotQuestion && !streaming && (
                        <AiTurn>
                          <p>
                            <span className="font-bold text-[var(--color-ink)]">추가 정보가 필요해요</span> — {slotQuestion.question}
                          </p>
                        </AiTurn>
                      )}
                      {readyToExecute && (
                        <>
                          <ConfirmCard
                            message={readyToExecute.message}
                            explanation={readyToExecute.explanation}
                            filledParams={filledParams}
                            onSave={handleSave}
                            onEdit={() => setMode('edit')}
                          />
                          {/* 저장 검증 실패 피드백 — 카드 '아래'에 표시(#368) */}
                          {saveError && (
                            <AiTurn>
                              <p>{saveError}</p>
                            </AiTurn>
                          )}
                        </>
                      )}
                      {skillSelection && !streaming && (
                        <SkillSelectionCard
                          prompt={skillSelection.prompt}
                          options={skillSelection.options}
                          allowSkip={skillSelection.allowSkip}
                          onPick={(id) => void submitSkillSelection(id)}
                          onSkip={() => void submitSkillSelection(null)}
                          disabled={streaming}
                        />
                      )}
                      <div ref={bottomRef} />
                    </div>
                  )}
                </div>

                {/* Input bar — 디자인 5: ChatGPT식 하단 고정, 720px 가운데 */}
                <div className="flex-shrink-0 px-6 pb-5 pt-2">
                  <div className="max-w-[720px] mx-auto">
                    <div className="flex items-end gap-2 bg-white border border-[var(--color-line-soft)] rounded-2xl px-3 py-2 shadow-[0_4px_16px_-10px_rgba(70,58,48,.35)] focus-within:border-[var(--color-accent)] transition-all">
                      <textarea
                        className="flex-1 resize-none bg-transparent text-[14px] font-medium text-[var(--color-ink)] placeholder-[var(--color-ink4)] outline-none py-1.5 disabled:opacity-50"
                        rows={1}
                        placeholder={
                          viewingSession ? '이전 대화 보기 중 — 입력하려면 현재 대화로 돌아가세요'
                          : streaming ? 'AI가 처리 중입니다…'
                          : '이어서 말씀해 주세요… (Shift+Enter 줄바꿈)'
                        }
                        value={input}
                        disabled={streaming || !!viewingSession}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            void handleSend();
                          }
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => void handleSend()}
                        disabled={streaming || !!viewingSession}
                        aria-label="전송"
                        className="w-8 h-8 rounded-lg bg-[var(--color-accent)] hover:bg-[var(--color-accent3)] text-white flex items-center justify-center flex-shrink-0 transition-all disabled:opacity-40 self-end"
                      >
                        <Icon name="arrow-up" className="w-4 h-4" />
                      </button>
                    </div>
                    <p className="text-center text-[10px] text-[var(--color-ink4)] font-bold mt-2">
                      Flowit은 실수할 수 있어요. 권한이 필요한 작업은 항상 확인 후 실행됩니다.
                    </p>
                  </div>
                </div>
              </div>

              {/* 우측 접힘 캔버스 — 워크플로우 결과물(디자인 §4). 작업과정·판단근거는
                  채팅 인라인(AgentWorkProcess)으로 이동, 우측은 결과물 캔버스 전용. */}
              <WorkflowCanvasPanel
                open={canvasOpen}
                onToggle={() => setCanvasOpen((v) => !v)}
                onEdit={() => setMode('edit')}
                onRun={() => setMode('run')}
                chips={canvasChips}
                hasWork={!!loadedWorkflow || !!readyToExecute}
              />
            </div>
          )}

          {/* ── Edit Mode ───────────────────────────────────────── */}
          {/* 완성된 워크플로우(AI 초안)는 WorkflowEditPane으로 — 파라미터 폼(NodeConfigDrawer)
              + 저장(updateWorkflow) + 검증 + 필수누락 시 실행 차단까지 풀 편집. 컨펌 게이트의
              "확인 필요 입력값"을 여기서 바로 고치고 저장·실행. 아니면 빈 빌더(FlowEditor). */}
          {mode === 'edit' && (
            <div className="flex-1 min-h-0 flex">
              {loadedWorkflow ? <WorkflowEditPane onExecuted={() => setMode('run')} /> : <FlowEditor />}
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
