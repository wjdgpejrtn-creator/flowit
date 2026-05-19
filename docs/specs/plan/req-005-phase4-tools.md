# Phase 4 — Tool 구현 (spec 15종 + 추가 도구)

> **대상 경로**: `modules/toolset/adapters/tools/`
> **구현 순서**: webhook → http_request → (spec 나머지) → llm → google_drive → gmail → google_calendar → google_sheets → slack
> **공통 패턴**: `BaseTool` 상속 + `@property` 메타데이터 + `async execute()` 구현

### spec 15종 구현 현황

| 카테고리 | 클래스 | risk_level | 구현 상태 |
|----------|--------|------------|----------|
| API 호출 | `HttpRequestTool` | High | ✅ 플랜 있음 |
| API 호출 | `RestApiTool` | Medium | ⬜ stub 추가 필요 |
| API 호출 | `GraphqlTool` | Medium | ⬜ stub 추가 필요 |
| API 호출 | `WebhookTool` | High | ✅ 플랜 있음 |
| 파일 처리 | `FileReadTool` | Low | ⬜ stub 추가 필요 |
| 파일 처리 | `FileWriteTool` | Medium | ⬜ stub 추가 필요 |
| 파일 처리 | `FileTransformTool` | Low | ⬜ stub 추가 필요 |
| 데이터 변환 | `JsonTransformTool` | Low | ⬜ stub 추가 필요 |
| 데이터 변환 | `TextTemplateTool` | Low | ⬜ stub 추가 필요 |
| 데이터 변환 | `DataMappingTool` | Low | ⬜ stub 추가 필요 |
| 조건/제어 | `ConditionalTool` | Low | ⬜ stub 추가 필요 |
| 조건/제어 | `LoopTool` | Medium | ⬜ stub 추가 필요 |
| 조건/제어 | `DelayTool` | Low | ⬜ stub 추가 필요 |
| 알림 | `EmailSendTool` | High | ⬜ stub 추가 필요 |
| 알림 | `SlackNotifyTool` | High | ⬜ stub 추가 필요 |

---

## ⚠️ 변경 사항 (common_schemas 실제 구현 반영)

| 항목 | 이전 플랜 (잘못됨) | 실제 구현 (올바름) |
|------|----------|----------|
| credential 토큰 필드 | `credential.token` | `credential.value` |
| ToolExecutionError import | `from common_schemas.exceptions import ToolExecutionError` | `from ...domain.exceptions import ToolExecutionError` |
| 예외 생성 방식 | `ToolExecutionError(code=ErrorCode.X, message="...")` | `ToolExecutionError(message="...", code="TOOL_EXECUTION_ERROR")` |
| Google SDK 인증 | `Credentials(token=credential.token)` | `Credentials(token=credential.value)` |

---

## 공통 패턴

```python
# adapters/tools/xxx_tool.py
from __future__ import annotations

from typing import Any

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError   # ← common_schemas 아님


class XxxTool(BaseTool):

    @property
    def name(self) -> str:
        return "xxx"                    # 고유 이름 (tool_name 기준)

    @property
    def description(self) -> str:
        return "..."                    # 도구 설명 (ToolMetadata.from_tool() 에서 사용)

    @property
    def version(self) -> str:
        return "1.0.0"                  # semver

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM         # LOW / MEDIUM / HIGH / RESTRICTED

    @property
    def input_schema(self) -> dict[str, Any]:
        return { ... }                  # JSON Schema Draft-7

    @property
    def output_schema(self) -> dict[str, Any]:
        return { ... }                  # JSON Schema Draft-7

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        # credential.value  ← 토큰값 (credential.token 아님)
        # credential.credential_kind  ← "fernet" or "aes_gcm"
        ...
```

---

## 4-1. `webhook_tool.py`

**가장 단순한 도구. 패턴 파악용으로 먼저 구현.**

