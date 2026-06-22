/**
 * localStorage 키 공유 상수.
 *
 * 동일 문자열을 여러 페이지에서 인라인 정의하면 한쪽만 변경 시 다른 쪽이
 * stale 데이터를 읽는 drift 위험이 있어 단일 모듈로 추출한다. (PR #216 리뷰)
 */

/** 업로드된 문서 목록 (documents 페이지 ↔ 스킬빌더 문서 선택 공유) */
export const DOCS_STORAGE_KEY = 'wf_documents_list';
