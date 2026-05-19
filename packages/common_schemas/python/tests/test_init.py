import common_schemas


def test_all_exports():
    assert len(common_schemas.__all__) == 56


def test_key_symbols_importable():
    from common_schemas import (
        AgentMode,
        AgentProtocolRequest,
        AgentProtocolResponse,
        AgentState,
        AnySSEFrame,
        DomainError,
        DraftSpec,
        Edge,
        HandoffPayload,
        IntentResultFrame,
        IntentType,
        LLMResponse,
        MemoryEntry,
        Message,
        NodeConfig,
        PermissionSource,
        PipelineStatusFrame,
        QAMetricFrame,
        ToolCall,
        ValidationErrorResponse,
        WorkflowDraftFrame,
        WorkflowSchema,
    )

    assert AgentMode is not None
    assert AgentProtocolRequest is not None
    assert AgentProtocolResponse is not None
    assert AgentState is not None
    assert AnySSEFrame is not None
    assert DomainError is not None
    assert DraftSpec is not None
    assert Edge is not None
    assert HandoffPayload is not None
    assert IntentResultFrame is not None
    assert IntentType is not None
    assert LLMResponse is not None
    assert MemoryEntry is not None
    assert Message is not None
    assert NodeConfig is not None
    assert PermissionSource is not None
    assert PipelineStatusFrame is not None
    assert QAMetricFrame is not None
    assert ToolCall is not None
    assert ValidationErrorResponse is not None
    assert WorkflowDraftFrame is not None
    assert WorkflowSchema is not None