```python
from __future__ import annotations

import os

import httpx

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError

_DEFAULT_TIMEOUT = int(os.getenv("TOOL_EXECUTION_TIMEOUT", "30"))
_MAX_RETRIES = int(os.getenv("WEBHOOK_MAX_RETRIES", "3"))


class WebhookTool(BaseTool):
    tool_id = "webhook"
    name = "Webhook"
    description = "지정된 URL로 HTTP 요청을 전송합니다. POST/GET/PUT/PATCH/DELETE 지원."
    risk_level = RiskLevel.HIGH

    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "format": "uri"},
            "method": {
                "type": "string",
                "enum": ["POST", "GET", "PUT", "PATCH", "DELETE"],
                "default": "POST",
            },
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "body": {"type": "object"},
            "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
        },
        "required": ["url"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "status_code": {"type": "integer"},
            "response_body": {},
            "headers": {"type": "object"},
            "elapsed_ms": {"type": "number"},
        },
        "required": ["status_code"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        url = input_data["url"]
        method = input_data.get("method", "POST").upper()
        headers = input_data.get("headers", {})
        body = input_data.get("body")
        timeout = input_data.get("timeout", _DEFAULT_TIMEOUT)

        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=body,
                    )
                    return {
                        "status_code": response.status_code,
                        "response_body": self._parse_response(response),
                        "headers": dict(response.headers),
                        "elapsed_ms": response.elapsed.total_seconds() * 1000,
                    }
            except httpx.TimeoutException as e:
                last_exc = e
            except httpx.RequestError as e:
                raise ToolExecutionError(
                    message=f"Webhook request failed: {e}",
                    code="TOOL_EXECUTION_ERROR",
                ) from e

        raise ToolExecutionError(
            message=f"Webhook timed out after {_MAX_RETRIES} retries: {url}",
            code="TOOL_EXECUTION_ERROR",
        ) from last_exc

    def _parse_response(self, response: httpx.Response) -> object:
        try:
            return response.json()
        except Exception:
            return response.text
```

---

## 4-2. `http_request_tool.py`

**Webhook보다 자유도 높음. Bearer 인증, 커스텀 헤더, form-data 등 지원.**

```python
from __future__ import annotations

import httpx

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError


class HttpRequestTool(BaseTool):
    tool_id = "http_request"
    name = "HTTP Request"
    description = "커스텀 HTTP 요청. Bearer 인증, form-data, query params 등 고급 옵션 지원."
    risk_level = RiskLevel.HIGH   # 임의 HTTP 요청 → 내부망 공격 가능성

    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "format": "uri"},
            "method": {"type": "string", "enum": ["POST", "GET", "PUT", "PATCH", "DELETE"]},
            "headers": {"type": "object"},
            "body": {},
            "body_type": {
                "type": "string",
                "enum": ["json", "form", "text"],
                "default": "json",
            },
            "query_params": {"type": "object"},
            "auth_type": {
                "type": "string",
                "enum": ["bearer", "basic", "none"],
                "default": "none",
            },
            "timeout": {"type": "integer", "default": 30},
            "verify_ssl": {"type": "boolean", "default": True},
        },
        "required": ["url", "method"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "status_code": {"type": "integer"},
            "response_body": {},
            "headers": {"type": "object"},
            "elapsed_ms": {"type": "number"},
        },
        "required": ["status_code"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        headers = dict(input_data.get("headers", {}))

        # credential 있으면 Bearer 토큰 주입
        # ⚠️ credential.value 사용 (credential.token 아님)
        if credential and input_data.get("auth_type") == "bearer":
            headers["Authorization"] = f"Bearer {credential.value}"

        body_type = input_data.get("body_type", "json")
        body = input_data.get("body")

        async with httpx.AsyncClient(
            timeout=input_data.get("timeout", 30),
            verify=input_data.get("verify_ssl", True),
        ) as client:
            try:
                request_kwargs: dict = {
                    "method": input_data["method"],
                    "url": input_data["url"],
                    "headers": headers,
                    "params": input_data.get("query_params"),
                }
                if body_type == "json":
                    request_kwargs["json"] = body
                elif body_type == "form":
                    request_kwargs["data"] = body
                elif body_type == "text":
                    request_kwargs["content"] = str(body)

                response = await client.request(**request_kwargs)
                return {
                    "status_code": response.status_code,
                    "response_body": self._parse_response(response),
                    "headers": dict(response.headers),
                    "elapsed_ms": response.elapsed.total_seconds() * 1000,
                }
            except httpx.RequestError as e:
                raise ToolExecutionError(
                    message=f"HTTP request failed: {e}",
                    code="TOOL_EXECUTION_ERROR",
                ) from e

    def _parse_response(self, response: httpx.Response) -> object:
        try:
            return response.json()
        except Exception:
            return response.text
```

