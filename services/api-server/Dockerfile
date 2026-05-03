FROM python:3.11-slim AS base

WORKDIR /app

COPY packages/common-schemas/python /app/packages/common-schemas/python
COPY modules /app/modules
COPY services/api-server /app/services/api-server

RUN pip install --no-cache-dir \
    -e /app/packages/common-schemas/python \
    -e /app/services/api-server

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
