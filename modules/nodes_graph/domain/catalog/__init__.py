from __future__ import annotations

from ..entities.base_node import BaseNode
from ..entities.node_definition import NodeDefinition
from .control.delay import DelayNode
from .control.delay import get_node_definition as _delay
from .control.if_condition import IfConditionNode
from .control.if_condition import get_node_definition as _if_condition
from .control.loop_count import LoopCountNode
from .control.loop_count import get_node_definition as _loop_count
from .control.loop_list import LoopListNode
from .control.loop_list import get_node_definition as _loop_list
from .control.merge_branch import MergeBranchNode
from .control.merge_branch import get_node_definition as _merge_branch
from .control.retry import RetryNode
from .control.retry import get_node_definition as _retry
from .control.stop_workflow import StopWorkflowNode
from .control.stop_workflow import get_node_definition as _stop_workflow
from .control.switch_case import SwitchCaseNode
from .control.switch_case import get_node_definition as _switch_case
from .data.base64_decode import Base64DecodeNode
from .data.base64_decode import get_node_definition as _base64_decode
from .data.base64_encode import Base64EncodeNode
from .data.base64_encode import get_node_definition as _base64_encode
from .data.csv_build import CsvBuildNode
from .data.csv_build import get_node_definition as _csv_build
from .data.csv_parse import CsvParseNode
from .data.csv_parse import get_node_definition as _csv_parse
from .data.date_format import DateFormatNode
from .data.date_format import get_node_definition as _date_format
from .data.json_extract import JsonExtractNode
from .data.json_extract import get_node_definition as _json_extract
from .data.json_merge import JsonMergeNode
from .data.json_merge import get_node_definition as _json_merge
from .data.list_filter import ListFilterNode
from .data.list_filter import get_node_definition as _list_filter
from .data.list_map import ListMapNode
from .data.list_map import get_node_definition as _list_map
from .data.number_calc import NumberCalcNode
from .data.number_calc import get_node_definition as _number_calc
from .data.regex_extract import RegexExtractNode
from .data.regex_extract import get_node_definition as _regex_extract
from .data.regex_replace import RegexReplaceNode
from .data.regex_replace import get_node_definition as _regex_replace
from .data.string_template import StringTemplateNode
from .data.string_template import get_node_definition as _string_template
from .data.text_transform import TextTransformNode
from .data.text_transform import get_node_definition as _text_transform
from .trigger.api_poll_trigger import ApiPollTriggerNode
from .trigger.api_poll_trigger import get_node_definition as _api_poll_trigger
from .trigger.event_trigger import EventTriggerNode
from .trigger.event_trigger import get_node_definition as _event_trigger
from .trigger.file_watch_trigger import FileWatchTriggerNode
from .trigger.file_watch_trigger import get_node_definition as _file_watch_trigger
from .trigger.manual_trigger import ManualTriggerNode
from .trigger.manual_trigger import get_node_definition as _manual_trigger
from .trigger.schedule_trigger import ScheduleTriggerNode
from .trigger.schedule_trigger import get_node_definition as _schedule_trigger
from .trigger.webhook_trigger import WebhookTriggerNode
from .trigger.webhook_trigger import get_node_definition as _webhook_trigger


def get_domain_node_definitions() -> list[NodeDefinition]:
    """도메인 28종 NodeDefinition (external 2종 제외). application/catalog_registry에서 조합."""
    return [
        # 데이터 처리 (14)
        _text_transform(),
        _json_extract(),
        _json_merge(),
        _csv_parse(),
        _csv_build(),
        _number_calc(),
        _date_format(),
        _list_filter(),
        _list_map(),
        _string_template(),
        _regex_extract(),
        _regex_replace(),
        _base64_encode(),
        _base64_decode(),
        # 조건/제어 (8)
        _if_condition(),
        _switch_case(),
        _loop_list(),
        _loop_count(),
        _delay(),
        _retry(),
        _merge_branch(),
        _stop_workflow(),
        # 트리거 (6)
        _schedule_trigger(),
        _webhook_trigger(),
        _manual_trigger(),
        _file_watch_trigger(),
        _event_trigger(),
        _api_poll_trigger(),
    ]


def get_domain_node_classes() -> dict[str, type[BaseNode]]:
    """도메인 28종 node_type → BaseNode 클래스 (ADR-0018 CatalogNodeExecutor 조회용)."""
    return {
        # 데이터 처리 (14)
        "text_transform": TextTransformNode,
        "json_extract": JsonExtractNode,
        "json_merge": JsonMergeNode,
        "csv_parse": CsvParseNode,
        "csv_build": CsvBuildNode,
        "number_calc": NumberCalcNode,
        "date_format": DateFormatNode,
        "list_filter": ListFilterNode,
        "list_map": ListMapNode,
        "string_template": StringTemplateNode,
        "regex_extract": RegexExtractNode,
        "regex_replace": RegexReplaceNode,
        "base64_encode": Base64EncodeNode,
        "base64_decode": Base64DecodeNode,
        # 조건/제어 (8)
        "if_condition": IfConditionNode,
        "switch_case": SwitchCaseNode,
        "loop_list": LoopListNode,
        "loop_count": LoopCountNode,
        "delay": DelayNode,
        "retry": RetryNode,
        "merge_branch": MergeBranchNode,
        "stop_workflow": StopWorkflowNode,
        # 트리거 (6)
        "schedule_trigger": ScheduleTriggerNode,
        "webhook_trigger": WebhookTriggerNode,
        "manual_trigger": ManualTriggerNode,
        "file_watch_trigger": FileWatchTriggerNode,
        "event_trigger": EventTriggerNode,
        "api_poll_trigger": ApiPollTriggerNode,
    }