---

## 4-3. `llm_tool.py`

**Modal L4 GPU의 Gemma4 호출.**

```python
from __future__ import annotations

import os

import httpx

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError

_MODAL_ENDPOINT = os.getenv("MODAL_LLM_ENDPOINT")   # 환경변수로 주입


class LLMTool(BaseTool):
    tool_id = "llm"
    name = "LLM (Gemma 4)"
    description = "Modal GPU에서 실행 중인 Gemma 4 모델로 텍스트를 생성합니다."
    risk_level = RiskLevel.LOW

    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "system_prompt": {"type": "string"},
            "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096, "default": 512},
            "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0, "default": 0.7},
        },
        "required": ["prompt"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "usage": {
                "type": "object",
                "properties": {
                    "prompt_tokens": {"type": "integer"},
                    "completion_tokens": {"type": "integer"},
                    "total_tokens": {"type": "integer"},
                },
            },
            "model": {"type": "string"},
        },
        "required": ["text"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        if not _MODAL_ENDPOINT:
            raise ToolExecutionError(
                message="MODAL_LLM_ENDPOINT environment variable is not set.",
                code="TOOL_EXECUTION_ERROR",
            )

        payload = {
            "prompt": input_data["prompt"],
            "max_tokens": input_data.get("max_tokens", 512),
            "temperature": input_data.get("temperature", 0.7),
        }
        if system_prompt := input_data.get("system_prompt"):
            payload["system_prompt"] = system_prompt

        async with httpx.AsyncClient(timeout=120) as client:
            try:
                response = await client.post(_MODAL_ENDPOINT, json=payload)
                response.raise_for_status()
                data = response.json()
                return {
                    "text": data["text"],
                    "usage": data.get("usage", {}),
                    "model": data.get("model", "gemma-4"),
                }
            except httpx.HTTPStatusError as e:
                raise ToolExecutionError(
                    message=f"LLM API error {e.response.status_code}: {e.response.text}",
                    code="TOOL_EXECUTION_ERROR",
                ) from e
            except httpx.RequestError as e:
                raise ToolExecutionError(
                    message=f"LLM API request failed: {e}",
                    code="TOOL_EXECUTION_ERROR",
                ) from e
```

---

## 4-4. `google_drive_tool.py`

