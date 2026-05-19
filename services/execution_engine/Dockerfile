FROM python:3.12-slim AS base

# Cloud Run worker: long-running Celery worker + dummy HTTP server (worker_entry).
# Cloud Run service는 startup HTTP probe를 요구하므로 worker_entry가 8080에서
# /health를 serve하는 동안 background subprocess로 celery worker를 띄운다.
#
# CLAUDE.md (Python 3.12 통일) + [[modal_deploy_quirks]] PYTHONPATH 패턴.

WORKDIR /app

# common_schemas — 직접 import (editable install)
COPY packages/common_schemas/python /app/packages/common_schemas/python
RUN pip install --no-cache-dir -e /app/packages/common_schemas/python

# execution_engine 본 패키지 + 의존성 (celery, redis, sqlalchemy, asyncpg, langgraph)
COPY services/execution_engine /app/services/execution_engine
RUN pip install --no-cache-dir -e /app/services/execution_engine[worker]

# 워커는 services/execution_engine을 CWD로 잡아 `src.*` import 일관
WORKDIR /app/services/execution_engine
ENV PYTHONPATH=/app/services/execution_engine

EXPOSE 8080

CMD ["python", "-m", "src.worker_entry"]
