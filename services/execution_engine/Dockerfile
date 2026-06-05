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

# auth + storage — ADR-0018 Phase 2b: credential_id가 있는 노드 실행 시
# CatalogNodeExecutor가 CredentialInjectionService(auth) + Pg*Repository(storage)로
# 자격증명을 해결한다. nodes_graph와 동일 패턴 — pip install -e는 의존성 설치용
# (auth: cryptography / storage: asyncpg·sqlalchemy[asyncio]·cloud-sql-connector[asyncpg]),
# 패키지 import는 아래 PYTHONPATH /app/modules로 해결한다.
COPY modules/auth /app/modules/auth
RUN pip install --no-cache-dir -e /app/modules/auth
COPY modules/storage /app/modules/storage
RUN pip install --no-cache-dir -e /app/modules/storage

# skills_marketplace — REQ-013 런타임 주입: CatalogNodeExecutor가 LLM 노드 실행 시 바인딩된
# SkillDocument 지침서를 GcsSkillDocumentStore(storage.adapters)로 load해 system 프롬프트에
# 주입한다. container._build_skill_document_store()가 SKILLS_MARKETPLACE_BUCKET env set 시
# storage.adapters.gcs_skill_document_store(→ skills_marketplace.domain.ports)를 import하므로
# worker에도 필요. 누락 시 create_container()가 ModuleNotFoundError('skills_marketplace')로
# 죽어 **모든 워크플로우 실행이 row조차 못 남기고 크래시**한다. flat layout(setuptools find +
# PYTHONPATH /app/modules)로 import 해결, pip install -e는 deps(common_schemas/pydantic 기설치) 정합용.
COPY modules/skills_marketplace /app/modules/skills_marketplace
RUN pip install --no-cache-dir -e /app/modules/skills_marketplace

# doc_parser — REQ-006/009: analyze_document_task가 ParsingPipeline(7종 파서)로 문서를
# 파싱하고, PgDocumentRepository도 doc_parser.domain.ports를 import한다. nodes_graph와 동일
# flat layout — pip install -e는 파서 의존성(pymupdf/pdfplumber/python-docx/openpyxl/
# python-pptx/pyhwp+beautifulsoup4/lxml/markdown-it-py) 설치용, 패키지 import는 아래
# PYTHONPATH /app/modules로 해결. (2026-05-29 worker analyze ModuleNotFound(doc_parser) 사고)
COPY modules/doc_parser /app/modules/doc_parser
RUN pip install --no-cache-dir -e /app/modules/doc_parser

# execution_engine 본 패키지 + 의존성 (celery, redis, sqlalchemy, pg8000)
COPY services/execution_engine /app/services/execution_engine
RUN pip install --no-cache-dir -e /app/services/execution_engine[worker]

# 워커는 services/execution_engine을 CWD로 잡아 `src.*` import 일관.
# /app/modules는 nodes_graph 패키지 import 경로 (flat layout — 위 주석 참조).
WORKDIR /app/services/execution_engine
ENV PYTHONPATH=/app/services/execution_engine:/app/modules

EXPOSE 8080

CMD ["python", "-m", "src.worker_entry"]
