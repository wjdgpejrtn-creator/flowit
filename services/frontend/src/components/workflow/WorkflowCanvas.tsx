'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ConnectionMode,
  useReactFlow,
  type Node as RFNode,
  type Edge as RFEdge,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type OnSelectionChangeParams,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import type { NodeConfig } from '@common/generated';
import { useWorkflowStore } from '@/stores/workflowStore';
import { showToast } from '@/stores/toastStore';
import NodePalette, { readPaletteDragPayload, type NodePaletteDragPayload } from './NodePalette';
import Icon from '@/components/common/Icon';
import CustomNode, { type CustomNodeData } from './CustomNode';
import EdgeLine from './EdgeLine';
import { buildEdgeId, resolveSourceHandle, resolveTargetHandle } from '@/lib/adapters/reactFlowAdapter';

const nodeTypes = { custom: CustomNode };
const edgeTypes = { custom: EdgeLine };

const defaultEdgeOptions = { type: 'custom' };

function makeInstanceId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // jsdom/test fallback
  return `tmp-${Math.random().toString(36).slice(2, 10)}`;
}

function CanvasInner({ catalog, showPalette = true }: { catalog?: NodeConfig[] | null; showPalette?: boolean }) {
  const workflow = useWorkflowStore((s) => s.workflow);
  const selectedNodeId = useWorkflowStore((s) => s.selectedNodeId);
  const addNode = useWorkflowStore((s) => s.addNode);
  const updateNodePosition = useWorkflowStore((s) => s.updateNodePosition);
  const removeNode = useWorkflowStore((s) => s.removeNode);
  const addEdge = useWorkflowStore((s) => s.addEdge);
  const removeEdge = useWorkflowStore((s) => s.removeEdge);
  const setSelectedNodeId = useWorkflowStore((s) => s.setSelectedNodeId);
  // 엣지 선택은 store가 아닌 로컬 — rfEdges가 workflow에서 파생되는 컨트롤드 구조라
  // selected를 명시 주입하지 않으면 React Flow 선택이 매 렌더 유실돼 EdgeLine ×버튼·
  // Delete가 동작하지 않는다(노드 selectedNodeId와 동일 패턴).
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const { screenToFlowPosition } = useReactFlow();

  const rfNodes: RFNode[] = useMemo(() => {
    if (!workflow) return [];
    return workflow.nodes.map((n) => {
      const meta = (n.parameters as { __palette?: CustomNodeData })?.__palette;
      const cfg = catalog?.find((c) => c.node_id === n.node_id);
      const data: CustomNodeData = {
        name: meta?.name ?? cfg?.name ?? n.node_id.slice(0, 8),
        node_type: meta?.node_type ?? cfg?.node_type ?? n.node_id,
        risk_level: meta?.risk_level ?? cfg?.risk_level ?? ('low' as CustomNodeData['risk_level']),
        category: cfg?.category,
      };
      return {
        id: n.instance_id,
        position: { x: n.position.x, y: n.position.y },
        type: 'custom',
        data: data as unknown as Record<string, unknown>,
        selected: n.instance_id === selectedNodeId,
      };
    });
  }, [workflow, selectedNodeId, catalog]);

  const rfEdges: RFEdge[] = useMemo(() => {
    if (!workflow) return [];
    return workflow.connections.map((e) => {
      const id = buildEdgeId(e);
      return {
        id,
        source: e.from_instance_id,
        target: e.to_instance_id,
        // 레거시/AI 엣지의 from_handle="output"·to_handle="input" 을 4방향 핸들 id 로 매핑.
        // 빈 값/미지 값은 기존 좌→우 레이아웃으로 폴백 (reactFlowAdapter 단일 소스).
        sourceHandle: resolveSourceHandle(e.from_handle),
        targetHandle: resolveTargetHandle(e.to_handle),
        type: 'custom',
        selected: id === selectedEdgeId,
      };
    });
  }, [workflow, selectedEdgeId]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const c of changes) {
        if (c.type === 'position' && c.position && !c.dragging) {
          updateNodePosition(c.id, { x: c.position.x, y: c.position.y });
        } else if (c.type === 'remove') {
          removeNode(c.id);
        } else if (c.type === 'select') {
          // selection handled by onSelectionChange
        }
      }
    },
    [updateNodePosition, removeNode],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const c of changes) {
        if (c.type === 'remove') {
          removeEdge(c.id);
        }
      }
    },
    [removeEdge],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      // Loose 모드에서 자기 자신 연결(self-loop) 방지
      if (connection.source === connection.target) return;
      addEdge({
        from_instance_id: connection.source,
        to_instance_id: connection.target,
        from_handle: connection.sourceHandle ?? '',
        to_handle: connection.targetHandle ?? '',
      });
    },
    [addEdge],
  );

  const onSelectionChange = useCallback(
    (params: OnSelectionChangeParams) => {
      const first = params.nodes[0];
      setSelectedNodeId(first?.id ?? null);
      setSelectedEdgeId(params.edges[0]?.id ?? null);
    },
    [setSelectedNodeId, setSelectedEdgeId],
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  // 노드 추가 공통 — 드롭/클릭 양쪽에서 사용. 추가 토스트 포함(시안 addCustomNode).
  const addPaletteNode = useCallback(
    (payload: NodePaletteDragPayload, position: { x: number; y: number }) => {
      addNode({
        instance_id: makeInstanceId(),
        node_id: payload.node_id,
        parameters: {
          __palette: {
            name: payload.name,
            node_type: payload.node_type,
            risk_level: payload.risk_level,
          },
        },
        credential_id: null,
        credential_ids: {},
        position: { x: position.x, y: position.y },
      });
      showToast(`'${payload.name}' 노드를 추가했습니다.`);
    },
    [addNode],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const payload = readPaletteDragPayload(e);
      if (!payload) return;
      addPaletteNode(payload, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
    },
    [addPaletteNode, screenToFlowPosition],
  );

  // 시안 addCustomNode: 팔레트 클릭으로도 캔버스 중앙(약간 스태거)에 추가
  const onPalettePick = useCallback(
    (node: NodeConfig) => {
      const wrap = wrapperRef.current;
      let position = { x: 120, y: 90 };
      if (wrap) {
        const r = wrap.getBoundingClientRect();
        position = screenToFlowPosition({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
      }
      const n = workflow?.nodes.length ?? 0;
      addPaletteNode(
        { node_id: node.node_id, node_type: node.node_type, name: node.name, risk_level: node.risk_level },
        { x: position.x + ((n * 28) % 140) - 70, y: position.y + ((n * 28) % 140) - 70 },
      );
    },
    [addPaletteNode, screenToFlowPosition, workflow?.nodes.length],
  );

  // 시안 휴지통 존 — 노드 드래그 중 하단에 나타나고, 위에서 드롭하면 삭제
  const [draggingNode, setDraggingNode] = useState(false);
  const [trashHover, setTrashHover] = useState(false);
  const trashRef = useRef<HTMLDivElement | null>(null);
  const isOverTrash = (clientX: number, clientY: number) => {
    const r = trashRef.current?.getBoundingClientRect();
    return !!r && clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom;
  };
  const onNodeDragStart = useCallback(() => setDraggingNode(true), []);
  const onNodeDrag = useCallback(
    (e: React.MouseEvent) => setTrashHover(isOverTrash(e.clientX, e.clientY)),
    [],
  );
  const onNodeDragStop = useCallback(
    (e: React.MouseEvent, node: RFNode) => {
      if (isOverTrash(e.clientX, e.clientY)) {
        removeNode(node.id);
        showToast('노드를 제거했습니다.');
      }
      setDraggingNode(false);
      setTrashHover(false);
    },
    [removeNode],
  );

  return (
    <>
      {showPalette && <NodePalette catalog={catalog} onPick={onPalettePick} />}
      <div
        ref={wrapperRef}
        className="flex-1 h-full min-h-0 relative"
        style={{ background: 'var(--color-surface)' }}
        onDragOver={onDragOver}
        onDrop={onDrop}
        data-testid="workflow-canvas-drop-target"
      >
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          connectionMode={ConnectionMode.Loose}
          connectionLineStyle={{
            stroke: 'var(--color-accent-coral)',
            strokeWidth: 2,
            strokeDasharray: '6 4',
            opacity: 0.85,
          }}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onSelectionChange={onSelectionChange}
          onNodeDragStart={onNodeDragStart}
          onNodeDrag={onNodeDrag}
          onNodeDragStop={onNodeDragStop}
          deleteKeyCode={['Backspace', 'Delete']}
          fitView
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1.3} color="#D8CBB8" />
          <Controls />
          <MiniMap pannable zoomable style={{ background: 'var(--color-surface)' }} />
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
      <div
        className="absolute bottom-2 right-2 text-[10px] text-[var(--color-ink3)] bg-[var(--color-surface)] border-[1.5px] border-[var(--color-line-soft)] rounded px-2 py-[2px] pointer-events-none"
        data-testid="canvas-hint"
      >
        삭제: 노드/엣지 선택 후 <kbd className="font-mono">×</kbd> 버튼 또는 <kbd className="font-mono">Delete</kbd>
        </div>
      </div>
    </>
  );
}

export default function WorkflowCanvas({
  showPalette = true,
  catalog,
}: {
  showPalette?: boolean;
  catalog?: NodeConfig[] | null;
}) {
  return (
    <div className="flex flex-1 min-h-0">
      <ReactFlowProvider>
        <CanvasInner catalog={catalog} showPalette={showPalette} />
      </ReactFlowProvider>
    </div>
  );
}
