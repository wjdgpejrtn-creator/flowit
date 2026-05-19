"""Cloud Run worker entry — dummy HTTP health server + Celery worker subprocess.

Cloud Run service는 startup HTTP probe를 요구하지만 Celery worker는 HTTP 서버가
아니다. 이 모듈은 두 책임을 한 컨테이너에 묶는다:

1. FastAPI uvicorn으로 ``$PORT``(default 8080)에서 ``GET /health`` serve
2. ``celery -A src._celery_app worker`` subprocess spawn

worker subprocess가 죽으면 ``/health``가 503으로 응답해 Cloud Run이 컨테이너를
재시작한다. 추가로 broker 연결 상태도 검증해 false-healthy(프로세스는 살아있지만
Redis 연결 실패로 task pickup 못 함) 케이스를 잡는다.

환경 변수:

- ``PORT`` — uvicorn listen port (default ``8080``)
- ``CELERY_CONCURRENCY`` — worker concurrency (default ``2``)
- ``CELERY_QUEUES`` — listen queue names (CSV, default ``default``)
- ``HEALTH_BROKER_PING`` — ``"1"``이면 ``/health``에서 broker ping 추가 (default ``"1"``)

로컬 dev에서는 본 모듈 대신 ``celery -A src._celery_app worker``를 직접 실행한다.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

logger = logging.getLogger("worker_entry")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

_worker_proc: subprocess.Popen[bytes] | None = None


def _build_worker_cmd() -> list[str]:
    concurrency = os.getenv("CELERY_CONCURRENCY", "2")
    queues = os.getenv("CELERY_QUEUES", "default")
    return [
        "celery",
        "-A",
        "src._celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={concurrency}",
        f"--queues={queues}",
    ]


def _spawn_worker() -> subprocess.Popen[bytes]:
    cmd = _build_worker_cmd()
    logger.info("Spawning celery worker: %s", " ".join(cmd))
    return subprocess.Popen(cmd)  # noqa: S603 — env-configured fixed args


def _broker_alive(timeout_s: float = 2.0) -> bool:
    """Celery control plane ping — broker 연결 + worker ready 동시 검증.

    프로세스는 살아있지만 broker 접속 실패 / 첫 ready 전이면 False.
    timeout 내 응답 못 받으면 False (idle worker가 잠시 응답 못 할 수 있어 보수적).
    """
    try:
        from src._celery_app import celery_app
    except Exception as exc:  # pragma: no cover — boot-time import error
        logger.warning("celery_app import 실패: %s", exc)
        return False

    try:
        replies = celery_app.control.inspect(timeout=timeout_s).ping()
        return bool(replies)
    except Exception as exc:
        logger.warning("broker ping 실패: %s", exc)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global _worker_proc
    _worker_proc = _spawn_worker()
    try:
        yield
    finally:
        if _worker_proc and _worker_proc.poll() is None:
            logger.info("Sending SIGTERM to celery worker pid=%s", _worker_proc.pid)
            _worker_proc.send_signal(signal.SIGTERM)
            try:
                _worker_proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                logger.warning("Worker did not exit in 30s — sending SIGKILL")
                _worker_proc.kill()


app = FastAPI(title="execution_engine_worker", lifespan=lifespan)


@app.get("/health")
def health() -> Response:
    if _worker_proc is None:
        return Response(status_code=503, content="worker not started")
    rc = _worker_proc.poll()
    if rc is not None:
        return Response(status_code=503, content=f"worker exited rc={rc}")
    if os.getenv("HEALTH_BROKER_PING", "1") == "1" and not _broker_alive():
        return Response(status_code=503, content=f"worker pid={_worker_proc.pid} but broker not reachable")
    return Response(status_code=200, content=f"ok pid={_worker_proc.pid}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # noqa: S104
