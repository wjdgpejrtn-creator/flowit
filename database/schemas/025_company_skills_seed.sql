-- 025_company_skills_seed.sql
-- ecommerce 워크플로우 5종 seed (회사 초기 세팅, ADR-0020 company_skills 자동 PUBLISHED).
-- author_id=시스템 유저(00000000-…-0001). node_id는 node_type 서브쿼리로 환경 독립 해결.
-- credential은 워크플로우 미포함 — 실행 시 CatalogNodeExecutor 주입(ADR-0018 Phase 2b).
-- 출처: 외부 Claude Skills 50선 — description에 원본 표기.
-- ADR-0011: ON CONFLICT DO NOTHING 멱등 + schema_migrations 추적 대상.
--
-- ┌─ SSOT 정합 수정(2026-06-04, 리뷰 반영) ─────────────────────────────┐
-- │ 1) scope: 'company' → 'public'                                        │
-- │    이유: 001_core.sql CHECK (scope IN ('private','team','public')).   │
-- │    'company'는 허용값 아님 → INSERT 시 CHECK 위반 → 트랜잭션 롤백.    │
-- │    'public'=전사 공개. ('company' 개념은 company_skills 테이블 존재   │
-- │     자체로 표현됨. 워크플로우 가시범위는 public이 맞음.)              │
-- │ 2) NodeInstance.instance_id: 'n1' → UUID 리터럴(고정).               │
-- │    이유: common_schemas workflow.py NodeInstance.instance_id: UUID.   │
-- │    'n1'(React Flow 표기)은 model_validate ValidationError → 읽기 500. │
-- │    고정 UUID 사용 = 재실행 멱등 유지(gen_random_uuid()면 멱등 깨짐).  │
-- │ 3) connections: {source,target} → Edge 4필드.                        │
-- │    Edge = {from_instance_id:UUID, to_instance_id:UUID,                │
-- │           from_handle:str, to_handle:str}. (branch 필드는 없음)       │
-- │ 4) if_condition 분기: Edge.from_handle='true'로 표현(별도 키 아님).   │
-- └──────────────────────────────────────────────────────────────────────┘
--
-- 설계 메모:
--   (A) parameters 키 = node_definitions.input_schema 속성명과 13종 전수 일치 확인됨.
--       실행 슬롯(required 중 미충원: http_request.url, regex_extract.{text,pattern},
--       postgresql_query.query, gmail_send.{to,subject,body}, pdf_generate.{title,sections} 등)은
--       의도적으로 비움 — 워크플로우 생성 시 Main Agent(LLM)가 채우고 사용자에게 변경 안내하는 설계.
--       seed에 정적 default 박지 말 것.
--   (B) from_handle/to_handle = 'output'/'input'(if 분기는 'true'). TopologicalScheduler가
--       from_instance_id/to_instance_id만 사용하고 핸들은 무시 → 로드/검증/위상정렬 무해.
--       (단 같은 이유로 if 분기는 엔진이 현재 강제 안 함 — 핸들 타입 메타 도입 시 유효. REQ-007 별건.)
-- ⚠️ 선행 의존: workflows.user_id → users(user_id) FK.
--   author/user_id = 시스템 유저(…0001)가 users에 존재해야 함(system_user.sql 선행 적용).

BEGIN;

-- 인스턴스 ID 규약(가독성): c1111111-0000-4000-8000-0000000000{WF}{NODE}
--   WF=워크플로우번호(1~5), NODE=노드순번(1~4). 예: WF1 n2 = …012.

-- ── workflows (노드 그래프; nodes/connections JSONB) ──

-- #1 마케팅 이메일 (manual → gemma → template → gmail)
INSERT INTO workflows (workflow_id, user_id, name, description, scope, is_draft, nodes, connections, version) VALUES (
  'b1111111-0000-4000-8000-000000000001', '00000000-0000-0000-0000-000000000001', '마케팅 이메일 자동 작성·발송', '캠페인 맥락(제품·타깃·목표)을 입력하면 베스트프랙티스 기반 마케팅 이메일을 생성해 발송. 제목줄·세그먼트·라이프사이클 원칙 반영. (원본: Email Marketing Bible)', 'public', FALSE,
  jsonb_build_array(
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000011','node_id',(SELECT node_id FROM node_definitions WHERE node_type='manual_trigger'),'parameters','{}'::jsonb,'position',jsonb_build_object('x',100,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000012','node_id',(SELECT node_id FROM node_definitions WHERE node_type='gemma_chat'),'parameters','{"prompt": "당신은 이메일 마케팅 전문가입니다. 제목줄 30자 내외·호기심/이득 명확·스팸 단어 회피, 본문 첫 문장에 핵심 가치·단일 CTA·짧은 단락, 톤은 타깃 맞춤·과장 금지. 아래 캠페인 맥락에 맞춰 마케팅 이메일을 작성하세요. 출력 JSON: {subject, body}. 캠페인 맥락:", "response_format": "json", "temperature": 0.7, "max_tokens": 1024}'::jsonb,'position',jsonb_build_object('x',340,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000013','node_id',(SELECT node_id FROM node_definitions WHERE node_type='text_template'),'parameters','{"template": "{body}\n\n──────────────\n본 메일은 마케팅 수신 동의자에게 발송됩니다.\n수신거부: {unsubscribe_url}", "variables": {}}'::jsonb,'position',jsonb_build_object('x',580,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000014','node_id',(SELECT node_id FROM node_definitions WHERE node_type='gmail_send'),'parameters','{"is_html": false}'::jsonb,'position',jsonb_build_object('x',820,'y',200))
  ),
  '[{"from_instance_id":"c1111111-0000-4000-8000-000000000011","to_instance_id":"c1111111-0000-4000-8000-000000000012","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000012","to_instance_id":"c1111111-0000-4000-8000-000000000013","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000013","to_instance_id":"c1111111-0000-4000-8000-000000000014","from_handle":"output","to_handle":"input"}]'::jsonb, 1
) ON CONFLICT (workflow_id) DO NOTHING;

