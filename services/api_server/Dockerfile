FROM python:3.11-slim AS base

WORKDIR /app

COPY packages/common_schemas/python /app/packages/common_schemas/python
COPY modules /app/modules
COPY services/api_server /app/services/api_server

RUN pip install --no-cache-dir \
    -e /app/packages/common_schemas/python \
    -e /app/services/api_server

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
