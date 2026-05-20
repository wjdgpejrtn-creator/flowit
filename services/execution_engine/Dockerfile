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

# nodes_graph — CatalogNodeExecutor가 get_all_node_classes()로 53종 노드 클래스를
# import (ADR-0018). pip install -e는 의존성(httpx/fpdf2 — http_request·pdf_generate
# process 구현분)만 설치한다. nodes_graph는 flat layout(디렉토리 자체가 패키지)이라
# setuptools find()가 패키지를 매핑하지 못하므로, import는 아래 PYTHONPATH의
# /app/modules로 해결한다 (services/execution_engine을 src.*로 import하는 것과 동일 방식).
COPY modules/nodes_graph /app/modules/nodes_graph
RUN pip install --no-cache-dir -e /app/modules/nodes_graph

# execution_engine 본 패키지 + 의존성 (celery, redis, sqlalchemy, pg8000)
COPY services/execution_engine /app/services/execution_engine
RUN pip install --no-cache-dir -e /app/services/execution_engine[worker]

# 워커는 services/execution_engine을 CWD로 잡아 `src.*` import 일관.
# /app/modules는 nodes_graph 패키지 import 경로 (flat layout — 위 주석 참조).
WORKDIR /app/services/execution_engine
ENV PYTHONPATH=/app/services/execution_engine:/app/modules

EXPOSE 8080

CMD ["python", "-m", "src.worker_entry"]