-- #2 GEO/SEO 리포트 (manual → http → anthropic → pdf)
INSERT INTO workflows (workflow_id, user_id, name, description, scope, is_draft, nodes, connections, version) VALUES (
  'b1111111-0000-4000-8000-000000000002', '00000000-0000-0000-0000-000000000001', 'GEO/SEO 분석 리포트 생성', '대상 페이지 URL을 입력하면 콘텐츠를 수집해 AI 검색 최적화(GEO) 관점에서 citability·구조·스키마를 분석하고 PDF 리포트로 산출. (원본: GEO/SEO Claude)', 'public', FALSE,
  jsonb_build_array(
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000021','node_id',(SELECT node_id FROM node_definitions WHERE node_type='manual_trigger'),'parameters','{}'::jsonb,'position',jsonb_build_object('x',100,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000022','node_id',(SELECT node_id FROM node_definitions WHERE node_type='http_request'),'parameters','{"method": "GET", "timeout": 30.0}'::jsonb,'position',jsonb_build_object('x',340,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000023','node_id',(SELECT node_id FROM node_definitions WHERE node_type='anthropic_chat'),'parameters','{"model": "claude-sonnet-4", "system": "당신은 GEO(생성형 엔진 최적화)·SEO 전문가입니다. 주어진 페이지 콘텐츠를 분석해 citability 점수, 제목/헤딩 구조, 스키마 마크업 유무, 개선 권고 5가지를 평가하세요. 출력은 섹션별 markdown.", "messages": [], "max_tokens": 2048, "temperature": 0.3}'::jsonb,'position',jsonb_build_object('x',580,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000024','node_id',(SELECT node_id FROM node_definitions WHERE node_type='pdf_generate'),'parameters','{"font_size": 12, "margin": 10}'::jsonb,'position',jsonb_build_object('x',820,'y',200))
  ),
  '[{"from_instance_id":"c1111111-0000-4000-8000-000000000021","to_instance_id":"c1111111-0000-4000-8000-000000000022","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000022","to_instance_id":"c1111111-0000-4000-8000-000000000023","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000023","to_instance_id":"c1111111-0000-4000-8000-000000000024","from_handle":"output","to_handle":"input"}]'::jsonb, 1
) ON CONFLICT (workflow_id) DO NOTHING;

-- #3 근거 기반 응대 (webhook → gemma → if_condition → slack) ※ if 분기는 from_handle='true'
INSERT INTO workflows (workflow_id, user_id, name, description, scope, is_draft, nodes, connections, version) VALUES (
  'b1111111-0000-4000-8000-000000000003', '00000000-0000-0000-0000-000000000001', '근거 기반 고객 문의 응대', '고객 문의가 웹훅으로 들어오면 근거 기반(sycophancy 회피)으로 답변을 생성하고, 에스컬레이션이 필요하면 담당 채널로 Slack 알림. (원본: Evidence-Based Dialogue)', 'public', FALSE,
  jsonb_build_array(
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000031','node_id',(SELECT node_id FROM node_definitions WHERE node_type='webhook_trigger'),'parameters','{"method": "POST"}'::jsonb,'position',jsonb_build_object('x',100,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000032','node_id',(SELECT node_id FROM node_definitions WHERE node_type='gemma_chat'),'parameters','{"prompt": "당신은 근거 기반 고객 지원 상담원입니다. 추측이나 비위 맞추기를 금지하고, 확실한 근거가 있을 때만 단정하세요. 근거가 부족하면 확인 필요로 표시하세요. 출력 JSON: {answer, confidence, needs_escalation}. 고객 문의:", "response_format": "json", "temperature": 0.2, "max_tokens": 1024}'::jsonb,'position',jsonb_build_object('x',340,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000033','node_id',(SELECT node_id FROM node_definitions WHERE node_type='if_condition'),'parameters','{"operator": "eq", "right": true}'::jsonb,'position',jsonb_build_object('x',580,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000034','node_id',(SELECT node_id FROM node_definitions WHERE node_type='slack_notify'),'parameters','{"username": "CS-Bot", "icon_emoji": ":sos:"}'::jsonb,'position',jsonb_build_object('x',820,'y',200))
  ),
  '[{"from_instance_id":"c1111111-0000-4000-8000-000000000031","to_instance_id":"c1111111-0000-4000-8000-000000000032","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000032","to_instance_id":"c1111111-0000-4000-8000-000000000033","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000033","to_instance_id":"c1111111-0000-4000-8000-000000000034","from_handle":"true","to_handle":"input"}]'::jsonb, 1
) ON CONFLICT (workflow_id) DO NOTHING;

