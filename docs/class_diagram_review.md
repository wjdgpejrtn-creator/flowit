# 클래스 다이어그램 교차 정적분석 보고서

- **분석일**: 2026-05-04
- **분석자**: 황대원
- **대상**: 12개 REQ 클래스 다이어그램 (class_diagram/ 폴더)

---

## 분석 범위

| REQ | 담당 | 형식 | 클래스 수 (추정) |
|-----|------|------|-----------------|
| 001 Database | 황대원 | .drawio | 32+ |
| 002 Auth-Security | 박아름 | .drawio | 28 |
| 003 Nodes-Graph | 박아름 | .drawio | 26 |
| 004 AI Agent | 신정혜 | .png (편집 불가) | ~30 |
| 005 Toolset | 햄햄 | .png (편집 불가) | ~15 |
| 006 doc-parser | 김진형 | .drawio (3개 파일) | 27 |
| 007 Execution Engine | 황대원 | .drawio | 21 |
| 008 Storage | 황대원 | .drawio | 19 |
| 009 API Server | 황대원 | .drawio | 27 |
| 010 Frontend | 황대원 | .drawio | 33 |
| 011 Infra | 황대원 | .drawio | 30 |
| 012 Common Schemas | 황대원 | .drawio | 30 |

---

## HIGH — 반드시 수정 필요

### H-1. WorkflowSchema / NodeInstance / Edge 중복 정의 (REQ-003 vs REQ-012)

REQ-012가 SSOT(Single Source of Truth)로 이 3개 타입을 정의하고 있으나, REQ-003도 독자적으로 재정의함.

| 필드 | REQ-003 | REQ-012 | 불일치 |
|------|---------|---------|-------|
| `NodeInstance.instance_id` | `str` | `UUID` | 타입 다름 |
| `NodeInstance.position` | `dict` | `Position` (별도 VO) | 타입 다름 |
| `WorkflowSchema.description` | 있음 | 없음 | 필드 유무 |

**조치**: REQ-003은 REQ-012를 참조(import)하는 것으로 변경. 자체 정의 삭제. 필요 시 REQ-012에 description 필드 추가 논의.

---

### H-2. 암호화 클래스 중복 + 시그니처 불일치 (REQ-001 vs REQ-002)

| 항목 | REQ-001 | REQ-002 |
|------|---------|---------|
| 추상 클래스명 | `EncryptionStrategy` | `BaseCipher` |
| encrypt 시그니처 | `encrypt(plaintext: bytes): bytes` | `encrypt(plaintext: str): bytes` |
| decrypt 시그니처 | `decrypt(ciphertext: bytes): bytes` | `decrypt(ciphertext: bytes): str` |
| AES 구현체명 | `AesGcmCipher` | `AESGCMCipher` |
| Fernet 구현체명 | `FernetCipher` | `FernetCipher` |

같은 목적(AES-GCM + Fernet)인데 파라미터 타입이 다름 (bytes vs str).

**조치**: 단일 소유 REQ 결정 필요. REQ-002(Auth-Security)가 cipher를 소유하고, REQ-001은 REQ-002의 cipher를 의존성 주입받는 구조로 통일 권장.

---

### H-3. Repository ABC ↔ 구현체 메서드 시그니처 불일치

REQ-002가 ABC(인터페이스)를, REQ-001이 구현체를 담당하는 구조인데, 메서드가 전혀 맞지 않음.

#### SessionRepository

| REQ-002 ABC 정의 | REQ-001 구현체 |
|------------------|---------------|
| `create(user_id, hash) → Session` | `create_session(user_id, kind) → ChatSessionModel` |
| `find_by_hash(hash) → Session` | `load(session_id) → ChatSessionModel` |
| `revoke(session_id) → None` | `flush(session_id) → None` |
| `revoke_all_for_user(user_id) → int` | (없음) |

#### OAuthConnectionRepository

| REQ-002 ABC 정의 | REQ-001 구현체 |
|------------------|---------------|
| `create(user_id, service, tokens) → Conn` | `upsert(connection) → None` |
| `get_by_credential_id(cid) → Conn` | (없음) |
| `get_active_for_user(user_id, service) → Conn` | `list(user_id) → list` |
| `update_tokens(cid, new_tokens) → None` | `refresh(connection_id) → None` |
| `revoke(cid) → None` | `disconnect(connection_id) → None` |

