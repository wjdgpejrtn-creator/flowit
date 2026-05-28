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