-- #4 정기 수집·적재 (schedule → http → regex → postgresql)
INSERT INTO workflows (workflow_id, user_id, name, description, scope, is_draft, nodes, connections, version) VALUES (
  'b1111111-0000-4000-8000-000000000004', '00000000-0000-0000-0000-000000000001', '정기 웹 데이터 수집·적재', 'Cron 스케줄에 따라 대상 URL을 수집하고 정규식으로 값을 추출해 PostgreSQL에 적재. 모니터링/가격추적 등 정기 수집 자동화. (원본: Web Scraper)', 'public', FALSE,
  jsonb_build_array(
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000041','node_id',(SELECT node_id FROM node_definitions WHERE node_type='schedule_trigger'),'parameters','{"cron": "0 9 * * *", "timezone": "Asia/Seoul"}'::jsonb,'position',jsonb_build_object('x',100,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000042','node_id',(SELECT node_id FROM node_definitions WHERE node_type='http_request'),'parameters','{"method": "GET", "timeout": 30.0}'::jsonb,'position',jsonb_build_object('x',340,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000043','node_id',(SELECT node_id FROM node_definitions WHERE node_type='regex_extract'),'parameters','{"ignore_case": false, "multiline": true}'::jsonb,'position',jsonb_build_object('x',580,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000044','node_id',(SELECT node_id FROM node_definitions WHERE node_type='postgresql_query'),'parameters','{"fetch_mode": "none", "timeout_seconds": 30.0}'::jsonb,'position',jsonb_build_object('x',820,'y',200))
  ),
  '[{"from_instance_id":"c1111111-0000-4000-8000-000000000041","to_instance_id":"c1111111-0000-4000-8000-000000000042","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000042","to_instance_id":"c1111111-0000-4000-8000-000000000043","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000043","to_instance_id":"c1111111-0000-4000-8000-000000000044","from_handle":"output","to_handle":"input"}]'::jsonb, 1
) ON CONFLICT (workflow_id) DO NOTHING;

-- #5 딥 리서치 (manual → http → anthropic → pdf)
INSERT INTO workflows (workflow_id, user_id, name, description, scope, is_draft, nodes, connections, version) VALUES (
  'b1111111-0000-4000-8000-000000000005', '00000000-0000-0000-0000-000000000001', '딥 리서치 리포트 생성', '리서치 주제를 입력하면 외부 검색 API로 소스를 수집하고 다단계로 분석·종합해 출처가 달린 PDF 리포트로 산출. (원본: Deep Research Engine)', 'public', FALSE,
  jsonb_build_array(
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000051','node_id',(SELECT node_id FROM node_definitions WHERE node_type='manual_trigger'),'parameters','{}'::jsonb,'position',jsonb_build_object('x',100,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000052','node_id',(SELECT node_id FROM node_definitions WHERE node_type='http_request'),'parameters','{"method": "GET", "timeout": 30.0}'::jsonb,'position',jsonb_build_object('x',340,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000053','node_id',(SELECT node_id FROM node_definitions WHERE node_type='anthropic_chat'),'parameters','{"model": "claude-sonnet-4", "system": "당신은 리서치 애널리스트입니다. 검색 결과를 바탕으로 핵심 발견 3~5개, 각 발견의 근거 소스 명시, 상충 정보 표기, 한계·추가조사 항목을 정리하세요. 추측과 사실을 구분하고 모든 주장에 출처를 답니다. 출력은 섹션별 markdown.", "messages": [], "max_tokens": 4096, "temperature": 0.3}'::jsonb,'position',jsonb_build_object('x',580,'y',200)),
    jsonb_build_object('instance_id','c1111111-0000-4000-8000-000000000054','node_id',(SELECT node_id FROM node_definitions WHERE node_type='pdf_generate'),'parameters','{"font_size": 12, "margin": 10}'::jsonb,'position',jsonb_build_object('x',820,'y',200))
  ),
  '[{"from_instance_id":"c1111111-0000-4000-8000-000000000051","to_instance_id":"c1111111-0000-4000-8000-000000000052","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000052","to_instance_id":"c1111111-0000-4000-8000-000000000053","from_handle":"output","to_handle":"input"},
    {"from_instance_id":"c1111111-0000-4000-8000-000000000053","to_instance_id":"c1111111-0000-4000-8000-000000000054","from_handle":"output","to_handle":"input"}]'::jsonb, 1
) ON CONFLICT (workflow_id) DO NOTHING;