```python
from __future__ import annotations

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError


class GoogleDriveTool(BaseTool):
    tool_id = "google_drive"
    name = "Google Drive"
    description = "Google Drive 파일 업로드, 다운로드, 목록 조회, 공유 기능을 제공합니다."
    risk_level = RiskLevel.MEDIUM

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["upload", "download", "list", "share", "delete", "move"],
            },
            "file_id": {"type": "string"},
            "file_name": {"type": "string"},
            "content": {"type": "string"},
            "mime_type": {"type": "string"},
            "parent_folder_id": {"type": "string"},
            "share_email": {"type": "string"},
            "share_role": {
                "type": "string",
                "enum": ["reader", "writer", "commenter"],
                "default": "reader",
            },
            "query": {"type": "string"},
            "page_size": {"type": "integer", "default": 10, "maximum": 100},
        },
        "required": ["action"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "file_name": {"type": "string"},
            "content": {"type": "string"},
            "mime_type": {"type": "string"},
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "mimeType": {"type": "string"},
                    },
                },
            },
            "web_view_link": {"type": "string"},
            "success": {"type": "boolean"},
        },
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        service = self._build_service(credential)
        action = input_data["action"]

        dispatch = {
            "upload": self._upload,
            "download": self._download,
            "list": self._list,
            "share": self._share,
            "delete": self._delete,
            "move": self._move,
        }

        handler = dispatch.get(action)
        if not handler:
            raise ToolExecutionError(
                message=f"Unsupported action: {action}",
                code="TOOL_EXECUTION_ERROR",
            )
        return await handler(service, input_data)

    def _build_service(self, credential: PlaintextCredential | None):
        if not credential:
            raise ToolExecutionError(
                message="Google Drive requires OAuth credential.",
                code="TOOL_EXECUTION_ERROR",
            )
        # ⚠️ credential.value 사용 (credential.token 아님)
        creds = Credentials(token=credential.value)
        return build("drive", "v3", credentials=creds)

    async def _upload(self, service, params: dict) -> dict:
        content = params.get("content", "").encode()
        mime_type = params.get("mime_type", "text/plain")
        media = MediaInMemoryUpload(content, mimetype=mime_type)
        metadata = {"name": params["file_name"]}
        if folder_id := params.get("parent_folder_id"):
            metadata["parents"] = [folder_id]
        file = service.files().create(body=metadata, media_body=media, fields="id,name,webViewLink").execute()
        return {"file_id": file["id"], "file_name": file["name"], "web_view_link": file.get("webViewLink")}

    async def _download(self, service, params: dict) -> dict:
        content = service.files().get_media(fileId=params["file_id"]).execute()
        meta = service.files().get(fileId=params["file_id"], fields="name,mimeType").execute()
        return {"file_id": params["file_id"], "file_name": meta["name"], "content": content.decode(errors="replace")}

    async def _list(self, service, params: dict) -> dict:
        q = params.get("query", "")
        result = service.files().list(q=q, pageSize=params.get("page_size", 10), fields="files(id,name,mimeType)").execute()
        return {"files": result.get("files", [])}

    async def _share(self, service, params: dict) -> dict:
        permission = {"type": "user", "role": params.get("share_role", "reader"), "emailAddress": params["share_email"]}
        service.permissions().create(fileId=params["file_id"], body=permission).execute()
        return {"success": True, "file_id": params["file_id"]}

    async def _delete(self, service, params: dict) -> dict:
        service.files().delete(fileId=params["file_id"]).execute()
        return {"success": True, "file_id": params["file_id"]}

    async def _move(self, service, params: dict) -> dict:
        file = service.files().get(fileId=params["file_id"], fields="parents").execute()
        prev_parents = ",".join(file.get("parents", []))
        service.files().update(
            fileId=params["file_id"],
            addParents=params["parent_folder_id"],
            removeParents=prev_parents,
        ).execute()
        return {"success": True, "file_id": params["file_id"]}
```

---

## 4-5. `gmail_tool.py`

```python
from __future__ import annotations

import base64
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError


class GmailTool(BaseTool):
    tool_id = "gmail"
    name = "Gmail"
    description = "이메일 발송, 읽기, 검색, 보관 기능을 제공합니다."
    risk_level = RiskLevel.HIGH

    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["send", "read", "search", "archive"]},
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "message_id": {"type": "string"},
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["action"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "message_id": {"type": "string"},
            "thread_id": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "messages": {"type": "array"},
            "success": {"type": "boolean"},
        },
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        service = self._build_service(credential)
        action = input_data["action"]
        dispatch = {
            "send": self._send,
            "read": self._read,
            "search": self._search,
            "archive": self._archive,
        }
        return await dispatch[action](service, input_data)

    def _build_service(self, credential: PlaintextCredential | None):
        if not credential:
            raise ToolExecutionError(
                message="Gmail requires OAuth credential.",
                code="TOOL_EXECUTION_ERROR",
            )
        # ⚠️ credential.value 사용
        creds = Credentials(token=credential.value)
        return build("gmail", "v1", credentials=creds)

    async def _send(self, service, params: dict) -> dict:
        msg = MIMEText(params["body"])
        msg["to"] = params["to"]
        msg["subject"] = params["subject"]
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"message_id": result["id"], "thread_id": result["threadId"], "success": True}

    async def _read(self, service, params: dict) -> dict:
        msg = service.users().messages().get(userId="me", id=params["message_id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        body = self._extract_body(msg["payload"])
        return {"message_id": msg["id"], "subject": headers.get("Subject", ""), "body": body}

    async def _search(self, service, params: dict) -> dict:
        result = service.users().messages().list(
            userId="me", q=params.get("query", ""), maxResults=params.get("max_results", 10)
        ).execute()
        return {"messages": result.get("messages", [])}

    async def _archive(self, service, params: dict) -> dict:
        service.users().messages().modify(
            userId="me", id=params["message_id"], body={"removeLabelIds": ["INBOX"]}
        ).execute()
        return {"success": True, "message_id": params["message_id"]}

    def _extract_body(self, payload: dict) -> str:
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part["body"].get("data", "")
                    return base64.urlsafe_b64decode(data).decode(errors="replace")
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data).decode(errors="replace") if data else ""
```

