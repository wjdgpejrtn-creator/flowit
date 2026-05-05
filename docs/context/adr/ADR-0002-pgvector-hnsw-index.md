# ADR-0002: pgvector HNSW 인덱스 설정 (m=16, ef_construction=64)

- **Status**: Accepted
- **Date**: 2026-05-05
- **Deciders**: @dhwang0803-glitch (REQ-001)
- **Tags**: area/database, layer/infrastructure

## Context

REQ-001 Database 구현에서 BGE-M3 1024차원 벡터 임베딩을 저장하는 테이블이 4개 존재한다:
- `skills` (005_skill_bootstrap.sql)
- `document_blocks` (006_doc_parser.sql)
- `node_definitions` (009_node_definitions.sql)
- `agent_memories` (012_agent_memory.sql)

이 테이블들에서 코사인 유사도 기반 시맨틱 검색을 수행해야 하며, pgvector 확장의 인덱스 전략을 결정해야 했다.

pgvector는 두 가지 ANN 인덱스를 제공한다:
- **IVFFlat**: 빠른 빌드, 데이터 분포에 민감, 대량 데이터에서 recall 저하
- **HNSW**: 빌드 느림, recall 높음, 증분 insert에 강함

## Decision

**모든 벡터 컬럼에 HNSW 인덱스를 적용하고, 파라미터는 `m=16, ef_construction=64`로 통일한다.**

```sql
CREATE INDEX idx_{table}_embedding_hnsw ON {table}
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 파라미터 선택 근거

| 파라미터 | 값 | 의미 |
|---------|---|------|
| `m` | 16 | 그래프 노드당 연결 수. 높을수록 recall↑, 메모리↑ |
| `ef_construction` | 64 | 인덱스 빌드 시 탐색 범위. 높을수록 정확도↑, 빌드 시간↑ |
| `vector_cosine_ops` | - | BGE-M3가 코사인 유사도 기준으로 학습됨 |

MVP 단계 예상 데이터: 노드 54종, 스킬 ~1000건, 문서 블록 ~10K건. `m=16`은 10K~100K 규모에서 recall 95%+ 달성하면서 메모리 오버헤드가 합리적인 수준.

## Consequences

### Positive

- 4개 테이블에서 일관된 검색 성능 보장
- INSERT 시 인덱스 자동 갱신 (IVFFlat 대비 VACUUM 불필요)
- 코사인 유사도 연산자(`<=>`) 사용 시 인덱스 스캔 활용

### Negative / Trade-offs

- 초기 빌드 시간이 IVFFlat 대비 2~3배 소요 (MVP 규모에서는 무시 가능)
- 데이터 100K+ 초과 시 `ef_construction` 상향 검토 필요
- 1024차원 벡터에 대한 메모리 사용량: 노드당 ~65KB (m=16 기준)

### Follow-ups

- [ ] 프로덕션 데이터 100K 초과 시 `m=24, ef_construction=128` 벤치마크
- [ ] `ef_search` 런타임 파라미터 튜닝 (쿼리 시 `SET hnsw.ef_search = 100`)

## Alternatives Considered

- **Option A: IVFFlat (lists=100)** — 빌드 속도 우선. 기각 사유: 54종 노드 시드 데이터에서 list 수 결정 어렵고, 데이터 증가 시 reindex 필수
- **Option B: HNSW (m=32, ef_construction=200)** — 최대 recall. 기각 사유: MVP 규모에서 over-provisioning, 빌드 시간/메모리 불필요하게 증가
- **Option C: 인덱스 없이 순차 스캔** — 기각 사유: 시맨틱 검색이 핵심 기능(REQ-004 Retriever Node)이므로 성능 보장 필수

## References

- pgvector 공식 문서: HNSW 파라미터 가이드
- BGE-M3 모델: 1024차원 dense embedding
- 관련 SQL: `005_skill_bootstrap.sql`, `006_doc_parser.sql`, `009_node_definitions.sql`, `012_agent_memory.sql`
