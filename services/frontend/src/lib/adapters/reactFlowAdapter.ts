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
    sourceHandle: edge.from_handle ?? null,
    targetHandle: edge.to_handle ?? null,
  };
}

export function fromReactFlowNode(rfNode: RFNode): Partial<NodeInstance> {
  return {
    instance_id: rfNode.id,
    position: { x: rfNode.position.x, y: rfNode.position.y },
  };
}
