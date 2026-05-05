// Auto-generated from Python common_schemas — DO NOT EDIT
// Regenerate: python scripts/generate_ts.py


export enum AgentMode {
  ONBOARDING = "onboarding",
  WIZARD = "wizard",
  EDIT = "edit",
  GENERAL = "general",
  SECURITY = "security",
}

export enum ExecutionStatus {
  RUNNING = "running",
  PAUSED = "paused",
  COMPLETED = "completed",
  FAILED = "failed",
}

export enum RiskLevel {
  LOW = "Low",
  MEDIUM = "Medium",
  HIGH = "High",
  RESTRICTED = "Restricted",
}

export enum ErrorCode {
  E_NODE_TYPE_MISMATCH = "E_NODE_TYPE_MISMATCH",
  E_CYCLE_DETECTED = "E_CYCLE_DETECTED",
  E_ISOLATED_NODE = "E_ISOLATED_NODE",
  E_DUPLICATE_ID = "E_DUPLICATE_ID",
  E_PERMISSION_DENIED = "E_PERMISSION_DENIED",
  E_MISSING_CONNECTION = "E_MISSING_CONNECTION",
  E_INVALID_TRIGGER = "E_INVALID_TRIGGER",
}

export interface Position {
  x: number;
  y: number;
}

export interface Edge {
  from_instance_id: string;
  to_instance_id: string;
  from_handle: string;
  to_handle: string;
}

export interface NodeInstance {
  instance_id: string;
  node_id: string;
  parameters: Record<string, unknown>;
  credential_id?: string | null;
  position: Position;
}

export interface NodeConfig {
  node_id: string;
  node_type: string;
  name: string;
  category: string;
  version: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  parameter_schema: Record<string, unknown>;
  risk_level: "Low" | "Medium" | "High" | "Restricted";
  required_connections: Array<string>;
  description: string;
  is_mvp: boolean;
}

export interface WorkflowSchema {
  workflow_id: string;
  name: string;
  description?: string | null;
  scope: "private" | "team" | "public";
  is_draft: boolean;
  draft_spec?: DraftSpec | null;
  nodes: Array<NodeInstance>;
  connections: Array<Edge>;
  version?: number | null;
  sha256?: string | null;
  created_via_session_id?: string | null;
}

export interface BBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface SheetMeta {
  sheet_name: string;
  row_count: number;
  col_count: number;
}

export interface ParserMeta {
  parser_name: string;
  parser_version: string;
  parse_duration_ms?: number | null;
}

export interface SourceRef {
  page?: number | null;
  section?: string | null;
  block_index?: number | null;
  bbox?: BBox | null;
  sheet_name?: string | null;
  slide_number?: number | null;
}

export interface FileMeta {
  file_name: string;
  file_type: string;
  mime_type: string;
  file_size: number;
  page_count?: number | null;
  unit_type?: string | null;
  created_at?: unknown | null;
  author?: string | null;
  sheet_meta?: Array<SheetMeta> | null;
}

export interface ContentBlock {
  block_id: string;
  block_type: "text" | "table" | "image" | "heading" | "code";
  content?: string | null;
  table?: Array<Array<unknown>> | null;
  page?: number | null;
  section_title?: string | null;
  bbox?: BBox | null;
  source_ref?: SourceRef | null;
  token_estimate?: number | null;
  importance_score?: number | null;
}

export interface DocumentBlock {
  document_id: string;
  workflow_id?: string | null;
  user_id?: string | null;
  file_meta: FileMeta;
  parser?: ParserMeta | null;
  blocks: Array<ContentBlock>;
}

export interface AnalysisResult {
  document_title: string;
  category: string;
  summary: string;
  key_points: Array<string>;
  confidence: number;
  source_refs: Array<Record<string, unknown>>;
  warnings: Array<string>;
  questions: Array<string>;
  prompt_version: string;
  template_type: string;
  few_shot_count: number;
}

export interface UnresolvedNode {
  placeholder_id: string;
  hint: string;
  candidate_node_types: Array<string>;
}

export interface SlotFillingState {
  asked: Array<string>;
  pending: Array<string>;
  filled: Record<string, unknown>;
}

export interface DraftSpec {
  natural_language_intent: string;
  unresolved_nodes: Array<UnresolvedNode>;
  discovered_entities: Record<string, unknown>;
  slot_filling_state: SlotFillingState;
  consultant_turn_count: number;
}

export interface IntentResult {
  intent: "clarify" | "draft" | "refine" | "propose";
  confidence: number;
  analyzed_entities: Record<string, unknown>;
}

export interface AgentState {
  session_id: string;
  user_id: string;
  messages: Array<unknown>;
  turn_count: number;
  mode: "onboarding" | "wizard" | "edit" | "general" | "security";
  draft_spec?: DraftSpec | null;
  intent_result?: IntentResult | null;
  node_candidates?: Array<NodeConfig>;
  workflow_draft?: WorkflowSchema | null;
  execution_status: "running" | "paused" | "completed" | "failed";
}

export interface SSEFrame {
  frame_type: string;
}

export interface SessionFrame {
  frame_type?: "session";
  session_id: string;
  langgraph_thread_id: string;
}

export interface AgentNodeFrame {
  frame_type?: "agent_node";
  agent_node_name: string;
}

export interface RationaleDeltaFrame {
  frame_type?: "rationale_delta";
  delta: string;
}

export interface SlotFillQuestionFrame {
  frame_type?: "slot_fill_question";
  question: string;
  field_name: string;
}

export interface DraftSpecDeltaFrame {
  frame_type?: "draft_spec_delta";
  delta: Record<string, unknown>;
}

export interface ResultFrame {
  frame_type?: "result";
  intent: string;
  payload: Record<string, unknown>;
}

export interface ErrorFrame {
  frame_type?: "error";
  code: string;
  message: string;
}

export interface ValidationErrorItem {
  code: "E_NODE_TYPE_MISMATCH" | "E_CYCLE_DETECTED" | "E_ISOLATED_NODE" | "E_DUPLICATE_ID" | "E_PERMISSION_DENIED" | "E_MISSING_CONNECTION" | "E_INVALID_TRIGGER";
  message: string;
  node_ids: Array<string>;
  edge_id?: string | null;
  validator: "SchemaValidation" | "RuntimeValidation";
  hint?: string | null;
}

export interface ValidationErrorResponse {
  validation_status: "passed" | "failed";
  errors: Array<ValidationErrorItem>;
}

export interface PermissionSource {
  user_id: string;
  role: "User" | "Admin";
  department_id: string;
  session_id: string;
  current_workflow_id?: string | null;
  current_skill_id?: string | null;
  granted_scopes: Array<"Private" | "Team" | "Public">;
  risk_ceiling: "High" | "Restricted";
}

export interface PlaintextCredential {
  credential_id: string;
  credential_kind: "fernet" | "aes_gcm";
  value: string;
}

export interface HandoffPayload {
  handoff_type: "recovery_mode" | "result_review";
  direction: "forward" | "reverse";
  error_codes: Array<string>;
  error_messages: Array<string>;
  state_data: Record<string, unknown>;
  correlation_id: string;
}

export interface EvaluationResult {
  score: number;
  pass_flag: boolean;
  reason: string;
  feedback: string;
}

export type AnySSEFrame = SessionFrame | AgentNodeFrame | RationaleDeltaFrame | SlotFillQuestionFrame | DraftSpecDeltaFrame | ResultFrame | ErrorFrame;
