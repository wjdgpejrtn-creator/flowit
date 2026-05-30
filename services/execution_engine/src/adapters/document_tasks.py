"""REQ-006/009 — Documents 분석 Celery task.

api_server `POST /api/v1/documents/{id}/analyze`가 dispatch한 task. 흐름:

    1. document_id로 PgDocumentRepository.get_by_id → file_meta + user_id 확보
    2. GCS download (`documents/{id}/{filename}`) → 로컬 tmpfile
    3. ParsingPipeline.execute(path, file_meta) → (parsed DocumentBlock, chunks, quality)
    4. PgDocumentRepository.save(parsed) — UPSERT(merge)로 blocks 채움 + user_id 보존
    5. save_chunks + save_quality_log
    6. tmpfile cleanup

Sync celery task 내부에서 `asyncio.run`으로 async I/O(GCS + AsyncSession). Cross-loop
함정 회피: connector/engine을 매 task call마다 fresh 생성 + finally에서 dispose
(container `_build_credential_service_factory` 패턴과 동일).
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from celery import shared_task
from common_schemas import AnalysisStatus
from common_schemas.broker_tasks import TASK_ANALYZE_DOCUMENT

logger = logging.getLogger(__name__)

# analysis_error 컬럼은 TEXT라 길이 제한 없지만, 운영 로그/UI 표시 안정성 위해 잘라 저장.
_ERROR_MSG_MAX_LEN = 1000


@shared_task(
    name=TASK_ANALYZE_DOCUMENT,
    bind=True,
    max_retries=0,
    acks_late=True,
)
def analyze_document_task(self, document_id: str) -> dict:
    """document_id의 GCS 파일을 다운로드 → 파싱 → DB UPSERT."""
    try:
        return asyncio.run(_analyze(UUID(document_id)))
    except Exception as exc:
        # DomainError vs system error를 worker 측에서 구분하지 않는다 (분석 실패는 모두 task ERROR)
        # — 실패 회복은 운영 측 재시도 정책으로(현재 max_retries=0이라 1회로 한정).
        logger.exception("analyze_document_task failed: document_id=%s", document_id)
        return {"document_id": document_id, "status": "error", "error": str(exc)}


async def _analyze(document_id: UUID) -> dict:
    from google.cloud.sql.connector import IPTypes, create_async_connector
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from storage.adapters.gcs_adapter import GCSAdapter
    from storage.repositories.pg_document_repository import PgDocumentRepository

    instance = os.getenv("CLOUD_SQL_INSTANCE")
    iam_user = os.getenv("DB_IAM_USER")
    db_name = os.getenv("DB_NAME")
    bucket = os.getenv("DOCUMENTS_BUCKET")
    if not (instance and iam_user and db_name and bucket):
        raise RuntimeError(
            "analyze_document_task는 CLOUD_SQL_INSTANCE / DB_IAM_USER / DB_NAME / "
            "DOCUMENTS_BUCKET 환경변수를 요구한다 (Cloud SQL IAM auth + GCS)."
        )

    object_storage = GCSAdapter(bucket_name=bucket)
    connector = await create_async_connector()

    async def getconn():
        return await connector.connect_async(
            instance,
            "asyncpg",
            user=iam_user,
            db=db_name,
            enable_iam_auth=True,
            ip_type=IPTypes.PUBLIC,
        )

    engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn, poolclass=NullPool)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # 1. 메타 조회 + analysis_status="running" 표기 (atomic).
        async with session_factory() as session:
            repo = PgDocumentRepository(session)
            document = await repo.get_by_id(document_id)
            if document is None:
                return {"document_id": str(document_id), "status": "not_found"}
            file_meta = document.file_meta
            original_user_id = document.user_id
            running = document.model_copy(update={
                "analysis_status": AnalysisStatus.RUNNING,
                "analysis_error": None,
            })
            await repo.save(running)
            await session.commit()

        try:
            # 2. GCS download → tmpfile
            key = f"documents/{document_id}/{file_meta.file_name}"
            payload = await object_storage.download(key)
            suffix = Path(file_meta.file_name).suffix
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(payload)
                tmp_path = tmp.name

            try:
                # 3. ParsingPipeline (sync)
                pipeline = _build_pipeline()
                parsed_doc, chunks, quality = pipeline.execute(tmp_path, file_meta)

                # 4. 결과 영속화 — UPSERT로 blocks 채움 + status="completed" + analyzed_at 갱신.
                result = parsed_doc.model_copy(update={
                    "document_id": document_id,
                    "user_id": original_user_id,
                    "analysis_status": AnalysisStatus.COMPLETED,
                    "analysis_error": None,
                    "analyzed_at": datetime.now(UTC),
                    "coverage": quality.coverage,  # QualityGate 산출 커버리지를 문서에 실어 노출
                })
                # 청크의 parent_document_id를 실제 document_id로 remap. 파이프라인은 파싱 시
                # masked_document에 자체 uuid를 부여하고 ChunkingService가 그 id를
                # parent_document_id로 박는다. document는 위에서 실제 document_id로 갱신하지만
                # 청크를 그대로 두면 parent_document_id가 파싱 시점 uuid를 가리켜
                # document_chunks_parent_document_id_fkey FK 위반(documents에 없음)이 난다.
                chunks = [c.model_copy(update={"parent_document_id": document_id}) for c in chunks]
                async with session_factory() as session:
                    save_repo = PgDocumentRepository(session)
                    await save_repo.save(result)
                    if chunks:
                        await save_repo.save_chunks(chunks)
                    await save_repo.save_quality_log(quality, document_id)
                    await session.commit()

                return {
                    "document_id": str(document_id),
                    "status": "completed",
                    "block_count": len(result.blocks),
                    "chunk_count": len(chunks),
                    "quality_status": quality.quality_status,
                }
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as exc:
            # 실패 상태 기록 — blocks는 이전 상태 보존(덮어쓰지 않음). 프론트가 폴링으로 인지.
            await _mark_failed(session_factory, document_id, exc)
            raise
    finally:
        await engine.dispose()
        await connector.close_async()


async def _mark_failed(session_factory, document_id: UUID, exc: BaseException) -> None:
    """분석 실패 시 documents row에 status=failed + error를 기록.

    blocks/parser_meta는 그대로 두고 상태 컬럼만 갱신. 기록 자체가 실패해도 task는 정상
    예외 전파(상위 try가 dict 반환) — 가용성 우선.
    """
    from storage.repositories.pg_document_repository import PgDocumentRepository

    try:
        async with session_factory() as session:
            fail_repo = PgDocumentRepository(session)
            current = await fail_repo.get_by_id(document_id)
            if current is None:
                return
            failed = current.model_copy(update={
                "analysis_status": AnalysisStatus.FAILED,
                "analysis_error": str(exc)[:_ERROR_MSG_MAX_LEN],
            })
            await fail_repo.save(failed)
            await session.commit()
    except Exception:
        logger.exception("analyze_document_task: failed-state 기록 실패 document_id=%s", document_id)


def _build_vision_llm():
    """Vision(InterleavingParser) 활성 시 ParserFactory에 주입할 LLM 클라이언트.

    doc_parser `VisionExtractor`는 `llm.generate.remote(prompt, images=[data_url])`로
    llm-base(Gemma 4 멀티모달) Modal RPC를 호출한다. 따라서 llm은 llm-base Modal Cls의
    **인스턴스**여야 한다(`modal.Cls.from_name("llm-base", "LLMBase")()`).

    안전 기본값 = None(텍스트 전용, 현 동작). 아래 env가 모두 갖춰질 때만 vision을 켠다:
      - DOC_PARSER_VISION_ENABLED = "true"|"1"|"yes"
      - MODAL_TOKEN_ID + MODAL_TOKEN_SECRET (Modal RPC 인증 — Cloud Run worker에 secret 주입 필요)
      - (선택) LLM_BASE_MODAL_APP / LLM_BASE_MODAL_CLS 로 앱/클래스명 override
    설정 누락·클라이언트 생성 실패 시 경고 로그 + None으로 degrade(분석은 텍스트로 계속).

    ⚠️ 이 seam만으로는 vision이 켜지지 않는다 — 워커에 Modal 토큰 secret 주입(infra) +
    DOC_PARSER_VISION_ENABLED 설정이 선행돼야 한다. docs/guides/worker-vision-enable.md 참조.
    """
    flag = os.getenv("DOC_PARSER_VISION_ENABLED", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return None
    if not (os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET")):
        logger.warning(
            "DOC_PARSER_VISION_ENABLED=on이나 MODAL_TOKEN_ID/SECRET 미설정 — "
            "vision 비활성(텍스트 전용)으로 degrade"
        )
        return None
    try:
        import modal

        app_name = os.getenv("LLM_BASE_MODAL_APP", "llm-base")
        cls_name = os.getenv("LLM_BASE_MODAL_CLS", "LLMBase")
        llm = modal.Cls.from_name(app_name, cls_name)()
        logger.info("vision LLM 활성 — Modal RPC %s/%s", app_name, cls_name)
        return llm
    except Exception:
        logger.exception("vision LLM 클라이언트 생성 실패 — vision 비활성(텍스트 전용)으로 degrade")
        return None


def _build_pipeline():
    """ParsingPipeline 조립 — 매 task call마다 fresh build.

    `_build_vision_llm()`이 None이면 텍스트 전용(현 동작), Modal LLM 인스턴스를 반환하면
    ParserFactory가 PDF/HWPX/PPTX를 InterleavingParser(VisionExtractor)로 래핑해 vision 활성.
    """
    from doc_parser.adapters.config.yaml_config_loader import YamlConfigLoader
    from doc_parser.adapters.parser_factory import ParserFactory
    from doc_parser.adapters.parsers.csv_parser import CsvParser
    from doc_parser.adapters.parsers.docx_parser import DocxParser
    from doc_parser.adapters.parsers.hwp_parser import HwpParser
    from doc_parser.adapters.parsers.hwpx_parser import HwpxParser
    from doc_parser.adapters.parsers.markdown_parser import MarkdownParser
    from doc_parser.adapters.parsers.pdf_parser import PdfParser
    from doc_parser.adapters.parsers.pptx_parser import PptxParser
    from doc_parser.adapters.parsers.xlsx_parser import XlsxParser
    from doc_parser.application.use_cases import ParsingPipeline
    from doc_parser.domain.services.chunking_service import ChunkingService
    from doc_parser.domain.services.normalization import NormalizationService
    from doc_parser.domain.services.pii_masking import PIIMaskingService
    from doc_parser.domain.services.quality_gate import QualityGate

    factory = ParserFactory(llm=_build_vision_llm())
    for parser in (
        PdfParser(),
        DocxParser(),
        XlsxParser(),
        CsvParser(),
        MarkdownParser(),
        PptxParser(),
        HwpParser(),
        HwpxParser(),
    ):
        factory.register(parser)

    return ParsingPipeline(
        parser_factory=factory,
        normalization_service=NormalizationService(),
        pii_masking_service=PIIMaskingService(),
        quality_gate=QualityGate(),
        chunking_service=ChunkingService(config={}),
        config_loader=YamlConfigLoader(),
    )
