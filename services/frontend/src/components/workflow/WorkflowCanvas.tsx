'use client';

import { useCallback, useMemo, useRef } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
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
import NodePalette, { readPaletteDragPayload } from './NodePalette';
import CustomNode, { type CustomNodeData } from './CustomNode';
import EdgeLine from './EdgeLine';

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

function CanvasInner({ catalog }: { catalog?: NodeConfig[] | null }) {
  const workflow = useWorkflowStore((s) => s.workflow);
  const selectedNodeId = useWorkflowStore((s) => s.selectedNodeId);
  const addNode = useWorkflowStore((s) => s.addNode);
  const updateNodePosition = useWorkflowStore((s) => s.updateNodePosition);
  const removeNode = useWorkflowStore((s) => s.removeNode);
  const addEdge = useWorkflowStore((s) => s.addEdge);
  const removeEdge = useWorkflowStore((s) => s.removeEdge);
  const setSelectedNodeId = useWorkflowStore((s) => s.setSelectedNodeId);

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
    return workflow.connections.map((e) => ({
      id: `${e.from_instance_id}->${e.to_instance_id}`,
      source: e.from_instance_id,
      target: e.to_instance_id,
      sourceHandle: e.from_handle || null,
      targetHandle: e.to_handle || null,
      type: 'custom',
    }));
  }, [workflow]);

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
          const [from, to] = c.id.split('->');
          if (from && to) removeEdge(from, to);
        }
      }
    },
    [removeEdge],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
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
    },
    [setSelectedNodeId],
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const payload = readPaletteDragPayload(e);
      if (!payload) return;
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
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
        position: { x: position.x, y: position.y },
      });
    },
    [addNode, screenToFlowPosition],
  );

  return (
    <div
      ref={wrapperRef}
      className="flex-1 h-full min-h-0 relative"
      style={{ background: 'var(--color-paper2)' }}
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
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onSelectionChange={onSelectionChange}
        deleteKeyCode={['Backspace', 'Delete']}
        fitView
      >
        <Background color="var(--color-line-soft)" />
        <Controls />
        <MiniMap pannable zoomable style={{ background: 'var(--color-surface)' }} />
      </ReactFlow>
      <div
        className="absolute bottom-2 right-2 text-[10px] text-[var(--color-ink3)] bg-[var(--color-surface)] border-[1.5px] border-[var(--color-line-soft)] rounded px-2 py-[2px] pointer-events-none"
        data-testid="canvas-hint"
      >
        삭제: 노드/엣지 선택 후 <kbd className="font-mono">×</kbd> 버튼 또는 <kbd className="font-mono">Delete</kbd>
      </div>
    </div>
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
        {showPalette && <NodePalette catalog={catalog} />}
        <CanvasInner catalog={catalog} />
      </ReactFlowProvider>
    </div>
  );
}