**조치**: REQ-001(황대원)과 REQ-002(박아름) 담당자가 합의하여 인터페이스 계약을 통일해야 함. ABC 정의를 기준으로 구현체를 맞추거나, 양쪽 합의 후 통일.

---

### H-4. NodeDefinitionRepository 메서드 불일치 (REQ-002 vs REQ-003)

REQ-002의 `CredentialInjectionService`가 필요한 메서드:
- `get_service_type(node_id) → str`
- `get_required_connections(node_id) → list`
- `get_risk_level(node_id) → str`

REQ-003이 정의한 `NodeDefinitionRepository` ABC:
- `upsert(definition) → None`
- `list_all(mvp_only) → list`
- `get_by_id(node_id) → NodeDefinition`
- `search_by_embedding(query, limit) → list`

REQ-002가 필요한 3개 메서드가 REQ-003 ABC에 **없음**. `get_by_id` 후 객체에서 추출할 수도 있지만, REQ-002는 별도 메서드로 정의함.

**조치**: REQ-003 NodeDefinitionRepository ABC에 REQ-002 필요 메서드 추가하거나, `get_by_id` 반환값인 `NodeDefinition`에 해당 필드가 있음을 명시.

---

### H-5. 파일 형식 문제 (REQ-004, 005)

| 파일 | 문제 |
|------|------|
| `REQ-004_Class다이어그램.drawio.png..png` | 확장자 이중 오류 + PNG(편집 불가) |
| `REQ-005_Class 다이어그램.drawio.png` | PNG(편집 불가) + 파일명 공백 |

draw.io에서 편집하려면 `.drawio` XML 원본이 필요.

**조치**: 신정혜, 햄햄에게 `.drawio` 원본 파일 요청. 파일명 컨벤션 통일: `REQ-XXX-모듈명.drawio`

---

### H-6. DocumentBlock 중복 정의 + 심각한 필드 불일치 (REQ-006 vs REQ-012)

REQ-006과 REQ-012 모두 `DocumentBlock`을 정의하지만 필드가 크게 다름.

| 필드 | REQ-006 | REQ-012 | 불일치 |
|------|---------|---------|-------|
| `document_id` | `str` | `UUID` | 타입 다름 |
| `workflow_id` | `str` | (없음) | REQ-012에 누락 |
| `user_id` | `str` | (없음) | REQ-012에 누락 |
| `parser` | `ParserMeta` (객체) | `str` | 타입 완전히 다름 (객체 vs 문자열) |
| `blocks` | `list[Block]` | `list[ContentBlock]` | 하위 클래스명 다름 |

**조치**: REQ-012가 SSOT이므로 REQ-006의 상세 필드를 REQ-012에 반영하거나, REQ-006이 REQ-012를 import하고 확장하는 구조로 합의 필요. `workflow_id`, `user_id`는 REQ-006 파서 파이프라인에 필요한 컨텍스트이므로 REQ-012에 추가 논의.

---

### H-7. FileMeta 중복 정의 + 필드 불일치 (REQ-006 vs REQ-012)

| 필드 | REQ-006 | REQ-012 | 불일치 |
|------|---------|---------|-------|
| `file_name` | ✅ | ✅ | 동일 |
| `file_type` | ✅ | ✅ | 동일 |
| `file_size` | ✅ | ✅ | 동일 |
| `page_count` | `int` | (없음) | REQ-012에 누락 |
| `unit_type` | `str` | (없음) | REQ-012에 누락 |
| `created_at` | `Optional[str]` | (없음) | REQ-012에 누락 |
| `author` | `Optional[str]` | (없음) | REQ-012에 누락 |
| `sheet_meta` | `Optional[list[SheetMeta]]` | (없음) | REQ-012에 누락 |
| `mime_type` | (없음) | `str` | REQ-006에 누락 |

REQ-006이 8필드, REQ-012가 4필드로 REQ-012가 지나치게 간소함.

**조치**: REQ-012 FileMeta를 REQ-006 수준으로 확장하고, REQ-006에 `mime_type` 추가. REQ-012가 SSOT, REQ-006은 import.

---

### H-8. Block vs ContentBlock 구조 불일치 (REQ-006 vs REQ-012)

