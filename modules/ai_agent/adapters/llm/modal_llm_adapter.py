from __future__ import annotations

import json
import os
import re
from typing import Any, TypeVar

import httpx
import modal
from pydantic import BaseModel

from common_schemas.exceptions import ExecutionError

from ...domain.ports.llm_port import LLMPort

T = TypeVar("T", bound=BaseModel)

# Modal cold start < 60s + P95 inference < 8s → 90s total
_DEFAULT_TIMEOUT = 90.0
_MODAL_APP_NAME = "llm-base"
_MODAL_CLS_NAME = "LLMBase"


class ModalLLMAdapter(LLMPort):
    """LLMPort 구현 — Modal llm-base app의 Gemma 4 추론 엔드포인트 호출.

    호출 방식:
        - generate / generate_structured: modal.Cls.from_name() → instance().generate.remote.aio()
          llm-base는 @app.cls / @modal.method() 구조이므로 Function.lookup() 대신
          Cls.from_name() 패턴 사용 (MODAL_TOKEN_ID / MODAL_TOKEN_SECRET 인증)
        - httpx.AsyncClient: web endpoint 직접 호출 또는 헬스체크 용도
          (LLM_BASE_URL 환경 변수 기반)
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._cls: Any | None = None  # modal.Cls (lazy lookup)

    def _modal_cls(self) -> Any:
        if self._cls is None:
            self._cls = modal.Cls.from_name(_MODAL_APP_NAME, _MODAL_CLS_NAME)
        return self._cls

    def _modal_instance(self) -> Any:
        """매 호출마다 새 인스턴스 핸들 반환 (Cls lookup은 캐시)."""
        return self._modal_cls()()

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        result: dict[str, Any] = await self._modal_instance().generate.remote.aio(
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

        _CANCEL_MARKERS = ("cancelled", "failure", "Function call")
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                use_grammar = attempt == 0  # 첫 시도만 json schema grammar 사용
                kwargs: dict[str, Any] = {"prompt": augmented}
                if use_grammar:
                    kwargs["format"] = "json"
                    kwargs["json_schema"] = schema_json

                result: dict[str, Any] = await self._modal_instance().generate.remote.aio(**kwargs)
                raw: str = result.get("generated_text", "").strip()

                # grammar cancel / 빈 응답 → 재시도
                if not raw or any(m in raw for m in _CANCEL_MARKERS):
                    last_exc = ExecutionError(
                        f"LLM 비정상 응답(시도 {attempt + 1}): {raw[:120]}", code="E_LLM_CANCEL"
                    )
                    continue

                # 마크다운 코드 펜스 제거
                raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
                raw = re.sub(r"\n?```\s*$", "", raw)
                return schema.model_validate_json(raw.strip())

            except Exception as exc:
                last_exc = exc
                continue

        raise ExecutionError(
            f"LLM structured 생성 3회 실패: {last_exc}", code="E_LLM_EMPTY"
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ModalLLMAdapter:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