---

## 4-6. `google_calendar_tool.py`

```python
from __future__ import annotations

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError


class GoogleCalendarTool(BaseTool):
    tool_id = "google_calendar"
    name = "Google Calendar"
    description = "Google 캘린더 이벤트 생성, 조회, 수정, 삭제 기능을 제공합니다."
    risk_level = RiskLevel.LOW

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create_event", "list_events", "update_event", "delete_event"],
            },
            "calendar_id": {"type": "string", "default": "primary"},
            "event_id": {"type": "string"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "start_datetime": {"type": "string", "format": "date-time"},
            "end_datetime": {"type": "string", "format": "date-time"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "time_min": {"type": "string", "format": "date-time"},
            "time_max": {"type": "string", "format": "date-time"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["action"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "summary": {"type": "string"},
            "html_link": {"type": "string"},
            "events": {"type": "array"},
            "success": {"type": "boolean"},
        },
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        if not credential:
            raise ToolExecutionError(
                message="Google Calendar requires OAuth credential.",
                code="TOOL_EXECUTION_ERROR",
            )
        # ⚠️ credential.value 사용
        creds = Credentials(token=credential.value)
        service = build("calendar", "v3", credentials=creds)
        action = input_data["action"]

        dispatch = {
            "create_event": self._create_event,
            "list_events": self._list_events,
            "update_event": self._update_event,
            "delete_event": self._delete_event,
        }
        return await dispatch[action](service, input_data)

    async def _create_event(self, service, params: dict) -> dict:
        body = {
            "summary": params["summary"],
            "start": {"dateTime": params["start_datetime"], "timeZone": "Asia/Seoul"},
            "end": {"dateTime": params["end_datetime"], "timeZone": "Asia/Seoul"},
        }
        if params.get("description"):
            body["description"] = params["description"]
        if params.get("attendees"):
            body["attendees"] = [{"email": e} for e in params["attendees"]]
        event = service.events().insert(calendarId=params.get("calendar_id", "primary"), body=body).execute()
        return {"event_id": event["id"], "summary": event["summary"], "html_link": event.get("htmlLink")}

    async def _list_events(self, service, params: dict) -> dict:
        result = service.events().list(
            calendarId=params.get("calendar_id", "primary"),
            timeMin=params.get("time_min"),
            timeMax=params.get("time_max"),
            maxResults=params.get("max_results", 10),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return {"events": result.get("items", [])}

    async def _update_event(self, service, params: dict) -> dict:
        event = service.events().get(
            calendarId=params.get("calendar_id", "primary"), eventId=params["event_id"]
        ).execute()
        if params.get("summary"):
            event["summary"] = params["summary"]
        if params.get("start_datetime"):
            event["start"] = {"dateTime": params["start_datetime"], "timeZone": "Asia/Seoul"}
        if params.get("end_datetime"):
            event["end"] = {"dateTime": params["end_datetime"], "timeZone": "Asia/Seoul"}
        updated = service.events().update(
            calendarId=params.get("calendar_id", "primary"), eventId=params["event_id"], body=event
        ).execute()
        return {"event_id": updated["id"], "summary": updated["summary"], "success": True}

    async def _delete_event(self, service, params: dict) -> dict:
        service.events().delete(
            calendarId=params.get("calendar_id", "primary"), eventId=params["event_id"]
        ).execute()
        return {"success": True, "event_id": params["event_id"]}
```

