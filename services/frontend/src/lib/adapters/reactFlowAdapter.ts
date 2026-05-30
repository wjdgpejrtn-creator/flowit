import type { NodeInstance, Edge as SchemaEdge } from '@common/generated';
import type { Node as RFNode, Edge as RFEdge } from '@xyflow/react';

export function toReactFlowNode(instance: NodeInstance): RFNode {
  return {
    id: instance.instance_id,
    position: { x: instance.position.x, y: instance.position.y },
    data: { ...(instance.parameters as Record<string, unknown>), nodeId: instance.node_id },
    type: 'custom',
  };
}

export function toReactFlowEdge(edge: SchemaEdge): RFEdge {
  return {
    id: `${edge.from_instance_id}-${edge.to_instance_id}`,
    source: edge.from_instance_id,
    target: edge.to_instance_id,
    // 핸들 id 가 없는 옛/AI 엣지는 기본 좌→우(source=right/target=left)로 폴백.
    sourceHandle: edge.from_handle || 'right',
    targetHandle: edge.to_handle || 'left',
  };
}

export function fromReactFlowNode(rfNode: RFNode): Partial<NodeInstance> {
  return {
    instance_id: rfNode.id,
    position: { x: rfNode.position.x, y: rfNode.position.y },
  };
}