같은 역할(문서 블록 단위)이나 클래스명과 필드 구조가 다름.

| 필드 | REQ-006 `Block` | REQ-012 `ContentBlock` | 불일치 |
|------|----------------|----------------------|-------|
| `block_id` | `str` | `str` | 동일 |
| `block_type` | `str` | `Literal["text","table","image","heading"]` | REQ-012가 더 엄격 |
| `text` | `Optional[str]` | → `content: str` | 필드명 다름 (text vs content) |
| `table` | `Optional[list[list[Any]]]` | (없음) | REQ-012에 누락 |
| `page` | `int` | (없음) | REQ-012에 누락 |
| `section_title` | `Optional[str]` | (없음) | REQ-012에 누락 |
| `bbox` | `Optional[BBox]` | (없음) | REQ-012에 누락 |
| `source_ref` | `Optional[SourceRef]` | `dict` | 타입 다름 (VO vs dict) |
| `token_estimate` | (없음) | `int` | REQ-006에 누락 |
| `importance_score` | (없음) | `float` | REQ-006에 누락 (※ Chunk에는 존재) |

**조치**: 클래스명을 통일(Block 또는 ContentBlock)하고 필드를 병합. REQ-012의 `source_ref: dict`를 REQ-006의 `SourceRef` VO로 교체. `token_estimate`, `importance_score`는 파싱 후 AI 단계에서 채워지는 필드이므로 Optional로 통합.

---

## MEDIUM — 확인/개선 권장

### M-1. REQ-009 DAGScheduler 명칭 혼동

REQ-007을 DAG → LangGraph StateGraph로 전환했으나, REQ-009에 `DAGScheduler`(Kahn topological sort)가 잔존. REQ-009의 DAGScheduler는 워크플로우 노드 실행 순서 결정용(execution order)으로 LangGraph 실행 엔진과는 별개이나, "DAG" 명칭이 혼동 유발 가능.

**조치**: `WorkflowOrderScheduler` 또는 `TopologicalScheduler`로 개명 고려.

---

### M-2. AgentState 이중 정의 가능성 (REQ-004 vs REQ-012)

- REQ-012: `AgentState` 정의 — messages, draft_spec, intent_result, node_candidates, workflow_draft, mode
- REQ-004 (PNG에서 확인): Layer 1에 `AgentState` 클래스 존재 — 필드가 다를 수 있음

**조치**: REQ-004의 AgentState가 REQ-012를 참조하는지 확인 필요 (PNG라 정확한 필드 확인 불가 → .drawio 원본 확보 후 재검증)

---

### M-3. REQ-005 다이어그램 해상도 심각 저하

PNG 해상도가 낮아 클래스명·메서드·타입이 거의 읽히지 않음. REQ-003 `ToolToNodeWrapper`가 REQ-005 `BaseTool`을 참조하는데 인터페이스 검증 불가.

**조치**: 고해상도 PNG 또는 .drawio 원본 필요.

---

### M-4. REQ-006 QualityGateResult vs REQ-012 AnalysisResult 관계 — **해소됨**

XML 원본 확인 결과 **별개 타입**으로 확정:

- `QualityGateResult` (REQ-006): 파서 품질 게이트 결과 — quality_status, metrics(QualityMetrics), warnings, error_codes, decision_reason. 파서 출력물의 **품질 점수/통과 여부** 판정.
- `AnalysisResult` (REQ-012): AI 분석 결과 — document_title, category, summary, key_points, confidence, source_refs, questions, prompt_version. LLM이 문서를 분석한 **내용적 결과**.

파이프라인 순서: 파서 → `QualityGateResult`(통과 여부) → AI 분석 → `AnalysisResult`.
두 타입은 목적이 다르며 중복이 아님. **추가 조치 불요.**

---

### M-5. REQ-004 vs REQ-007 LangGraph 사용 경계 불명확

- REQ-004 Layer 3: LangGraph StateGraph (AI Agent 내부 오케스트레이션)
- REQ-007: LangGraph StateGraph + Celery 2-Tier (워크플로우 실행 엔진)

둘 다 LangGraph를 쓰지만 목적이 다름.

**조치**: REQ-004는 "AI Agent 내부 그래프" (Consultant/Composer 흐름), REQ-007은 "워크플로우 실행 그래프" (사용자 정의 워크플로우 실행)로 역할 명확히 문서화.

