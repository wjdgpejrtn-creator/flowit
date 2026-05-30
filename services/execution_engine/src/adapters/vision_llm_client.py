"""llm-base(Gemma 4 멀티모달) HTTP 비전 클라이언트 — doc_parser VisionExtractor 주입용.

worker는 이미 `LLM_BASE_URL`(llm-base web endpoint) env를 갖고 있으므로 **Modal 토큰 없이**
HTTP로 비전 추론을 호출한다. Modal RPC(`.generate.remote()`) 대신 이 경로를 쓴다.

계약 (llm-base `services/agents/llm-base/main.py` 기준):
  요청 : POST {LLM_BASE_URL}/v1/generate
          {"prompt": str, "images": [data_url, ...], "max_tokens": int, "temperature": float, ...}
  응답 : {"generated_text": str, "finish_reason": str, "usage": {...}}

  ⚠️ llm-base `_run_generate`는 `images` kwargs를 이미 처리하지만(Gemma 4 vision), HTTP
  `GenerateReq`에 `images` 필드가 아직 없다 — 정혜님/REQ-011이 `GenerateReq.images:
  list[str] = []` + `generate_http`에서 `kwargs["images"] = req.images` 패스스루를 추가해야
  본 클라이언트가 실제로 동작한다. (그 전엔 images가 무시돼 텍스트 응답만 돌아옴.)

  VisionExtractor(쿠쿠/REQ-006)는 `self._llm.generate.remote(...)`를 `self._llm.generate(...)`로
  바꿔야 한다(transport-agnostic plain call). 본 클라이언트가 그 `.generate`를 제공한다.
"""
from __future__ import annotations

from typing import Any

import httpx

# vision 추론은 페이지 이미지 1장당 GPU inference — 텍스트보다 느림. 넉넉히.
_DEFAULT_TIMEOUT_SECONDS = 120.0


class HttpVisionLLM:
    """doc_parser VisionExtractor가 `llm.generate(prompt, images=[...]) -> dict`로 호출."""

    def __init__(self, base_url: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._url = base_url.rstrip("/") + "/v1/generate"
        self._timeout = timeout

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """llm-base /v1/generate 동기 POST. kwargs(images/max_tokens/temperature/...)는 그대로 전달."""
        payload: dict[str, Any] = {"prompt": prompt, **kwargs}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self._url, json=payload)
            resp.raise_for_status()
            return resp.json()
