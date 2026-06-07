"""라이브 캡처 러너 — 실 composer를 골든셋으로 1회 돌려 스냅샷을 만든다.

⚠️ 실 스택 필요: Modal LLM/Embedder + Neo4j AuraDB + Cloud SQL(노드 카탈로그).
   check_snapshot/test_metrics와 달리 이 파일만 네트워크에 붙는다. 무거운 import는
   전부 함수 안에 둔다(패키지 import-safe 유지).

조립은 services/agents/agent-composer/main.py(boot + route)를 미러한다. 로컬에서는
Modal Cloud SQL connector 대신 `DATABASE_URL`(cloud-sql-proxy, staging_node_catalog_reseed
레시피 — port 6544 ssl=False)로 세션을 만든다.

실행(로컬, cloud-sql-proxy 띄운 상태):
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    PYTHONPATH="modules:packages/common_schemas/python" \
    DATABASE_URL="postgresql+asyncpg://USER@127.0.0.1:6544/DB" \
    LLM_BASE_URL=... EMBEDDING_BASE_URL=... \
    NEO4J_URI=... NEO4J_USERNAME=... NEO4J_PASSWORD=... \
    python -m ai_agent.tests.eval.ontology_grounding.run_eval --label baseline-pgvector

캡처 후 check_snapshot로 집계를 보고, 만족스러우면 snapshots/composer_grounding.json을
snapshots/baseline.json(집계 dict)으로 승격한다(--promote-baseline).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas.transport import (
    ErrorFrame,
    QAMetricFrame,
    ResultFrame,
    WorkflowDraftFrame,
)

from .records import UNKNOWN_NODE_TYPE, RunRecord, Snapshot, save_snapshot
from .scenarios import SCENARIOS, Scenario

# ── 세션/조립 (main.py 미러) ──────────────────────────────────────────────────


async def _create_session_factory():
    """로컬 DATABASE_URL 우선, 없으면 Modal Cloud SQL connector 경로."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    db_url = os.getenv("DATABASE_URL")
    if db_url:
        engine = create_async_engine(db_url, poolclass=NullPool)
        return None, engine, async_sessionmaker(engine, expire_on_commit=False)

    # Modal 환경 fallback (main.py._create_session와 동일)
    from google.cloud.sql.connector import IPTypes, create_async_connector

    connector = await create_async_connector()

    async def getconn():
        return await connector.connect_async(
            os.environ["CLOUD_SQL_INSTANCE"], "asyncpg",
            user=os.environ["DB_IAM_USER"], db=os.environ["DB_NAME"],
            enable_iam_auth=True, ip_type=IPTypes.PUBLIC,
        )

    engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn, poolclass=NullPool)
    return connector, engine, async_sessionmaker(engine, expire_on_commit=False)


def _build_orchestrator(session, ontology_retriever):
    """main.py route 엔드포인트의 조립을 미러. 평가용으로 GCS 영속 store는 None(선택 의존)."""
    from nodes_graph.domain.services.graph_validator import GraphValidator
    from skills_marketplace.application.use_cases.search_skills_use_case import SearchSkillsUseCase
    from storage.repositories.pg_marketplace_skill_repository import PgMarketplaceSkillRepository
    from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository
    from storage.repositories.pg_oauth_repository import PgOAuthRepository
    from storage.repositories.pg_workflow_repository import PgWorkflowRepository

    from ai_agent.adapters.connection_resolver_adapter import OAuthConnectionResolver
    from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
    from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
    from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
    from ai_agent.adapters.node_registry_adapter import NodeRegistryAdapter
    from ai_agent.domain.services.drafter_service import DrafterService
    from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService
    from ai_agent.domain.services.qa_evaluator_service import QAEvaluatorService
    from ai_agent.domain.services.slot_filling_service import SlotFillingService

    llm = ModalLLMAdapter()
    embedder = ModalEmbeddingAdapter()
    node_repo = PgNodeDefinitionRepository(session)
    orchestrator = LangGraphOrchestrator(
        intent_analyzer=IntentAnalyzerService(llm),
        drafter=DrafterService(llm),
        qa_evaluator=QAEvaluatorService(llm),
        slot_filler=SlotFillingService(),
        node_registry=NodeRegistryAdapter(node_repo, embedder),
        workflow_repo=PgWorkflowRepository(session),
        graph_validator=GraphValidator(node_repo),
        session_frame_store=None,
        llm=llm,
        workflow_draft_store=None,
        execution_engine_url=os.getenv("EXECUTION_ENGINE_URL", ""),
        personal_memory_store=None,
        skill_search=SearchSkillsUseCase(repo=PgMarketplaceSkillRepository(session)),
        embedder=embedder,
        composer_state_store=None,
        connection_resolver=OAuthConnectionResolver(PgOAuthRepository(session)),
        ontology_retriever=ontology_retriever,
    )
    return orchestrator, node_repo


# ── 프레임 → RunRecord ────────────────────────────────────────────────────────


