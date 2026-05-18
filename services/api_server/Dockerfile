FROM python:3.12-slim AS base

WORKDIR /app

COPY packages/common_schemas/python /app/packages/common_schemas/python
COPY modules /app/modules
COPY services/api_server /app/services/api_server

RUN pip install --no-cache-dir \
    -e /app/packages/common_schemas/python \
    -e /app/modules/auth \
    -e /app/modules/nodes_graph \
    -e /app/modules/storage \
    -e /app/modules/doc_parser \
    -e /app/modules/toolset \
    -e /app/services/api_server

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