-- ── company_skills (PUBLISHED seed) ── (컬럼/lifecycle_state='published'/참조 모두 정합 확인됨)
INSERT INTO company_skills (skill_id, author_id, name, description, lifecycle_state, workflow_id, tags, staging_category, staging_risk_level, staging_required_connections) VALUES (
  'a1111111-0000-4000-8000-000000000001', '00000000-0000-0000-0000-000000000001', '마케팅 이메일 자동 작성·발송', '캠페인 맥락(제품·타깃·목표)을 입력하면 베스트프랙티스 기반 마케팅 이메일을 생성해 발송. 제목줄·세그먼트·라이프사이클 원칙 반영. (원본: Email Marketing Bible)', 'published', 'b1111111-0000-4000-8000-000000000001',
  '["marketing", "email", "ecommerce"]'::jsonb, 'marketing', 'High', '["google"]'::jsonb
) ON CONFLICT (skill_id) DO NOTHING;

INSERT INTO company_skills (skill_id, author_id, name, description, lifecycle_state, workflow_id, tags, staging_category, staging_risk_level, staging_required_connections) VALUES (
  'a1111111-0000-4000-8000-000000000002', '00000000-0000-0000-0000-000000000001', 'GEO/SEO 분석 리포트 생성', '대상 페이지 URL을 입력하면 콘텐츠를 수집해 AI 검색 최적화(GEO) 관점에서 citability·구조·스키마를 분석하고 PDF 리포트로 산출. (원본: GEO/SEO Claude)', 'published', 'b1111111-0000-4000-8000-000000000002',
  '["marketing", "seo", "geo", "ecommerce"]'::jsonb, 'marketing', 'Medium', '["anthropic"]'::jsonb
) ON CONFLICT (skill_id) DO NOTHING;

INSERT INTO company_skills (skill_id, author_id, name, description, lifecycle_state, workflow_id, tags, staging_category, staging_risk_level, staging_required_connections) VALUES (
  'a1111111-0000-4000-8000-000000000003', '00000000-0000-0000-0000-000000000001', '근거 기반 고객 문의 응대', '고객 문의가 웹훅으로 들어오면 근거 기반(sycophancy 회피)으로 답변을 생성하고, 에스컬레이션이 필요하면 담당 채널로 Slack 알림. (원본: Evidence-Based Dialogue)', 'published', 'b1111111-0000-4000-8000-000000000003',
  '["customer_support", "dialogue", "ecommerce"]'::jsonb, 'customer_support', 'High', '["slack"]'::jsonb
) ON CONFLICT (skill_id) DO NOTHING;

INSERT INTO company_skills (skill_id, author_id, name, description, lifecycle_state, workflow_id, tags, staging_category, staging_risk_level, staging_required_connections) VALUES (
  'a1111111-0000-4000-8000-000000000004', '00000000-0000-0000-0000-000000000001', '정기 웹 데이터 수집·적재', 'Cron 스케줄에 따라 대상 URL을 수집하고 정규식으로 값을 추출해 PostgreSQL에 적재. 모니터링/가격추적 등 정기 수집 자동화. (원본: Web Scraper)', 'published', 'b1111111-0000-4000-8000-000000000004',
  '["it_ops", "scraping", "etl", "ecommerce"]'::jsonb, 'it_ops', 'High', '["postgresql"]'::jsonb
) ON CONFLICT (skill_id) DO NOTHING;

INSERT INTO company_skills (skill_id, author_id, name, description, lifecycle_state, workflow_id, tags, staging_category, staging_risk_level, staging_required_connections) VALUES (
  'a1111111-0000-4000-8000-000000000005', '00000000-0000-0000-0000-000000000001', '딥 리서치 리포트 생성', '리서치 주제를 입력하면 외부 검색 API로 소스를 수집하고 다단계로 분석·종합해 출처가 달린 PDF 리포트로 산출. (원본: Deep Research Engine)', 'published', 'b1111111-0000-4000-8000-000000000005',
  '["document_data", "research", "ecommerce"]'::jsonb, 'document_data', 'Medium', '["anthropic"]'::jsonb
) ON CONFLICT (skill_id) DO NOTHING;

COMMIT;
