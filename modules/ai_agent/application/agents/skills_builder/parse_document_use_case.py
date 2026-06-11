from __future__ import annotations

from common_schemas.document import DocumentBlock, FileMeta
from doc_parser.application.use_cases import ParseDocumentUseCase

# 스킬빌더 T2 `parse_document` use case (ADR-0028 D1, 빌드순서 — 콜러블 툴).
#
# 업로드 파일(file_path + FileMeta) → DocumentBlock. doc_parser(REQ-006)의 `ParseDocumentUseCase`
# (application/use_cases)를 얇게 래핑한다 — mime 디스패치 + 정규화 + **PII 마스킹** + 품질게이트가
# 전부 doc_parser 내부에서 수행되므로 재구현 0. T3(extract_metadata)에 먹일 깨끗한 DocumentBlock을
# 돌려준다. 에이전트 루프(T1~T5 tool-calling) wrap은 O1(프레임 결정) 후 — 본 use case는 콜러블 툴.
#
# 크로스모듈 의존(ADR-0028 O7): ai_agent → doc_parser.application.use_cases.ParseDocumentUseCase.
# CLAUDE.md "modules 간 허용 import" 표에 등재(skills_marketplace use case 교차 import와 동일 선례).
# 원시 ParserPort 대신 use case를 래핑하는 이유 = PII 마스킹/정규화/품질게이트 파이프라인을 그대로
# 재사용해 SOP 문서의 개인정보가 LLM 추출로 새는 보안 회귀를 차단한다.


class ParseUserDocumentUseCase:
    """업로드 문서를 파싱해 DocumentBlock을 돌려준다 (스킬빌더 T2 `parse_document`).

    doc_parser `ParseDocumentUseCase`에 위임하고, 그 산출 튜플 `(DocumentBlock, QualityGateResult)`
    중 **DocumentBlock만** 통과시킨다(ADR-0028 D1 계약 = → DocumentBlock). QualityGateResult는
    폐기한다 — 품질 강제(저품질 파싱 거부)는 본 콜러블 툴의 책임이 아니라 호출자/에이전트 루프(O1)의
    정책 결정이며, doc_parser가 이미 정규화·PII 마스킹·품질게이트를 내부에서 수행한 결과다.

    파싱 실패(미지원 mime `E0201`, 손상 `E0202`, 추출 실패 `E0203` 등)는 삼키지 않고 그대로
    전파한다 — 에이전트 루프 wrap이 ErrorFrame으로 변환한다.
    """

    def __init__(self, parse_document: ParseDocumentUseCase) -> None:
        self._parse_document = parse_document

    def execute(self, file_path: str, file_meta: FileMeta) -> DocumentBlock:
        """`file_path`의 문서를 파싱해 정규화·PII 마스킹된 DocumentBlock 반환.

        Args:
            file_path: 파싱할 파일 경로(업로드 임시 경로 등).
            file_meta: 파일 메타데이터 — `mime_type`으로 doc_parser가 파서를 디스패치한다.

        Returns:
            정규화 + PII 마스킹 + 품질게이트를 거친 DocumentBlock. T3(extract_metadata) 입력.

        Raises:
            ValueError: 지원하지 않는 MIME 타입(E0201) — doc_parser에서 전파.
            Exception: 파일 손상/추출 실패 등 파서 예외 — 그대로 전파.
        """
        document, _quality_result = self._parse_document.execute(file_path, file_meta)
        return document
