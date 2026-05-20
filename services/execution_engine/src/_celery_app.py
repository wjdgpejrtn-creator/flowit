from __future__ import annotations

import os
import ssl

from celery import Celery
from kombu import Queue

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "execution_engine",
    broker=redis_url,
    backend=redis_url,
)

# Memorystore SERVER_AUTHENTICATION cert가 컨테이너 trust store에 없음 → cert verify skip.
# TLS encryption은 유지. production은 server-ca-cert image COPY로 강화 권장.
_tls_ssl_opts: dict = {"ssl_cert_reqs": ssl.CERT_NONE} if redis_url.startswith("rediss://") else {}

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_use_ssl=_tls_ssl_opts,
    redis_backend_use_ssl=_tls_ssl_opts,
    task_routes={
        "execution_engine.execute_workflow": {"queue": "default"},
        "execution_engine.cancel_execution": {"queue": "default"},
        "execution_engine.resume_execution": {"queue": "default"},
        "execution_engine.execute_node": {"queue": "default"},
        "execution_engine.handle_handoff": {"queue": "default"},
        "execution_engine.level_callback": {"queue": "default"},
    },
    task_queues=[
        Queue("default", routing_key="workflow.node.default"),
        Queue("llm", routing_key="workflow.node.llm"),
        Queue("external_api", routing_key="workflow.node.external"),
    ],
)

# Task 등록 — task 정의는 src/adapters/celery_tasks.py.
# autodiscover_tasks의 기본 related_name='tasks'라 파일명(celery_tasks)과 mismatch였고,
# 패키지 경로도 "execution_engine.src.adapters"는 setuptools가 `src` 패키지로 등록하는 것과 어긋남.
# 단일 모듈 명시 import로 확정 — import 시점에 @shared_task 데코레이터가 task를 등록한다.
from .adapters import celery_tasks as _celery_tasks  # noqa: E402,F401
