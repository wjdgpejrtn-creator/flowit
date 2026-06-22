"""Sub-Agent SSE 프록시 공통 헬퍼 (REQ-009/010/013).

orchestrator / skills-builder 등 Modal sub-agent의 `/v1/agent/route`는 응답을
`AgentProtocolResponse` 봉투(`data: {frames:[...], next_action, state_delta}`) SSE로 내보낸다.
api_server는 이 봉투에서 frame만 꺼내 프론트로 재전송한다 — 그 공통 로직(표준 헤더 + 봉투
언래핑)을 한 곳(SSOT)에 둔다. agents 라우터와 skills 추출 라우터가 함께 사용한다.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

# SSE 응답 표준 헤더 — Google Cloud LB의 gzip 압축으로 SSE 스트리밍이 깨지는 것 차단.
# - Cache-Control no-transform: LB에 응답 바디 변환 금지 지시 (핵심)
# - X-Accel-Buffering no: nginx/reverse-proxy 버퍼링 차단
# - Connection keep-alive: HTTP/1.1 keep-alive 명시
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def unwrap_agent_sse(raw: str) -> Iterator[str]:
    """AgentProtocolResponse 봉투(raw JSON)에서 frame을 꺼내 SSE 데이터 라인으로 변환.

    파싱 불가한 라인은 조용히 무시(빈 이터레이터). 각 frame은 `data: <json>\\n\\n` 한 줄.
    """
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return
    for frame in envelope.get("frames", []):
        yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
