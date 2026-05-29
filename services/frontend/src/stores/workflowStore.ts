import { create } from 'zustand';
import type {
  WorkflowSchema,
  NodeInstance,
  Edge,
  Position,
  ValidationErrorItem,
} from '@common/generated';

interface WorkflowStoreState {
  workflow: WorkflowSchema | null;
  selectedNodeId: string | null;
  dirty: boolean;
  validationErrors: ValidationErrorItem[];

  setWorkflow: (workflow: WorkflowSchema | null) => void;
  addNode: (node: NodeInstance) => void;
  updateNodeParams: (instanceId: string, parameters: Record<string, unknown>) => void;
  updateNodePosition: (instanceId: string, position: Position) => void;
  removeNode: (instanceId: string) => void;
  addEdge: (edge: Edge) => void;
  removeEdge: (fromInstanceId: string, toInstanceId: string) => void;
  setSelectedNodeId: (id: string | null) => void;
  setValidationErrors: (errors: ValidationErrorItem[]) => void;
  markClean: () => void;
}

export const useWorkflowStore = create<WorkflowStoreState>((set) => ({
  workflow: null,
  selectedNodeId: null,
  dirty: false,
  validationErrors: [],

  setWorkflow: (workflow) =>
    set({ workflow, selectedNodeId: null, dirty: false, validationErrors: [] }),

  addNode: (node) =>
    set((s) => {
      if (!s.workflow) return s;
      return {
        workflow: { ...s.workflow, nodes: [...s.workflow.nodes, node] },
        dirty: true,
      };
    }),

  updateNodeParams: (instanceId, parameters) =>
    set((s) => {
      if (!s.workflow) return s;
      return {
        workflow: {
          ...s.workflow,
          nodes: s.workflow.nodes.map((n) =>
            n.instance_id === instanceId ? { ...n, parameters } : n,
          ),
        },
        dirty: true,
      };
    }),

  updateNodePosition: (instanceId, position) =>
    set((s) => {
      if (!s.workflow) return s;
      return {
        workflow: {
          ...s.workflow,
          nodes: s.workflow.nodes.map((n) =>
            n.instance_id === instanceId ? { ...n, position } : n,
          ),
        },
        dirty: true,
      };
    }),

  removeNode: (instanceId) =>
    set((s) => {
      if (!s.workflow) return s;
      return {
        workflow: {
          ...s.workflow,
          nodes: s.workflow.nodes.filter((n) => n.instance_id !== instanceId),
          connections: s.workflow.connections.filter(
            (e) => e.from_instance_id !== instanceId && e.to_instance_id !== instanceId,
          ),
        },
        selectedNodeId: s.selectedNodeId === instanceId ? null : s.selectedNodeId,
        dirty: true,
      };
    }),

  addEdge: (edge) =>
    set((s) => {
      if (!s.workflow) return s;
      const exists = s.workflow.connections.some(
        (e) =>
          e.from_instance_id === edge.from_instance_id &&
          e.to_instance_id === edge.to_instance_id &&
          e.from_handle === edge.from_handle &&
          e.to_handle === edge.to_handle,
      );
      if (exists) return s;
      return {
        workflow: { ...s.workflow, connections: [...s.workflow.connections, edge] },
        dirty: true,
      };
    }),

  removeEdge: (fromInstanceId, toInstanceId) =>
    set((s) => {
      if (!s.workflow) return s;
      return {
        workflow: {
          ...s.workflow,
          connections: s.workflow.connections.filter(
            (e) =>
              !(e.from_instance_id === fromInstanceId && e.to_instance_id === toInstanceId),
          ),
        },
        dirty: true,
      };
    }),

  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  setValidationErrors: (errors) => set({ validationErrors: errors }),

  markClean: () => set({ dirty: false }),
}));
