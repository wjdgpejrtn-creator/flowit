from __future__ import annotations

from ..entities.node_definition import NodeDefinition
from .control.delay import get_node_definition as _delay
from .control.if_condition import get_node_definition as _if_condition
from .control.loop_count import get_node_definition as _loop_count
from .control.loop_list import get_node_definition as _loop_list
from .control.merge_branch import get_node_definition as _merge_branch
from .control.retry import get_node_definition as _retry
from .control.stop_workflow import get_node_definition as _stop_workflow
from .control.switch_case import get_node_definition as _switch_case
from .data.base64_decode import get_node_definition as _base64_decode
from .data.base64_encode import get_node_definition as _base64_encode
from .data.csv_build import get_node_definition as _csv_build
from .data.csv_parse import get_node_definition as _csv_parse
from .data.date_format import get_node_definition as _date_format
from .data.json_extract import get_node_definition as _json_extract
from .data.json_merge import get_node_definition as _json_merge
from .data.list_filter import get_node_definition as _list_filter
from .data.list_map import get_node_definition as _list_map
from .data.number_calc import get_node_definition as _number_calc
from .data.regex_extract import get_node_definition as _regex_extract
from .data.regex_replace import get_node_definition as _regex_replace
from .data.string_template import get_node_definition as _string_template
from .data.text_transform import get_node_definition as _text_transform
from .trigger.api_poll_trigger import get_node_definition as _api_poll_trigger
from .trigger.event_trigger import get_node_definition as _event_trigger
from .trigger.file_watch_trigger import get_node_definition as _file_watch_trigger
from .trigger.manual_trigger import get_node_definition as _manual_trigger
from .trigger.schedule_trigger import get_node_definition as _schedule_trigger
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
