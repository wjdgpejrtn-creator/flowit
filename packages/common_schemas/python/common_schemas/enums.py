from enum import Enum


class AgentMode(str, Enum):
    ONBOARDING = "onboarding"
    WIZARD = "wizard"
    EDIT = "edit"
    GENERAL = "general"
    SECURITY = "security"


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


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
    E_INVALID_TRIGGER = "E_INVALID_TRIGGER"