---

## 4-7. `google_sheets_tool.py`

```python
from __future__ import annotations

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError


class GoogleSheetsTool(BaseTool):
    tool_id = "google_sheets"
    name = "Google Sheets"
    description = "Google 스프레드시트 읽기, 쓰기, 행 추가, 시트 생성 기능을 제공합니다."
    risk_level = RiskLevel.MEDIUM

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "append", "create"],
            },
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},     # 예: "Sheet1!A1:D10"
            "values": {"type": "array"},      # write/append용 2D 배열
            "title": {"type": "string"},      # create용 스프레드시트 제목
        },
        "required": ["action"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "values": {"type": "array"},
            "updated_range": {"type": "string"},
            "updated_rows": {"type": "integer"},
            "spreadsheet_url": {"type": "string"},
            "success": {"type": "boolean"},
        },
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        if not credential:
            raise ToolExecutionError(
                message="Google Sheets requires OAuth credential.",
                code="TOOL_EXECUTION_ERROR",
            )
        # ⚠️ credential.value 사용
        creds = Credentials(token=credential.value)
        service = build("sheets", "v4", credentials=creds)
        sheets = service.spreadsheets()

        dispatch = {
            "read": self._read,
            "write": self._write,
            "append": self._append,
            "create": self._create,
        }
        return await dispatch[input_data["action"]](sheets, input_data)

    async def _read(self, sheets, params: dict) -> dict:
        result = sheets.values().get(
            spreadsheetId=params["spreadsheet_id"], range=params["range"]
        ).execute()
        return {"values": result.get("values", []), "spreadsheet_id": params["spreadsheet_id"]}

    async def _write(self, sheets, params: dict) -> dict:
        result = sheets.values().update(
            spreadsheetId=params["spreadsheet_id"],
            range=params["range"],
            valueInputOption="USER_ENTERED",
            body={"values": params["values"]},
        ).execute()
        return {
            "updated_range": result.get("updatedRange"),
            "updated_rows": result.get("updatedRows", 0),
            "success": True,
        }

    async def _append(self, sheets, params: dict) -> dict:
        result = sheets.values().append(
            spreadsheetId=params["spreadsheet_id"],
            range=params["range"],
            valueInputOption="USER_ENTERED",
            body={"values": params["values"]},
        ).execute()
        return {
            "updated_range": result.get("updates", {}).get("updatedRange"),
            "updated_rows": result.get("updates", {}).get("updatedRows", 0),
            "success": True,
        }

    async def _create(self, sheets, params: dict) -> dict:
        spreadsheet = {"properties": {"title": params.get("title", "새 스프레드시트")}}
        result = sheets.create(body=spreadsheet, fields="spreadsheetId,spreadsheetUrl").execute()
        return {
            "spreadsheet_id": result["spreadsheetId"],
            "spreadsheet_url": result.get("spreadsheetUrl"),
            "success": True,
        }
```

---

## 4-8. `slack_tool.py`

