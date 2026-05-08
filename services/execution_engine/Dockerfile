FROM python:3.11-slim AS base

WORKDIR /app

COPY packages/common_schemas/python /app/packages/common_schemas/python
COPY modules /app/modules
COPY services/execution_engine /app/services/execution_engine

RUN pip install --no-cache-dir \
    -e /app/packages/common_schemas/python \
    -e /app/services/execution_engine

CMD ["celery", "-A", "src.worker", "worker", "--loglevel=info"]
