"""ParseUserDocumentUseCase 단위 테스트 (ADR-0028 T2 `parse_document`).

doc_parser `ParseDocumentUseCase`(application/use_cases)를 얇게 래핑한다 — mime 디스패치 +
정규화 + PII 마스킹 + 품질게이트는 doc_parser 내부에서 수행되고, T2는 그 결과 DocumentBlock만
돌려준다. doc_parser use case Fake로 위임·PII 마스킹된 산출 통과·QualityGateResult 폐기·
unsupported mime 전파를 검증한다(inline 헬퍼, conftest 미사용).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import DocumentBlock
from common_schemas.document import ContentBlock, FileMeta

from ai_agent.application.agents.skills_builder.parse_document_use_case import (
    ParseUserDocumentUseCase,
)


def _file_meta(mime: str = "application/pdf") -> FileMeta:
    return FileMeta(file_name="sop.pdf", file_type="pdf", mime_type=mime, file_size=1024)


def _document(text: str = "환불 처리 SOP") -> DocumentBlock:
    return DocumentBlock(
        document_id=uuid4(),
        file_meta=_file_meta(),
        blocks=[ContentBlock(block_id=uuid4(), block_type="text", content=text)],
    )


class _FakeParseDocument:
    """doc_parser ParseDocumentUseCase 대역 — `.execute()`만 duck-type.

    실제 use case는 (DocumentBlock, QualityGateResult) 튜플을 돌려주고, 본 대역도 동일 계약을
    흉내낸다. quality 자리는 T2가 폐기하므로 sentinel로 둔다.
    """

    def __init__(self, document: DocumentBlock | None = None, raises: Exception | None = None) -> None:
        self._document = document if document is not None else _document()
        self._raises = raises
        self.calls: list[dict] = []
        self.quality_sentinel = object()

    def execute(self, file_path: str, file_meta: FileMeta) -> tuple[DocumentBlock, object]:
        self.calls.append({"file_path": file_path, "file_meta": file_meta})
        if self._raises is not None:
            raise self._raises
        return self._document, self.quality_sentinel


# ----------------------------------------------------------------------
# 위임 + 산출 통과
# ----------------------------------------------------------------------


def test_delegates_to_doc_parser_with_same_args():
    fake = _FakeParseDocument()
    uc = ParseUserDocumentUseCase(fake)
    meta = _file_meta()

    uc.execute("/tmp/sop.pdf", meta)

    assert len(fake.calls) == 1
    assert fake.calls[0]["file_path"] == "/tmp/sop.pdf"
    assert fake.calls[0]["file_meta"] is meta  # FileMeta 그대로 위임(mime 디스패치는 doc_parser 몫)


def test_returns_pii_masked_document_block_from_doc_parser():
    # doc_parser가 PII 마스킹·정규화·품질게이트를 마친 DocumentBlock을 그대로 통과시킨다.
    masked = _document(text="환불 담당자: [MASKED]")
    fake = _FakeParseDocument(document=masked)
    uc = ParseUserDocumentUseCase(fake)

    result = uc.execute("/tmp/sop.pdf", _file_meta())

    assert result is masked
    assert isinstance(result, DocumentBlock)


def test_discards_quality_gate_result():
    # T2 계약(ADR-0028 D1)은 → DocumentBlock. QualityGateResult는 폐기(품질 강제는 호출자/O1 wrap 몫).
    fake = _FakeParseDocument()
    uc = ParseUserDocumentUseCase(fake)

    result = uc.execute("/tmp/sop.pdf", _file_meta())

    assert result is fake._document
    assert result is not fake.quality_sentinel


# ----------------------------------------------------------------------
# 예외 전파
# ----------------------------------------------------------------------


def test_unsupported_mime_propagates_value_error():
    # doc_parser가 미지원 mime에 ValueError(E0201)를 던지면 T2는 삼키지 않고 전파한다
    # (콜러블 툴 — 에이전트 루프 wrap(O1)이 ErrorFrame으로 변환).
    fake = _FakeParseDocument(raises=ValueError("E0201: 지원하지 않는 파일 형식 — image/png"))
    uc = ParseUserDocumentUseCase(fake)

    with pytest.raises(ValueError, match="E0201"):
        uc.execute("/tmp/x.png", _file_meta(mime="image/png"))


def test_parse_failure_propagates():
    fake = _FakeParseDocument(raises=RuntimeError("E0202: 파일 손상"))
    uc = ParseUserDocumentUseCase(fake)

    with pytest.raises(RuntimeError, match="E0202"):
        uc.execute("/tmp/corrupt.pdf", _file_meta())