```python
from __future__ import annotations

import os

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from ...domain.base_tool import BaseTool
from ...domain.exceptions import ToolExecutionError

_SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")   # credential 없을 때 fallback


class SlackTool(BaseTool):
    tool_id = "slack"
    name = "Slack"
    description = "Slack 채널 메시지 전송, 스레드 답글, 파일 업로드 기능을 제공합니다."
    risk_level = RiskLevel.MEDIUM

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_message", "post_thread", "upload_file"],
            },
            "channel": {"type": "string"},
            "text": {"type": "string"},
            "thread_ts": {"type": "string"},       # post_thread용
            "file_content": {"type": "string"},    # upload_file용
            "file_name": {"type": "string"},
            "blocks": {"type": "array"},            # Block Kit JSON
        },
        "required": ["action", "channel"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "channel": {"type": "string"},
            "ts": {"type": "string"},
            "message": {"type": "object"},
        },
        "required": ["ok"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential: PlaintextCredential | None = kwargs.get("credential")
        # ⚠️ credential.value 사용. 없으면 환경변수 fallback
        token = credential.value if credential else _SLACK_BOT_TOKEN
        if not token:
            raise ToolExecutionError(
                message="Slack token not available (credential or SLACK_BOT_TOKEN required).",
                code="TOOL_EXECUTION_ERROR",
            )

        client = AsyncWebClient(token=token)
        action = input_data["action"]

        try:
            if action == "send_message":
                resp = await client.chat_postMessage(
                    channel=input_data["channel"],
                    text=input_data.get("text", ""),
                    blocks=input_data.get("blocks"),
                )
            elif action == "post_thread":
                resp = await client.chat_postMessage(
                    channel=input_data["channel"],
                    text=input_data.get("text", ""),
                    thread_ts=input_data["thread_ts"],
                )
            elif action == "upload_file":
                resp = await client.files_upload(
                    channels=input_data["channel"],
                    content=input_data.get("file_content", ""),
                    filename=input_data.get("file_name", "file.txt"),
                )
            else:
                raise ToolExecutionError(
                    message=f"Unsupported Slack action: {action}",
                    code="TOOL_EXECUTION_ERROR",
                )

            return {
                "ok": resp.get("ok", False),
                "channel": resp.get("channel"),
                "ts": resp.get("ts"),
                "message": resp.get("message"),
            }

        except SlackApiError as e:
            raise ToolExecutionError(
                message=f"Slack API error: {e.response['error']}",
                code="TOOL_EXECUTION_ERROR",
            ) from e
```

---

---

## 4-9. spec 15종 — 누락 도구 Stubs

> 아래 13개는 spec 기준 필수 구현 도구. 현재 skeleton만 제공. Phase 4 구현 시 완성 필요.

```python
# adapters/tools/rest_api_tool.py
from ...domain.base_tool import BaseTool
from common_schemas.enums import RiskLevel
from typing import Any

class RestApiTool(BaseTool):
    @property
    def name(self) -> str: return "rest_api"
    @property
    def description(self) -> str: return "REST API 호출 + 응답 파싱"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.MEDIUM
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/graphql_tool.py
class GraphqlTool(BaseTool):
    @property
    def name(self) -> str: return "graphql"
    @property
    def description(self) -> str: return "GraphQL 쿼리/뮤테이션"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.MEDIUM
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/file_read_tool.py
class FileReadTool(BaseTool):
    @property
    def name(self) -> str: return "file_read"
    @property
    def description(self) -> str: return "파일 읽기"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.LOW
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/file_write_tool.py
class FileWriteTool(BaseTool):
    @property
    def name(self) -> str: return "file_write"
    @property
    def description(self) -> str: return "파일 쓰기/생성"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.MEDIUM
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/file_transform_tool.py
class FileTransformTool(BaseTool):
    @property
    def name(self) -> str: return "file_transform"
    @property
    def description(self) -> str: return "포맷 변환 (CSV↔JSON 등)"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.LOW
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/json_transform_tool.py
class JsonTransformTool(BaseTool):
    @property
    def name(self) -> str: return "json_transform"
    @property
    def description(self) -> str: return "JMESPath/JSONPath 변환"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.LOW
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/text_template_tool.py
class TextTemplateTool(BaseTool):
    @property
    def name(self) -> str: return "text_template"
    @property
    def description(self) -> str: return "Jinja2 템플릿 렌더링"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.LOW
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/data_mapping_tool.py
class DataMappingTool(BaseTool):
    @property
    def name(self) -> str: return "data_mapping"
    @property
    def description(self) -> str: return "필드 매핑/리네이밍"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.LOW
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/conditional_tool.py
class ConditionalTool(BaseTool):
    @property
    def name(self) -> str: return "conditional"
    @property
    def description(self) -> str: return "조건 분기 (if/else)"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.LOW
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/loop_tool.py
class LoopTool(BaseTool):
    @property
    def name(self) -> str: return "loop"
    @property
    def description(self) -> str: return "반복 실행 (배열 순회)"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.MEDIUM
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/delay_tool.py
class DelayTool(BaseTool):
    @property
    def name(self) -> str: return "delay"
    @property
    def description(self) -> str: return "대기/지연"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.LOW
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/email_send_tool.py
class EmailSendTool(BaseTool):
    @property
    def name(self) -> str: return "email_send"
    @property
    def description(self) -> str: return "이메일 발송"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.HIGH
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

```python
# adapters/tools/slack_notify_tool.py
class SlackNotifyTool(BaseTool):
    @property
    def name(self) -> str: return "slack_notify"
    @property
    def description(self) -> str: return "Slack 메시지 전송"
    @property
    def version(self) -> str: return "1.0.0"
    @property
    def risk_level(self) -> RiskLevel: return RiskLevel.HIGH
    @property
    def input_schema(self) -> dict[str, Any]: return {}
    @property
    def output_schema(self) -> dict[str, Any]: return {}
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        raise NotImplementedError
```

---

## 4-10. `adapters/tools/__init__.py`

```python
# spec 15종
from .webhook_tool import WebhookTool
from .http_request_tool import HttpRequestTool
from .rest_api_tool import RestApiTool
from .graphql_tool import GraphqlTool
from .file_read_tool import FileReadTool
from .file_write_tool import FileWriteTool
from .file_transform_tool import FileTransformTool
from .json_transform_tool import JsonTransformTool
from .text_template_tool import TextTemplateTool
from .data_mapping_tool import DataMappingTool
from .conditional_tool import ConditionalTool
from .loop_tool import LoopTool
from .delay_tool import DelayTool
from .email_send_tool import EmailSendTool
from .slack_notify_tool import SlackNotifyTool
# 추가 도구 (spec 외)
from .llm_tool import LLMTool
from .google_drive_tool import GoogleDriveTool
from .gmail_tool import GmailTool
from .google_calendar_tool import GoogleCalendarTool
from .google_sheets_tool import GoogleSheetsTool
from .slack_tool import SlackTool

