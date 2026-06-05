import type { NodeInstance, Edge as SchemaEdge } from '@common/generated';
import type { Node as RFNode, Edge as RFEdge } from '@xyflow/react';

// CustomNode 가 렌더하는 4방향 핸들 id (ConnectionMode.Loose 라 방향 무관 양방향 연결).
const CANVAS_HANDLE_IDS = new Set(['left', 'right', 'top', 'bottom']);
const SOURCE_HANDLE_DEFAULT = 'right';
const TARGET_HANDLE_DEFAULT = 'left';

// AI 드래프터/레거시 엣지는 from_handle="output" / to_handle="input" 을 emit 한다
// (ai_agent/domain/services/drafter_service.py — Edge SSOT). 두 값 모두 truthy 라
// `|| 'right'` 단순 폴백으로는 안 걸려 sourceHandle="output" 으로 새고, 4방향 핸들 도입
// 후엔 매칭 핸들이 없어 React Flow 가 엣지를 안 그린다. 레거시 값을 캔버스 핸들 id 로
// 명시 매핑하고, 알 수 없는 값/빈 값은 기존 좌→우 레이아웃으로 폴백한다.
export function resolveSourceHandle(handle?: string | null): string {
  if (!handle || handle === 'output') return SOURCE_HANDLE_DEFAULT;
  return CANVAS_HANDLE_IDS.has(handle) ? handle : SOURCE_HANDLE_DEFAULT;
}

export function resolveTargetHandle(handle?: string | null): string {
  if (!handle || handle === 'input') return TARGET_HANDLE_DEFAULT;
  return CANVAS_HANDLE_IDS.has(handle) ? handle : TARGET_HANDLE_DEFAULT;
}

export function toReactFlowNode(instance: NodeInstance): RFNode {
  return {
    id: instance.instance_id,
    position: { x: instance.position.x, y: instance.position.y },
    data: { ...(instance.parameters as Record<string, unknown>), nodeId: instance.node_id },
    type: 'custom',
  };
}

// 엣지 단일 식별자. 같은 노드쌍에 핸들만 다른 병렬 엣지가 공존할 수 있어(addEdge 가
// 핸들까지 비교해 dedupe) 노드쌍만으론 선택·삭제 대상이 모호해진다 → 핸들까지 포함한다.
// React Flow id ↔ 스키마 엣지 매칭의 단일 소스(스토어 removeEdge·캔버스 rfEdges 공용).
export function buildEdgeId(
  edge: Pick<SchemaEdge, 'from_instance_id' | 'to_instance_id' | 'from_handle' | 'to_handle'>,
): string {
  return `${edge.from_instance_id}|${edge.from_handle ?? ''}->${edge.to_instance_id}|${edge.to_handle ?? ''}`;
}

export function toReactFlowEdge(edge: SchemaEdge): RFEdge {
  return {
    id: buildEdgeId(edge),
    source: edge.from_instance_id,
    target: edge.to_instance_id,
    sourceHandle: resolveSourceHandle(edge.from_handle),
    targetHandle: resolveTargetHandle(edge.to_handle),
  };
}

export function fromReactFlowNode(rfNode: RFNode): Partial<NodeInstance> {
  return {
    instance_id: rfNode.id,
    position: { x: rfNode.position.x, y: rfNode.position.y },
  };
}
