'use client';

import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  type Node as RFNode,
  type Edge as RFEdge,
  type Connection,
  type OnConnect,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import CustomNode from './CustomNode';
import EdgeLine from './EdgeLine';
import type { NodeInstance, Edge as SchemaEdge } from '@common/generated';

const NODE_TYPES = { custom: CustomNode };
const EDGE_TYPES = { custom: EdgeLine };

interface Props {
  nodes: NodeInstance[];
  connections: SchemaEdge[];
  readonly?: boolean;
  onNodeClick?: (node: NodeInstance) => void;
  onNodesChange?: (nodes: NodeInstance[]) => void;
  nodeStatusMap?: Map<string, string>;
}

function toRFNode(n: NodeInstance, statusMap?: Map<string, string>): RFNode {
  return {
    id: n.instance_id,
    type: 'custom',
    position: { x: n.position.x, y: n.position.y },
    data: {
      label: n.node_id,
      status: statusMap?.get(n.instance_id),
      ...n.parameters,
    },
  };
}

function toRFEdge(e: SchemaEdge, i: number): RFEdge {
  return {
    id: `e${i}-${e.from_instance_id}-${e.to_instance_id}`,
    type: 'custom',
    source: e.from_instance_id,
    target: e.to_instance_id,
    sourceHandle: e.from_handle || undefined,
    targetHandle: e.to_handle || undefined,
  };
}

export default function WorkflowCanvas({
  nodes: schemaNodes,
  connections,
  readonly = false,
  onNodeClick,
  nodeStatusMap,
}: Props) {
  const initialNodes = useMemo(
    () => schemaNodes.map((n) => toRFNode(n, nodeStatusMap)),
    [schemaNodes, nodeStatusMap],
  );
  const initialEdges = useMemo(
    () => connections.map((e, i) => toRFEdge(e, i)),
    [connections],
  );

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect: OnConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={readonly ? undefined : onNodesChange}
      onEdgesChange={readonly ? undefined : onEdgesChange}
      onConnect={readonly ? undefined : onConnect}
      onNodeClick={(_, node) => {
        const schema = schemaNodes.find((n) => n.instance_id === node.id);
        if (schema) onNodeClick?.(schema);
      }}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      fitView
      nodesDraggable={!readonly}
      nodesConnectable={!readonly}
      elementsSelectable={!readonly}
      style={{ background: 'var(--color-paper2)' }}
    >
      <Background color="var(--color-line-soft)" />
      <Controls />
      <MiniMap
        nodeColor={() => 'var(--color-ink3)'}
        style={{ background: 'var(--color-paper2)', border: '1.5px solid var(--color-ink)' }}
      />
    </ReactFlow>
  );
}
