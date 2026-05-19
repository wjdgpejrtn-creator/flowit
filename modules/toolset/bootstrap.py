"""toolset bootstrap — 11종 기본 tool 일괄 등록.

각 Modal app의 boot lifecycle에서 호출:
    registry = ToolRegistryAdapter()
    register_default_tools(registry)
"""
from __future__ import annotations

from uuid import NAMESPACE_DNS, UUID, uuid5

from .adapters.tool_registry_adapter import ToolRegistryAdapter


def _tid(name: str) -> UUID:
    return uuid5(NAMESPACE_DNS, f"toolset.{name}")


def register_default_tools(registry: ToolRegistryAdapter) -> None:
    """11종 기본 tool을 인스턴스화하고 registry에 일괄 등록한다.

    overwrite=True(기본값)이므로 중복 호출해도 안전하다.
    """
    from .adapters.internal.api.graphql_tool import GraphqlTool
    from .adapters.internal.api.rest_api_tool import RestApiTool
    from .adapters.internal.api.webhook_tool import WebhookTool
    from .adapters.internal.file.file_read_tool import FileReadTool
    from .adapters.internal.file.file_transform_tool import FileTransformTool
    from .adapters.internal.file.file_write_tool import FileWriteTool
    from .adapters.internal.notification.email_send_tool import EmailSendTool
    from .adapters.internal.notification.slack_notify_tool import SlackNotifyTool
    from .adapters.internal.transform.data_mapping_tool import DataMappingTool
    from .adapters.internal.transform.json_transform_tool import JsonTransformTool
    from .adapters.internal.transform.text_template_tool import TextTemplateTool

    tools = [
        GraphqlTool(),
        RestApiTool(),
        WebhookTool(),
        FileReadTool(),
        FileTransformTool(),
        FileWriteTool(),
        EmailSendTool(),
        SlackNotifyTool(),
        DataMappingTool(),
        JsonTransformTool(),
        TextTemplateTool(),
    ]
    registry.register_bulk([(t, _tid(t.name)) for t in tools])
