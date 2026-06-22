"""온톨로지 GraphRAG 그라운딩 평가 하니스 (ADR-0026 §6.5).

composer의 노드 그라운딩/모티프 품질을 **결정적으로 before/after 측정**하기 위한
하니스. `/rag-personalization-check`(BGE-M3 스냅샷 점검)의 패턴을 미러링한다:

  scenarios.py     골든 요청셋(정답지 포함)
  metrics.py       순수 지표 추출기(네트워크/DB 불필요)
  records.py       스냅샷 row 스키마(RunRecord) + 로드/세이브
  run_eval.py      라이브 캡처 러너 — 실 composer를 골든셋으로 1회 돌려 스냅샷 생성
  check_snapshot.py 결정적 게이트 — 스냅샷 집계 + 베이스라인 회귀 판정
  snapshots/       캡처 산출물(JSON)

핵심 분리: **지표 계산은 순수/결정적**(metrics.py, test_metrics.py로 검증)이고,
**라이브 캡처만 실 스택**(Modal LLM + Neo4j + DB)을 필요로 한다. A1(CAN_FOLLOW)
적용 전후로 run_eval를 떠서 check_snapshot로 회귀를 본다.
"""