---

### M-6. SourceRef 정의 불일치 (REQ-006 vs REQ-012)

- REQ-006: `SourceRef`를 풍부한 Pydantic 모델로 정의 (page, section, block_index, bbox, sheet_name, slide_number). `※ REQ-012 보류` 주석 부착.
- REQ-012: `ContentBlock.source_ref: dict`, `AnalysisResult.source_refs: list[dict]` — 타입이 `dict`로 미정의.

REQ-006이 상세하게 정의했으나 REQ-012가 아직 `dict`로만 선언하여 계약이 맞지 않음.

**조치**: REQ-012가 REQ-006의 `SourceRef`를 SSOT로 채택하여 `dict` → `SourceRef` VO로 교체. 김진형(REQ-006) + 황대원(REQ-012) 합의.

---

### M-7. Chunk.importance_score 크로스 모듈 의존성 (REQ-006 → REQ-004)

REQ-006 `Chunk` 클래스에 `importance_score: Optional[float]`이 존재하며, `※ REQ-004 담당` 주석 부착. 파서가 청크를 생성할 때는 None이고, REQ-004 AI Agent가 이후 채워주는 구조.

이 크로스 모듈 데이터 흐름이 문서화되어 있지 않음.

**조치**: REQ-004(신정혜)에게 importance_score 계산 시점·로직을 확인하고, 데이터 흐름을 architecture 문서에 반영.

---

## LOW — 참고사항

### L-1. 파일명 컨벤션 불통일

| 현재 | 권장 |
|------|------|
| `REQ-004_Class다이어그램.drawio.png..png` | `REQ-004-AI-Agent.drawio` |
| `REQ-005_Class 다이어그램.drawio.png` | `REQ-005-Toolset.drawio` |
| `REQ-006_Data_Class.drawio.png` (3개) | `REQ-006-DocParser.drawio` (통합) |
| `REQ-001-Database.drawio` | OK |
| `REQ-002.drawio` | `REQ-002-Auth-Security.drawio` (모듈명 추가 권장) |
| `REQ-003.drawio` | `REQ-003-Nodes-Graph.drawio` (모듈명 추가 권장) |

### L-2. REQ-006 파일 3개 분리

Data_Class, Parser_Engine, Service_Layer로 3개 분리. 다른 REQ는 단일 파일. draw.io 멀티탭으로 통합 가능.

### L-3. 색상 범례

REQ-002, 003은 자체 범례 포함 (좋음). 팀 전체 색상 통일은 필수 아님, 개별 범례만 있으면 충분.

---

## 조치 우선순위

| 순위 | 이슈 | 관련 담당자 | 비고 |
|------|------|------------|------|
| 1 | H-3 Repository 메서드 통일 | 황대원 + 박아름 | 코딩 전 필수 합의 |
| 2 | H-6 DocumentBlock 중복 정의 통일 | 김진형 + 황대원 | REQ-006 vs REQ-012, 필드 심각 불일치 |
| 3 | H-7 FileMeta 필드 통일 | 김진형 + 황대원 | REQ-012에 REQ-006 필드 반영 |
| 4 | H-8 Block vs ContentBlock 통일 | 김진형 + 황대원 | 클래스명·필드 병합 |
| 5 | H-1 공유 타입 중복 제거 | 박아름 (REQ-003 수정) | REQ-012 SSOT 준수 |
| 6 | H-2 Cipher 단일 소유 | 황대원 + 박아름 | 시그니처 통일 |
| 7 | H-4 NodeDefRepo 메서드 추가 | 박아름 (REQ-003 수정) | REQ-002 필요 메서드 |
| 8 | H-5 .drawio 원본 요청 | 신정혜, 햄햄 | 편집 가능 형식 |
| 9 | M-6 SourceRef SSOT 합의 | 김진형 + 황대원 | REQ-012 dict → VO 교체 |
| 10 | M-7 importance_score 흐름 문서화 | 신정혜 (REQ-004) | 크로스 모듈 의존성 |
| 11 | M-1, M-2, M-3, M-5 | 각 담당자 | 코딩 착수 후 순차 |
| — | ~~M-4~~ | — | 해소됨 (별개 타입 확정) |
