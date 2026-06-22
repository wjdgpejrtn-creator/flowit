from enum import Enum


class AgentMode(str, Enum):
    ONBOARDING = "onboarding"
    WIZARD = "wizard"
    EDIT = "edit"
    GENERAL = "general"
    SECURITY = "security"
    SKILL_BUILDER = "skill_builder"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    RESTRICTED = "Restricted"


class ErrorCode(str, Enum):
    E_NODE_TYPE_MISMATCH = "E_NODE_TYPE_MISMATCH"
    E_CYCLE_DETECTED = "E_CYCLE_DETECTED"
    E_ISOLATED_NODE = "E_ISOLATED_NODE"
    E_DUPLICATE_ID = "E_DUPLICATE_ID"
    E_PERMISSION_DENIED = "E_PERMISSION_DENIED"
    E_MISSING_CONNECTION = "E_MISSING_CONNECTION"
    E_MISSING_REQUIRED_PARAMETER = "E_MISSING_REQUIRED_PARAMETER"
    E_INVALID_TRIGGER = "E_INVALID_TRIGGER"
    # 워크플로우 노드가 카탈로그에 실재하지 않는(=실행 불가) node_type/node_id를 참조 —
    # GraphValidator가 검증 시점에 거부해, LLM이 임시 생성한 비실재 노드가 QA를 통과한 뒤
    # 실행 단계에서 executor 없어 실패하는 것을 차단한다 (ADR-0026 §6.6 검증 게이트).
    E_UNKNOWN_NODE_TYPE = "E_UNKNOWN_NODE_TYPE"


class AnalysisStatus(str, Enum):
    """문서 분석 비동기 태스크 상태 — Celery worker가 갱신, api_server가 노출."""
    PENDING = "pending"      # 업로드 직후 — analyze 미요청
    RUNNING = "running"      # Celery 태스크 시작
    COMPLETED = "completed"  # blocks 저장 완료
    FAILED = "failed"        # 파싱 실패 — analysis_error 참조


class IntentType(str, Enum):
    CLARIFY = "clarify"
    DRAFT = "draft"
    REFINE = "refine"
    PROPOSE = "propose"
    BUILD_SKILL = "build_skill"
    # fast-path intents — composer 호출 없이 즉시 처리
    CHITCHAT = "chitchat"
    INFO_QUESTION = "info_question"
    CONTROL = "control"
    WORKFLOW_EXECUTE = "workflow_execute"
