from __future__ import annotations

import os

from celery import Celery
from kombu import Queue

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "execution_engine",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "execution_engine.execute_workflow": {"queue": "default"},
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

celery_app.autodiscover_tasks(["execution_engine.src.adapters"])