def _frames_to_record(scenario: Scenario, frames: list, node_type_by_id: dict[UUID, str]) -> RunRecord:
    """수집 프레임 + 카탈로그 맵으로 RunRecord 정규화."""
    last_draft: WorkflowDraftFrame | None = None
    last_qa: QAMetricFrame | None = None
    result: ResultFrame | None = None
    error_msg: str | None = None
    for f in frames:
        if isinstance(f, WorkflowDraftFrame):
            last_draft = f
        elif isinstance(f, QAMetricFrame):
            last_qa = f
        elif isinstance(f, ResultFrame):
            result = f
        elif isinstance(f, ErrorFrame):
            error_msg = f.message

    node_types: list[str] = []
    edges: list[tuple[int, int]] = []
    produced = last_draft is not None or (result is not None and result.payload.get("workflow_id"))

    if last_draft is not None:
        idx_by_instance: dict[str, int] = {}
        for i, n in enumerate(last_draft.nodes):
            nid = n.get("node_id")
            try:
                node_type = node_type_by_id.get(UUID(str(nid)), UNKNOWN_NODE_TYPE)
            except (ValueError, TypeError):
                node_type = UNKNOWN_NODE_TYPE
            node_types.append(node_type)
            inst = n.get("instance_id")
            if inst is not None:
                idx_by_instance[str(inst)] = i
        for c in last_draft.connections:
            a = idx_by_instance.get(str(c.get("from_instance_id")))
            b = idx_by_instance.get(str(c.get("to_instance_id")))
            if a is not None and b is not None:
                edges.append((a, b))

    attempt = last_qa.attempt if last_qa else 0
    qa_score = last_qa.score if last_qa else 0.0
    retry_count = max(0, attempt - 1)

    return RunRecord(
        scenario_id=scenario.scenario_id,
        utterance=scenario.utterance,
        expected_motif=scenario.expected_motif,
        distractor=scenario.distractor,
        produced_workflow=bool(produced),
        node_types=node_types,
        edges=edges,
        validator_passed_first=(retry_count == 0 and bool(produced)),
        retry_count=retry_count,
        qa_score=qa_score,
        error=error_msg,
        meta={
            "intent": result.intent if result else None,
            "qa_attempt": attempt,
            "n_nodes": len(node_types),
            "n_edges": len(edges),
        },
    )


async def _capture_one(orchestrator, scenario: Scenario, node_type_by_id: dict[UUID, str]) -> RunRecord:
    frames: list = []
    try:
        async for frame in await orchestrator.stream(
            user_id=uuid4(), session_id=uuid4(), message=scenario.utterance, round=1,
        ):
            frames.append(frame)
    except Exception as exc:  # noqa: BLE001 — 캡처는 어떤 실패도 레코드로 남긴다
        return RunRecord(
            scenario_id=scenario.scenario_id, utterance=scenario.utterance,
            expected_motif=scenario.expected_motif, distractor=scenario.distractor,
            produced_workflow=False, node_types=[], edges=[],
            validator_passed_first=False, retry_count=0, qa_score=0.0,
            error=f"stream 예외: {exc}",
        )
    return _frames_to_record(scenario, frames, node_type_by_id)


async def run(label: str) -> Snapshot:
    from ai_agent.adapters.ontology.neo4j_ontology_adapter import Neo4jOntologyAdapter

    connector, engine, session_factory = await _create_session_factory()
    ontology_retriever = Neo4jOntologyAdapter()
    records: list[RunRecord] = []
    try:
        async with session_factory() as session:
            orchestrator, node_repo = _build_orchestrator(session, ontology_retriever)
            defs = await node_repo.list_all()
            node_type_by_id = {d.node_id: d.node_type for d in defs}
            print(f"카탈로그 {len(node_type_by_id)}종 로드. 시나리오 {len(SCENARIOS)}건 캡처 시작…")
            for i, sc in enumerate(SCENARIOS, 1):
                rec = await _capture_one(orchestrator, sc, node_type_by_id)
                flag = "✗" if rec.error else ("∅" if not rec.produced_workflow else "✓")
                print(f"  [{i:>2}/{len(SCENARIOS)}] {flag} {sc.scenario_id} "
                      f"(노드 {len(rec.node_types)}, retry {rec.retry_count}, qa {rec.qa_score})")
                records.append(rec)
    finally:
        await engine.dispose()
        if connector is not None:
            await connector.close_async()

    return Snapshot(
        label=label,
        captured_at=datetime.now(UTC).isoformat(),
        records=records,
    )


def _promote_baseline() -> int:
    """현재 스냅샷 집계를 baseline.json으로 승격."""
    import json

    from .metrics import aggregate
    from .records import BASELINE_FILE, load_snapshot

    snap = load_snapshot()
    if snap is None:
        print("[FAIL] 승격할 스냅샷 없음 — run_eval를 먼저 실행하세요.")
        return 1
    agg = aggregate(snap.records)
    BASELINE_FILE.write_text(json.dumps(agg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"베이스라인 승격 완료 → {BASELINE_FILE}\n{agg.as_table()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="온톨로지 그라운딩 라이브 캡처")
    parser.add_argument("--label", default="capture", help="스냅샷 라벨(예: baseline-pgvector)")
    parser.add_argument("--promote-baseline", action="store_true",
                        help="캡처 대신 현재 스냅샷 집계를 baseline.json으로 승격")
    args = parser.parse_args()

    if args.promote_baseline:
        return _promote_baseline()

    snap = asyncio.run(run(args.label))
    path = save_snapshot(snap)
    print(f"\n스냅샷 저장 → {path} ({len(snap.records)}건)")
    print("이어서 점검: python -m ai_agent.tests.eval.ontology_grounding.check_snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
