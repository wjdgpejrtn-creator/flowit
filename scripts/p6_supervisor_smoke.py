"""P6 staging smoke — supervisor 루프 직접 호출(orchestrator /v1/agent/route).

api_server SSO를 우회해 orchestrator를 직접 때려 supervisor 프레임 시퀀스를 검증한다.
한글 메시지는 argv 인코딩 깨짐을 피해 **스크립트 내부 상수**(SCENARIOS)로 둔다. 사용:
    python scripts/p6_supervisor_smoke.py "<url>" <scenario_key> [max_seconds]
scenario_key: chitchat | draft | composite
"""
from __future__ import annotations

import io
import json
import sys
import time
from uuid import uuid4

import httpx
from common_schemas import AgentState
from common_schemas.agent_protocol import AgentProtocolRequest
from common_schemas.enums import AgentMode, ExecutionStatus

# Windows 콘솔 UTF-8 강제 (한글 출력 mojibake 방지) — import는 stdout에 쓰지 않으므로
# reconfig를 import 뒤·첫 print 전에 둔다(E402 회피, 동작 동일).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# (message, round, selected_skill_id) — UTF-8 소스 상수로 인코딩 안전.
SCENARIOS: dict[str, tuple[str, int, str | None]] = {
    "chitchat": ("안녕하세요, 오늘 기분이 참 좋네요!", 1, None),
    "draft": (
        "매일 오전 9시에 슬랙 #general 채널로 오늘 날씨 요약을 보내는 워크플로우를 만들어줘",
        1,
        None,
    ),
    "draft_simple": (
        "웹훅으로 데이터를 받으면 슬랙 #general 채널로 그 내용을 메시지로 보내는 워크플로우를 만들어줘",
        1,
        None,
    ),
    "composite": (
        "날씨를 한 줄로 요약해 주는 스킬을 만들어서, 그 스킬을 이용해 "
        "매일 아침 슬랙으로 날씨 알림을 보내는 워크플로우를 만들어줘",
        1,
        None,
    ),
}


def build_body(message: str, round_: int, selected_skill_id: str | None) -> dict:
    state = AgentState(
        session_id=uuid4(),
        user_id=uuid4(),
        messages=[{"role": "user", "content": message}],
        turn_count=round_,
        mode=AgentMode.WIZARD,
        execution_status=ExecutionStatus.RUNNING,
    )
    payload: dict = {"message": message, "round": round_}
    if selected_skill_id:
        payload["selected_skill_id"] = selected_skill_id
    req = AgentProtocolRequest(
        session_id=state.session_id,
        user_id=state.user_id,
        state=state,
        payload=payload,
        trace_id=f"p6-smoke-{uuid4().hex[:8]}",
    )
    return json.loads(req.model_dump_json())


def run(url: str, message: str, round_: int, skill_id: str | None, max_s: float) -> int:
    body = build_body(message, round_, skill_id)
    route = url.rstrip("/") + "/v1/agent/route"
    seq: list[str] = []
    chats: list[str] = []
    errors: list[str] = []
    result_payload = None
    final_action = None
    hb = 0
    n = 0
    t0 = time.monotonic()
    print(f"\n=== SMOKE: {message!r} (round={round_}, skill={skill_id}) ===")
    try:
        with httpx.stream("POST", route, json=body, timeout=httpx.Timeout(max_s + 30)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if time.monotonic() - t0 > max_s:
                    final_action = "TIMEOUT(capture cap)"
                    break
                if not line or not line.startswith("data:"):
                    continue
                env = json.loads(line[5:].strip())
                final_action = env.get("next_action")
                for f in env.get("frames", []):
                    ft = f.get("frame_type")
                    if ft == "heartbeat":
                        hb += 1
                        continue
                    n += 1
                    if ft == "agent_node":
                        seq.append(f.get("agent_node_name", "?"))
                    elif ft in ("chat_message", "chat"):
                        chats.append((f.get("content") or f.get("message") or "")[:60])
                    elif ft == "error":
                        errors.append(f"{f.get('code')}: {f.get('message')}")
                    elif ft == "result":
                        result_payload = f.get("payload")
                sd = env.get("state_delta") or {}
                if sd.get("error"):
                    errors.append(f"envelope.error: {sd['error'][:80]}")
                if final_action in ("complete", "error"):
                    break
    except Exception as exc:  # noqa: BLE001
        errors.append(f"transport: {type(exc).__name__}: {exc}")
    dt = time.monotonic() - t0
    print(f"  elapsed={dt:.1f}s frames={n} heartbeats={hb} final={final_action}")
    print(f"  agent_node 순서: {' → '.join(seq) if seq else '(없음)'}")
    if chats:
        print("  chat:")
        for c in chats:
            print(f"    - {c}")
    if result_payload is not None:
        rp = result_payload if isinstance(result_payload, dict) else {}
        print(f"  result: status={rp.get('status')} workflow_id={rp.get('workflow_id')}")
    if errors:
        print("  ERRORS:")
        for e in errors:
            print(f"    ! {e}")
    return 0 if not errors else 1


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    key = sys.argv[2] if len(sys.argv) > 2 else "chitchat"
    max_s = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
    message, round_, skill_id = SCENARIOS[key]
    sys.exit(run(url, message, round_, skill_id, max_s))
