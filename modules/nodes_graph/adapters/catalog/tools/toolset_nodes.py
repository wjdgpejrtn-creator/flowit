from __future__ import annotations

from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.node_definition import NodeDefinition


def get_node_definitions() -> list[NodeDefinition]:
    """REQ-005 toolset 14종 NodeDefinition.

    delay는 domain/catalog/control/delay.py와 node_type 충돌 — 제외 (nodes_graph 것 사용).
    http_request는 http_request_tool로 이름 변경하여 포함.
    """
    return [
        _http_request_tool(),
        _rest_api(),
        _graphql(),
        _webhook(),
        _file_read(),
        _file_write(),
        _file_transform(),
        _json_transform(),
        _text_template(),
        _data_mapping(),
        _conditional(),
        _loop(),
        _slack_notify(),
        _email_send(),
    ]


def _http_request_tool() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "http_request_tool"),
        node_type="http_request_tool",
        name="HTTP 요청 (인증)",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
                "headers": {"type": "object"},
                "body": {"type": "object"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
            },
            "required": ["url"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "body": {},
                "headers": {"type": "object"},
                "ok": {"type": "boolean"},
            },
            "required": ["status_code", "body", "headers", "ok"],
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=[],
        description="외부 HTTP API 호출. credential 주입 시 Bearer 인증 헤더 자동 추가",
        is_mvp=True,
        service_type=None,
    )


def _rest_api() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "rest_api"),
        node_type="rest_api",
        name="REST API",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "base_url": {"type": "string"},
                "path": {"type": "string", "default": ""},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
                "query_params": {"type": "object"},
                "headers": {"type": "object"},
                "body": {"type": "object"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
            },
            "required": ["base_url"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "data": {},
                "ok": {"type": "boolean"},
            },
            "required": ["status_code", "data", "ok"],
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=[],
        description="REST API 호출 및 JSON 응답 파싱. base_url + path 조합, credential 선택적 지원",
        is_mvp=True,
        service_type=None,
    )


def _graphql() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "graphql"),
        node_type="graphql",
        name="GraphQL",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "endpoint": {"type": "string"},
                "query": {"type": "string"},
                "variables": {"type": "object"},
                "headers": {"type": "object"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
            },
            "required": ["endpoint", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "data": {},
                "errors": {"type": "array"},
                "ok": {"type": "boolean"},
            },
            "required": ["data", "ok"],
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=[],
        description="GraphQL 쿼리/뮤테이션 실행",
        is_mvp=True,
        service_type=None,
    )


def _webhook() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "webhook"),
        node_type="webhook",
        name="웹훅 발송",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "payload": {"type": "object"},
                "headers": {"type": "object"},
                "secret": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60, "default": 10},
            },
            "required": ["url", "payload"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "delivered": {"type": "boolean"},
            },
            "required": ["status_code", "delivered"],
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=[],
        description="웹훅 발송 (fire-and-forget). secret 제공 시 HMAC-SHA256 서명 헤더 자동 추가",
        is_mvp=True,
        service_type=None,
    )


def _file_read() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "file_read"),
        node_type="file_read",
        name="파일 읽기",
        category="utility",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "encoding": {"type": "string", "default": "utf-8"},
                "binary": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {},
                "size_bytes": {"type": "integer"},
                "path": {"type": "string"},
            },
            "required": ["content", "size_bytes", "path"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="파일 텍스트/바이너리 읽기. binary=true 시 hex 문자열 반환",
        is_mvp=True,
        service_type=None,
    )


def _file_write() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "file_write"),
        node_type="file_write",
        name="파일 쓰기",
        category="utility",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "encoding": {"type": "string", "default": "utf-8"},
                "mode": {"type": "string", "enum": ["w", "a"], "default": "w"},
                "create_parents": {"type": "boolean", "default": False},
            },
            "required": ["path", "content"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "bytes_written": {"type": "integer"},
                "success": {"type": "boolean"},
            },
            "required": ["path", "bytes_written", "success"],
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=[],
        description="파일 쓰기/추가. mode=a 시 기존 파일에 append. create_parents=true 시 중간 디렉토리 생성",
        is_mvp=True,
        service_type=None,
    )


