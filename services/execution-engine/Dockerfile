FROM python:3.11-slim AS base

WORKDIR /app

COPY packages/common-schemas/python /app/packages/common-schemas/python
COPY modules /app/modules
COPY services/execution-engine /app/services/execution-engine

RUN pip install --no-cache-dir \
    -e /app/packages/common-schemas/python \
    -e /app/services/execution-engine

CMD ["celery", "-A", "src.worker", "worker", "--loglevel=info"]
