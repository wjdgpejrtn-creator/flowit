"""Personalization Agent E2E 테스트 — Modal 앱 HTTP 직접 호출.

실행 전 준비:
    export PERSONALIZATION_AGENT_URL=https://<workspace>--agent-personalization-personalizationagent-fastapi.modal.run
    python modules/ai_agent/tests/manual/test_personalization_e2e.py

검증 순서:
    health → load_memory → update_memory → recall_skills → cleanup_memory

pytest 자동 수집 대상 아님 — 직접 실행 전용 (pyproject.toml norecursedirs: tests/manual)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any

import httpx

# ── 설정 ──────────────────────────────────────────────────────────────────────
MODAL_URL = os.getenv("PERSONALIZATION_AGENT_URL", "")
TIMEOUT = 30.0
# ──────────────────────────────────────────────────────────────────────────────

SESSION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

BASE_STATE = {
    "session_id": str(SESSION_ID),
    "user_id": str(USER_ID),
    "messages": [],
    "turn_count": 1,
    "mode": "general",
    "execution_status": "running",
    "personal_memory": [],
}

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
SKIP = "\033[93m[SKIP]\033[0m"

_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    status = PASS if ok else FAIL
    msg = f"  {detail}" if detail else ""
    print(f"{status} {name}{msg}")


def _build_request(action: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action}
    if extra:
        payload.update(extra)
    return {
        "session_id": str(SESSION_ID),
        "user_id": str(USER_ID),
        "state": BASE_STATE,
        "personal_memory": [],
        "payload": payload,
        "trace_id": f"e2e-{action}",
    }


async def check_health(client: httpx.AsyncClient) -> bool:
    print("\n── 1. Health Check ───────────────────────────────────────────")
    try:
        r = await client.get(f"{MODAL_URL}/v1/health")
        ok = r.status_code == 200
        body = r.json()
        _record("GET /v1/health", ok, json.dumps(body, ensure_ascii=False))
        return ok
    except Exception as exc:
        _record("GET /v1/health", False, str(exc))
        return False


async def test_load_memory(client: httpx.AsyncClient) -> None:
    print("\n── 2. load_memory ────────────────────────────────────────────")
    try:
        r = await client.post(
            f"{MODAL_URL}/v1/agent/route",
            json=_build_request("load_memory"),
        )
        ok = r.status_code == 200
        body = r.json()
        has_key = "personal_memory" in body.get("state_delta", {})
        _record("load_memory → 200", ok, f"status={r.status_code}")
        _record("load_memory → state_delta.personal_memory 존재", has_key)
        if ok:
            entries = body["state_delta"]["personal_memory"]
            _record(
                f"load_memory → entries 타입 확인 (list)",
                isinstance(entries, list),
                f"len={len(entries)}",
            )
    except Exception as exc:
        _record("load_memory", False, str(exc))


async def test_update_memory(client: httpx.AsyncClient) -> None:
    print("\n── 3. update_memory ──────────────────────────────────────────")
    dummy_workflow = {
        "workflow_id": str(uuid.uuid4()),
        "name": "E2E 테스트 워크플로우",
        "scope": "private",
        "is_draft": True,
        "nodes": [],
        "connections": [],
    }
    try:
        r = await client.post(
            f"{MODAL_URL}/v1/agent/route",
            json=_build_request(
                "update_memory",
                {
                    "turn_count": 3,
                    "session_summary": "사용자가 슬랙 알림 자동화를 요청했고, Google Sheets 연동 워크플로우를 만들었다.",
                    "workflow": dummy_workflow,
                },
            ),
            timeout=60.0,  # LLM 호출 포함 — 넉넉하게
        )
        ok = r.status_code == 200
        body = r.json()
        _record("update_memory → 200", ok, f"status={r.status_code}")
        _record(
            "update_memory → next_action=complete",
            body.get("next_action") == "complete",
        )
    except Exception as exc:
        _record("update_memory", False, str(exc))


async def test_recall_skills(client: httpx.AsyncClient) -> None:
    print("\n── 4. recall_skills ──────────────────────────────────────────")
    try:
        r = await client.post(
            f"{MODAL_URL}/v1/agent/route",
            json=_build_request(
                "recall_skills",
                {"query": "슬랙 알림 자동화", "limit": 3},
            ),
            timeout=30.0,
        )
        ok = r.status_code == 200
        body = r.json()
        has_key = "recalled_skills" in body.get("state_delta", {})
        _record("recall_skills → 200", ok, f"status={r.status_code}")
        _record("recall_skills → state_delta.recalled_skills 존재", has_key)
        if has_key:
            skills = body["state_delta"]["recalled_skills"]
            _record(
                "recall_skills → list 반환",
                isinstance(skills, list),
                f"len={len(skills)}",
            )
    except Exception as exc:
        _record("recall_skills", False, str(exc))


async def test_cleanup_memory(client: httpx.AsyncClient) -> None:
    print("\n── 5. cleanup_memory ─────────────────────────────────────────")
    try:
        r = await client.post(
            f"{MODAL_URL}/v1/agent/route",
            json=_build_request("cleanup_memory"),
        )
        ok = r.status_code == 200
        body = r.json()
        _record("cleanup_memory → 200", ok, f"status={r.status_code}")
        _record(
            "cleanup_memory → next_action=complete",
            body.get("next_action") == "complete",
        )
    except Exception as exc:
        _record("cleanup_memory", False, str(exc))


async def test_unknown_action(client: httpx.AsyncClient) -> None:
    print("\n── 6. unknown action (400 확인) ──────────────────────────────")
    try:
        r = await client.post(
            f"{MODAL_URL}/v1/agent/route",
            json=_build_request("does_not_exist"),
        )
        _record("unknown action → 400", r.status_code == 400, f"status={r.status_code}")
    except Exception as exc:
        _record("unknown action", False, str(exc))


async def main() -> None:
    if not MODAL_URL:
        print(f"{FAIL} PERSONALIZATION_AGENT_URL 환경변수를 설정하세요 (modal app list → agent-personalization URL)")
        sys.exit(1)

    print(f"대상 URL  : {MODAL_URL}")
    print(f"SESSION_ID: {SESSION_ID}")
    print(f"USER_ID   : {USER_ID}")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        healthy = await check_health(client)
        if not healthy:
            print(f"\n{FAIL} Health check 실패 — 이후 테스트를 건너뜁니다.")
            sys.exit(1)

        await test_load_memory(client)
        await test_update_memory(client)
        await test_recall_skills(client)
        await test_cleanup_memory(client)
        await test_unknown_action(client)

    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    print("\n" + "═" * 56)
    print(f"결과: {passed}/{total} 통과  {'🎉' if failed == 0 else '❌'}")
    if failed:
        print("실패 항목:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  - {name}  {detail}")
    print("═" * 56)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
