from __future__ import annotations

import json
import os
from typing import Any, TypeVar

import httpx
import modal
from pydantic import BaseModel

from ...domain.ports.llm_port import LLMPort

T = TypeVar("T", bound=BaseModel)

# Modal cold start < 60s + P95 inference < 8s → 90s total
_DEFAULT_TIMEOUT = 90.0
_MODAL_APP_NAME = "llm-base"
_MODAL_FN_NAME = "generate"


class ModalLLMAdapter(LLMPort):
    """LLMPort 구현 — Modal llm-base app의 Gemma 4 추론 엔드포인트 호출.

    호출 방식:
        - generate / generate_structured: modal.Function.lookup() → .remote.aio()
          (Modal RPC — MODAL_TOKEN_ID / MODAL_TOKEN_SECRET 인증 사용)
        - httpx.AsyncClient: web endpoint 직접 호출 또는 헬스체크 용도
          (LLM_BASE_URL 환경 변수 기반)
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._fn: modal.Function | None = None

    def _modal_fn(self) -> modal.Function:
        if self._fn is None:
            self._fn = modal.Function.lookup(_MODAL_APP_NAME, _MODAL_FN_NAME)
        return self._fn

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        result: dict[str, Any] = await self._modal_fn().remote.aio(
            prompt=prompt, **kwargs
        )
        return result["generated_text"]

    async def generate_structured(self, prompt: str, schema: type[T]) -> T:
        schema_json = schema.model_json_schema()
        augmented = (
            f"{prompt}\n\n"
            "아래 JSON 스키마에 맞는 JSON 객체만 반환하세요. "
            "설명이나 마크다운 없이 JSON만 출력하세요:\n"
            f"{json.dumps(schema_json, ensure_ascii=False)}"
        )
        result: dict[str, Any] = await self._modal_fn().remote.aio(
            prompt=augmented,
            format="json",
            json_schema=schema_json,
        )
        raw: str = result["generated_text"]
        return schema.model_validate_json(raw)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ModalLLMAdapter:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
