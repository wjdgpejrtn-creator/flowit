"""Cloud Run worker entry — dummy HTTP health server + Celery worker subprocess.

Cloud Run service는 startup HTTP probe를 요구하지만 Celery worker는 HTTP 서버가
아니다. 이 모듈은 두 책임을 한 컨테이너에 묶는다:

1. FastAPI uvicorn으로 8080에서 ``GET /health`` serve
2. ``celery -A src._celery_app worker`` subprocess spawn

worker subprocess가 죽으면 ``/health``가 503으로 응답해 Cloud Run이 컨테이너를
재시작한다. lifespan close 시 SIGTERM으로 graceful shutdown.

로컬 dev에서는 본 모듈 대신 ``celery -A src._celery_app worker``를 직접 실행한다.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

logger = logging.getLogger("worker_entry")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

_worker_proc: subprocess.Popen[bytes] | None = None
WORKER_CMD: list[str] = [
    "celery",
    "-A",
    "src._celery_app",
    "worker",
    "--loglevel=info",
    "--concurrency=2",
]


def _spawn_worker() -> subprocess.Popen[bytes]:
    logger.info("Spawning celery worker: %s", " ".join(WORKER_CMD))
    return subprocess.Popen(WORKER_CMD)  # noqa: S603 — fixed command


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
    return Response(status_code=200, content=f"ok pid={_worker_proc.pid}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # noqa: S104
    # subprocess가 main 종료 시 잔존하면 Cloud Run이 회수. 안전망:
    if _worker_proc and _worker_proc.poll() is None:
        _worker_proc.terminate()
        sys.exit(0)