ALL_TOOLS = [
    # spec 15종
    WebhookTool(), HttpRequestTool(), RestApiTool(), GraphqlTool(),
    FileReadTool(), FileWriteTool(), FileTransformTool(),
    JsonTransformTool(), TextTemplateTool(), DataMappingTool(),
    ConditionalTool(), LoopTool(), DelayTool(),
    EmailSendTool(), SlackNotifyTool(),
    # 추가 도구
    LLMTool(), GoogleDriveTool(), GmailTool(),
    GoogleCalendarTool(), GoogleSheetsTool(), SlackTool(),
]
```

---

## 환경 변수 요약

| 변수명 | 필수 | 사용 도구 | 설명 |
|--------|------|---------|------|
| `TOOL_EXECUTION_TIMEOUT` | N | 모든 도구 | 기본 타임아웃 (기본: 30초) |
| `WEBHOOK_MAX_RETRIES` | N | WebhookTool | 재시도 횟수 (기본: 3) |
| `MODAL_LLM_ENDPOINT` | Y | LLMTool | Modal GPU Gemma4 엔드포인트 |
| `SLACK_BOT_TOKEN` | 조건부 | SlackTool | credential 없을 때 fallback |

---

## 확인 체크리스트

- [ ] 모든 도구: `credential.value` 사용 (`credential.token` 아님)
- [ ] 모든 도구: `ToolExecutionError(message="...", code="TOOL_EXECUTION_ERROR")` 형식
- [ ] 모든 도구: `from ...domain.exceptions import ToolExecutionError` import 경로
- [ ] `WebhookTool`: retry 로직 + `_MAX_RETRIES` 환경변수
- [ ] `HttpRequestTool`: `risk_level = RiskLevel.HIGH` (임의 HTTP)
- [ ] `LLMTool`: `_MODAL_ENDPOINT` 없으면 즉시 에러
- [ ] Google 도구 4개: `Credentials(token=credential.value)` 빌드
- [ ] `SlackTool`: credential 없을 때 `SLACK_BOT_TOKEN` fallback
- [ ] `ALL_TOOLS` 리스트로 ToolRegistryAdapter 일괄 등록 가능
