import { create } from 'zustand';
import { RiskLevel, ExecutionStatus, NodeExecutionState, WorkflowSchema } from '@common/generated';

export interface WorkflowNode {
  id: string;
  name: string;
  icon: string;
  risk: RiskLevel;
  status?: NodeExecutionState['status'];
  meta?: string;
  position: { x: number; y: number };
}

export interface WorkflowEdge {
  id: string;
  from: string;
  to: string;
  label?: string;
  dashed?: boolean;
}

export interface Workflow {
  id: string;
  name: string;
  scope: WorkflowSchema['scope'];
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  riskLevel: RiskLevel;
  status: `${ExecutionStatus}`;
  nodeCount: number;
  updatedAt: string;
}

interface WorkflowStoreState {
  current: Workflow | null;
  setCurrent: (workflow: Workflow | null) => void;
  updateNode: (nodeId: string, updates: Partial<WorkflowNode>) => void;
}

export const useWorkflowStore = create<WorkflowStoreState>((set) => ({
  current: null,
  setCurrent: (workflow) => set({ current: workflow }),
  updateNode: (nodeId, updates) =>
    set((s) => {
      if (!s.current) return s;
      return {
        current: {
          ...s.current,
          nodes: s.current.nodes.map((n) => (n.id === nodeId ? { ...n, ...updates } : n)),
        },
      };
    }),
}));