def _file_transform() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "file_transform"),
        node_type="file_transform",
        name="파일 형식 변환",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "source_path": {"type": "string"},
                "target_path": {"type": "string"},
                "source_format": {"type": "string", "enum": ["csv", "json"]},
                "target_format": {"type": "string", "enum": ["csv", "json"]},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["source_path", "target_path", "source_format", "target_format"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "target_path": {"type": "string"},
                "rows_processed": {"type": "integer"},
            },
            "required": ["target_path", "rows_processed"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="CSV ↔ JSON 파일 형식 변환",
        is_mvp=True,
        service_type=None,
    )


def _json_transform() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "json_transform"),
        node_type="json_transform",
        name="JSON 변환 (JMESPath)",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "expression": {"type": "string"},
            },
            "required": ["data", "expression"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {},
                "matched": {"type": "boolean"},
            },
            "required": ["result", "matched"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="JMESPath 표현식으로 JSON 데이터 추출/변환. wildcard([*]), filter([?field]) 지원",
        is_mvp=True,
        service_type=None,
    )


def _text_template() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "text_template"),
        node_type="text_template",
        name="텍스트 템플릿",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "template": {"type": "string"},
                "variables": {"type": "object"},
            },
            "required": ["template", "variables"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "rendered": {"type": "string"},
            },
            "required": ["rendered"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="Python str.format_map() 기반 텍스트 템플릿 렌더링. {variable} 문법 사용",
        is_mvp=True,
        service_type=None,
    )


def _data_mapping() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "data_mapping"),
        node_type="data_mapping",
        name="데이터 매핑",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "mapping": {"type": "object"},
                "drop_unmapped": {"type": "boolean", "default": False},
            },
            "required": ["data", "mapping"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "object"},
                "mapped_count": {"type": "integer"},
            },
            "required": ["result", "mapped_count"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="필드명 리매핑. drop_unmapped=true 시 매핑 미정의 필드 제거",
        is_mvp=True,
        service_type=None,
    )


def _conditional() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "conditional"),
        node_type="conditional",
        name="조건 분기",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "left": {},
                "operator": {
                    "type": "string",
                    "enum": ["eq", "ne", "gt", "lt", "gte", "lte", "contains", "startswith", "endswith", "in"],
                },
                "right": {},
            },
            "required": ["left", "operator", "right"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "boolean"},
                "branch": {"type": "string", "enum": ["true_branch", "false_branch"]},
            },
            "required": ["result", "branch"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="if/else 조건 분기. 10종 연산자(eq/ne/gt/lt/gte/lte/contains/startswith/endswith/in) 지원",
        is_mvp=True,
        service_type=None,
    )


def _loop() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "loop"),
        node_type="loop",
        name="리스트 순회",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "max_iterations": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            },
            "required": ["items"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "count": {"type": "integer"},
            },
            "required": ["results", "count"],
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=[],
        description="리스트 순회. 각 요소를 {index, item} 형태로 반환. max_iterations 초과 시 잘라냄",
        is_mvp=True,
        service_type=None,
    )


def _slack_notify() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "slack_notify"),
        node_type="slack_notify",
        name="Slack 알림",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "channel": {"type": "string"},
                "username": {"type": "string"},
                "icon_emoji": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
            },
            "required": ["message"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "sent": {"type": "boolean"},
                "status_code": {"type": "integer"},
            },
            "required": ["sent", "status_code"],
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["slack"],
        description="Slack Incoming Webhook으로 메시지 전송. Webhook URL은 credential.value로 주입",
        is_mvp=True,
        service_type="slack",
    )


def _email_send() -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid5(_CATALOG_NS, "email_send"),
        node_type="email_send",
        name="이메일 발송",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "smtp_host": {"type": "string"},
                "smtp_port": {"type": "integer", "default": 587},
                "from_address": {"type": "string"},
                "to_addresses": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "body_type": {"type": "string", "enum": ["plain", "html"], "default": "plain"},
                "use_tls": {"type": "boolean", "default": True},
            },
            "required": ["smtp_host", "from_address", "to_addresses", "subject", "body"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "sent": {"type": "boolean"},
                "recipients_count": {"type": "integer"},
            },
            "required": ["sent", "recipients_count"],
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=[],
        description="SMTP 이메일 발송 (비가역적). credential.value 형식: 'username:password'",
        is_mvp=True,
        service_type=None,
    )
