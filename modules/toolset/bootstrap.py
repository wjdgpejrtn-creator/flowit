"""toolset bootstrap — 14종 기본 tool 일괄 등록.

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
    """14종 기본 tool을 인스턴스화하고 registry에 일괄 등록한다.

    overwrite=True(기본값)이므로 중복 호출해도 안전하다.
    """
    from .adapters.tools.api.graphql_tool import GraphqlTool
    from .adapters.tools.api.http_request_tool import HttpRequestTool
    from .adapters.tools.api.rest_api_tool import RestApiTool
    from .adapters.tools.api.webhook_tool import WebhookTool
    from .adapters.tools.control.conditional_tool import ConditionalTool
    from .adapters.tools.control.loop_tool import LoopTool
    from .adapters.tools.file.file_read_tool import FileReadTool
    from .adapters.tools.file.file_transform_tool import FileTransformTool
    from .adapters.tools.file.file_write_tool import FileWriteTool
    from .adapters.tools.notification.email_send_tool import EmailSendTool
    from .adapters.tools.notification.slack_notify_tool import SlackNotifyTool
    from .adapters.tools.transform.data_mapping_tool import DataMappingTool
    from .adapters.tools.transform.json_transform_tool import JsonTransformTool
    from .adapters.tools.transform.text_template_tool import TextTemplateTool

    tools = [
        GraphqlTool(),
        HttpRequestTool(),
        RestApiTool(),
        WebhookTool(),
        ConditionalTool(),
        LoopTool(),
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
