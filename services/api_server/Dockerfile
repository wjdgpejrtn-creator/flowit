FROM python:3.12-slim AS base

# Cloud Run service: FastAPI uvicorn (factory mode). Cloud Run v2 startup probe가
# container_port=8080 에서 응답해야 함 — terraform `module.api_server.container_port`와 일치.
#
# api_server는 modules 6종(auth/ai_agent/nodes_graph/storage/doc_parser/toolset)을
# 직접 또는 transitively import. setuptools editable install로 의존 resolution 자동.
#
# CLAUDE.md (Python 3.12 통일) + PR-B 정상화 패턴 따름.

WORKDIR /app

# 1) common_schemas — 모든 modules + services의 SSOT 의존 (먼저 install)
COPY packages/common_schemas/python /app/packages/common_schemas/python
RUN pip install --no-cache-dir -e /app/packages/common_schemas/python

# 2) modules — api_server가 사용하는 4종(auth/ai_agent/nodes_graph/storage) + storage가
#    transitively import하는 doc_parser/toolset domain ports까지 install. setuptools가
#    inter-module 의존 (auth.domain → nodes_graph.domain 등) 자동 resolution.
COPY modules /app/modules
RUN pip install --no-cache-dir \
    -e /app/modules/auth \
    -e /app/modules/ai_agent \
    -e /app/modules/nodes_graph \
    -e /app/modules/doc_parser \
    -e /app/modules/toolset \
    -e /app/modules/storage

# 3) api_server 본 패키지 + 의존성 (fastapi, uvicorn, jose, sqlalchemy, asyncpg, sse-starlette)
COPY services/api_server /app/services/api_server
RUN pip install --no-cache-dir -e /app/services/api_server

WORKDIR /app/services/api_server
ENV PYTHONPATH=/app/services/api_server

EXPOSE 8080

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
