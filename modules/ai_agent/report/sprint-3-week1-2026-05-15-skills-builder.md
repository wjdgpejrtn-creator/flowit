# Sprint 3 Week 1 — 2026-05-15 (금) 박아름 Skills Builder 진척 보고

> **작성**: 박아름 (REQ-002 Auth · REQ-003 Nodes-Graph · REQ-004 Skills Builder 담당)
> **세션 일자**: 2026-05-15 (금)
> **이전 보고서**: `2026-05-14-skills-builder.md`

---

## 1. 5/15 한 줄 요약

PR #68(gemma_chat 신설) 머지 완료 + PR #69(docs PR — CLAUDE.md SSOT 협의 5건 + EmbedderPort stale 정정 + verification 보고서 §6 재작성/§8/§9 신규 + ADR-0013 + REQ-003 docstring 정정) 생성 + 햄햄 카톡 사이클 **5회**(NodeSearchPort 위치 / 11종 분류 / LLMPort 의존성 / 분류 변경 정정 / 브랜치 결정) 완주. PR #60(김진형 doc-parser) 박아름 리뷰 코멘트 게시 + PR #70(신정혜 Personalization 연동) + PR #71(햄햄 PHASE 1) 박아름 리뷰 게시. 단체 카톡으로 노션 보고서 공유 + 4명 담당자별 협의 영역 명시.

---

## 2. 머지 / PR 사이클

### 2.1 PR #68 — gemma_chat 신설 머지 완료 ✅

- **머지 시점**: 2026-05-15 03:18:37 UTC (박아름 셀프 머지)
- **merge commit**: `f2e21c5`
- **변경 파일**: 5개 (gemma_chat.py / test_gemma_chat.py / catalog_registry.py / REQ-003 spec / seed JSON)
- **commits 4개**: `8c68c7c` 신설 + `9459852` development merge + `0112444` spec+seed + `fbc9365` catalog_registry
- **5/15 정밀 self-review** 코멘트 게시 (https://github.com/billionaireahreum/Workflow_Automation/pull/68#issuecomment-4456586411)
  - 3축 (SSOT / 타 모듈 의존성 / Clean Architecture) PASS
  - 트레이드오프 1건 명시: `catalog_registry.py` Plugin discovery 옵션 A (Plan §3 명시), Sprint 4+ 옵션 B 재검토 예정

### 2.2 PR #69 — docs PR 생성

- **URL**: https://github.com/billionaireahreum/Workflow_Automation/pull/69
- **commit**: `f5419a2` (5개 파일 통합)
- **base**: development / **head**: feature/req-004-skills-builder
- **변경**: 5 파일 / +386 / -293
- **상태**: OPEN / MERGEABLE / 조장 리뷰 대기
- **포함 내용**:
  - CLAUDE.md 협의 5건 (조장 협의 대상): 카탈로그 종 수 54→56 / 교차 import 표 2건(`auth → nodes_graph` + `toolset → nodes_graph`) 추가 / Port→Adapter 매핑 `EmbeddingPort` → `EmbedderPort` 예외 패턴 명시
  - EmbedderPort SSOT stale 정정 8곳: REQ-004 spec(3) + MONOREPO_STRUCTURE(2) + clean_architecture(3)
  - verification 보고서 §1.5(의존성 발견) + §4.1(인용 라인 정정) + §6(통째 재작성, Y옵션) + §8(FAQ 9건 신규) + §9(협의 사항 신규)

---

## 3. 햄햄 카톡 사이클 (5회 완주)

### 3.1 햄햄 첫 자료 — NodeSearchPort 위치 + toolset_nodes 협의

박아름 답변 [1]~[7]:
- 원칙 동의: "Tool = AI 내부 도구, Node = workflow 구성요소"
- NodeSearchPort = `toolset/adapters/node_search_adapter.py` 동의
- 의존성 방향 1건 확인 부탁: `toolset → nodes_graph application/use_cases` 교차 import 표 추가 필요 → **PR #69로 처리 완료**
- 한 줄 정리 보강 (CipherPort / ParserPort / EmbedderPort 예외 패턴) → **PR #69로 처리 완료**
- toolset_nodes 14종 중 중복 3건 박아름 동의 → 나머지 11종 처리 확정 부탁
- 작업 시점: PR #68 머지 + 햄햄 11종 처리 확정 후 박아름 별도 PR

### 3.2 햄햄 응답 — 11종 분류안 도착

햄햄이 박아름 답변 후 11종 분류안 공유:

**Node 유지 6종 (`external/` 이동)**:
- `rest_api` / `graphql` / `webhook` (사용자 외부 연동)
- `email_send` / `slack_notify` (워크플로우 알림)
- `text_template` (사용자 템플릿 작성)

**Internal Tool 5종 (`toolset` 영역 BaseTool 신설)**:
- `json_transform` / `data_mapping` (AI 내부 처리)
- `file_read` / `file_write` / `file_transform` (보안 + 경로 노출 우려)

### 3.3 박아름 5/15 정밀 검증 + 답변

003 브랜치 체크아웃해서 정밀 비교:

| 항목 | 발견 |
|---|---|
| `slack_notify` vs `slack_post_message` | **별개 노드 확정** — `slack_post_message`(OAuth Bot + chat.postMessage + Block Kit) vs `slack_notify`(Incoming Webhook URL). 박아름 첫 답변 "중복 3건"이 잘못, 햄햄 분류 맞음 |
| `http_request_tool` vs `external/http_request` | 중복 ✅ — 박아름 + 햄햄 양측 제거 동의 |
| `conditional`/`loop` vs `domain/catalog/control/if_condition`+`loop_list` | 중복 ✅ — 박아름 + 햄햄 양측 제거 동의 |

→ 박아름 첫 답변 "중복 3건" → 정정 **"중복 2건 + slack_notify 별개"**.

**Skills Builder SkillNode 30종 영향 평가**:
- `modules/ai_agent/seeds/functional_domain_defaults/*.json` 5개 + `industry_defaults/*.json` 6개 전수 grep 결과 Internal Tool 5종 사용 **0건**
- Skills Builder 작업 변경 불필요

박아름 답변 발송: 11종 전면 동의 + 박아름 PR 작업 8단계 + 카탈로그 종 수 변화 예상(56 → 48)

### 3.4 햄햄 LLMPort 의존성 질문 + 박아름 답변

햄햄 질문: gemma_* `process()` wiring 시 `toolset → ai_agent.LLMPort` 호출이 CLAUDE.md 교차 import 표에 없는데, 옵션 A(execution_engine DI 주입) vs 옵션 B(toolset이 Gemma HTTP endpoint 직접 호출)?

박아름 답변: **옵션 A 권장**

근거:
1. Clean Architecture 의존성 역전(DIP) 정합 — `ai_agent/domain/ports/LLMPort` SSOT + 구현체 `ai_agent/adapters/llm/ModalLLMAdapter`
2. LLM 정책(timeout / retry / prompt 정규화) 중복 회피
3. 박아름 anthropic_chat / gemma_chat 패턴과 정합 (NotImplementedError + ai_agent.LLMPort 위임 메시지)

CLAUDE.md 교차 import 표 추가 필요: `toolset → ai_agent.domain.ports/LLMPort`
- 처리 방법: 박아름 docs PR 추가 commit 또는 햄햄 PHASE 1 PR 포함 — 햄햄 결정 영역

### 3.5 햄햄 회신 — 분류 + 일정 확정

- 박아름 분류·중복·정정 모두 확인 ✅
- gemma_* wiring 햄햄 담당 인정 ✅
- PHASE 1 PR — `ToolCategory` Enum + `capabilities` 추가만, 금주 내 PR 예정
- PR #68 머지되면 알림 부탁 → 박아름 5/15 03:18 PR #68 셀프 머지 후 햄햄에게 카톡 알림 발송 완료

### 3.6 햄햄 5/15 후반 분류 변경 카톡 발생 + 박아름 정정 + 햄햄 재확인

PR #71 본체 작업 진행 중 햄햄이 카톡으로 분류 변경 시도:
- "외부 API 3 + 이메일/알림 2 + 데이터 변환 3 + 파일 처리 3 = 11종 모두 `external/` 일원화" 제안
- 5종(`json_transform`/`data_mapping`/`file_read`/`file_write`/`file_transform`)을 Internal Tool에서 external/로 변경 시도
- 3종(`conditional`/`loop`/`http_request_tool`)도 "별도 처리 방향 확인" 재요청 (이전 박아름 + 햄햄 합의 = 제거였음)

**박아름 정정 답변**:
- 이전 5/15 분류 vs 이번 분류 정확히 비교 표 제시
- 5종 분류 변경 우려 짚음:
  - file_* — 햄햄 본인이 5/15에 "보안 + 경로 노출 우려, Agent 내부 전용" 명시한 영역
  - json/data — "복잡한 변환은 AI 내부 처리" 의도 변경?
- 작업 시간 영향 (3~4h → 5~7h) 명시
- 3종 중복 — 박아름 003 브랜치 정밀 비교 결과 다시 공유 (도메인 쪽 더 풍부, 제거 권장)

**햄햄 재확인 응답**:
- "카톡에 실수가 있었어요, 이전 5/15 분류 그대로가 맞아요" — 박아름 지적 정확 인정
- 메모리에 이전 분류 미저장으로 인한 혼선이었음
- **최종 확정**: Node 유지 6 + Internal Tool 5 + 제거 3 그대로 유지
- 작업 범위 external/ 6 파일 + 14종 제거 + 3~4h 기준 그대로 진행

### 3.7 박아름 toolset 정리 PR 브랜치 결정 — 별도 PR

햄햄이 "이 정리 작업 자체는 feature/req-005-toolset 브랜치 범위"라고 제안 (PR #71에 통합 의도).

**박아름 결정 — 별도 PR로 진행 (REQ-003 메인 브랜치)**:
- 근거 1: 박아름 룰 [[feedback_branch_strategy]] "REQ별 메인 브랜치 영구 보존"
- 근거 2: 5/15 진척 보고서 §3.3 + verification §9.2.2에 "박아름 별도 PR" 명시
- 근거 3: nodes_graph 영역 책임 박아름 → 책임 영역 분리 명확화
- 근거 4: PR #71과 박아름 PR이 다른 영역 변경이라 분리 머지 가능

**흐름**:
1. 햄햄 PR #71 조장 리뷰 + 머지 (대기 중)
2. PR #71 머지 후 박아름이 development sync
3. REQ-003 메인 브랜치(`feature/req-003-nodes-graph`)에 commit + 박아름 새 PR 생성
4. 박아름 PR 조장 리뷰 + 머지

박아름 별도 PR 양해 부탁 카톡 발송 완료 (5/15) → **햄햄 동의 받음 ✅**:
> "nodes_graph 영역이라 REQ-003 메인 브랜치로 별도 PR 내시는 게 추적성이나 책임 분리 면에서 훨씬 깔끔한 것 같아요. 순서(PR #71 머지 → development sync → 박아름 PR)도 맞고요. 진행 OK입니다."

→ **흐름 합의 완료**. PR #71 머지 후 박아름 진입 트리거.

---

## 4. PR #60 (김진형 doc-parser) 박아름 리뷰

### 4.1 첫 리뷰 (얕음) — 박아름 자체 반성

- PR #60 코드 4개 파일 import만 확인 + 박아름 영역 영향만 평가
- 박아름의 "프로젝트 전체적 내용 보고 한 거 맞지?" 지적 → 솔직히 인정

### 4.2 두 번째 리뷰 (전체 영향)

`feature/req-006-doc-parser` 브랜치 체크아웃해서 정밀 검증:

- **PR body 미명시 큰 변경 2건 발견**:
  - `hwpx_parser.py` — HWPX 표 셀 자식 요소(`t/run/r`) 추출 패턴 변경 (commit `cbf3dfa`)
  - `markdown_parser.py` — Markdown 표 파서 활성화 + `table_open`~`table_close` 블록 추출 (commit `4b65ebb`, +31줄)
- **doc_parser 외부 소비자 = 박아름 Skills Builder 1개만** (Composer / api_server / execution_engine 모두 5/15 시점 import 0건)
- **박아름 영역 영향 = 0건**, 긍정적 효과 (DocumentBlock 입력 품질 향상)
- **fixture 50~80MB 추가 추정** → git LFS 협의 권장 (조장 영역)
- **코드 품질 3건 Minor**: `except Exception` 광범위 / `count` regex 광범위 / Markdown 표 헤더 구분 누락
- **단위 테스트 누락 가능**: `_load_workbook_safe` / HWPX 표 / Markdown 표 단독 단위 테스트

박아름 리뷰 코멘트 게시: https://github.com/billionaireahreum/Workflow_Automation/pull/60#issuecomment-4456308955

---

## 5. verification 보고서 노션 업로드 준비

### 5.1 보고서 갱신 사항 (5/15)

| 영역 | 변경 |
|---|---|
| 헤더 검증 일자 | 2026-05-14 → **2026-05-15 (5/14 초안 + 5/15 §1.5/§6/§8/§9 갱신 + docs PR 반영)** |
| §1.5 (신규) | `credential_injection_service.py:6` `from nodes_graph.domain.ports.NodeDefinitionRepository` 의존성 발견 |
| §4.1 인용 라인 정정 | `anthropic_chat.py:40` → `:57-103` (NodeMetadata vs NodeDefinition 위치 정확화) |
| §6 통째 재작성 (Y옵션) | 옵션 B+(Tier 1 4개) 잔재 → §6.7 부록(폐기됨 명시)으로 압축. 본문은 gemma_chat 1개 + anthropic_chat 보존으로 일관 |
| §7 🔵 docs PR | ✅ PR #69 생성 완료 (2026-05-15) |
| §8 FAQ 9건 (신규) | LangGraph(신정혜) / 4 Frame / Modal / Composer UI / 장단기 분류 등 SSOT 비교 검증 포함 |
| §9 협의 사항 (신규) | 조장 협의 5건 (§9.1 CLAUDE.md) + 담당자 4명별 분리 (§9.2) |
| 종합 결론 표 | §6 결정 반전 + PR #68 머지 완료 반영 |

### 5.2 단체 카톡 발송 완료

조장 / 신정혜 / 햄햄 / 김진형 4명 멘션 + 노션 링크 + 영역별 확인 요청:

- **조장 (§9.1 + §9.2.3)**: PR #69 / PR #68 / baseline 25종 출처 / 장단기 의도 출처
- **신정혜 (§9.2.1)**: RouteRequestUseCase 의도 분류 명칭 SSOT 갱신
- **햄햄 (§9.2.2)**: toolset_nodes 11종 처리 (별도 카톡 사이클 진행 중)
- **김진형 (§9.2.4)**: 박아름 협의 0건 + PR #60 박아름 리뷰 코멘트 참고

---

## 6. 5/15 박아름 결정 흐름 정리

| # | 결정 | 근거 |
|---|---|---|
| 1 | PR #68 셀프 머지 결정 | 박아름 본인 PR + 조장 리뷰 대기 후 박아름 결정 (5/14 야간 self-review 3축 PASS + 5/15 정밀 self-review 추가 PASS) |
| 2 | §6 통째 재작성 (Y옵션) | 옵션 X(결정 반전 박스만 추가)는 본문↔헤더 모순. 노션 올리면 팀장 혼란 가능. Y옵션으로 깔끔 정리 |
| 3 | docs PR로 협의 5건 일괄 처리 | 박아름이 5/14에 햄햄/조장에 약속한 후속 docs PR — PR #51 머지 후 진행 가능 → PR #69 생성 |
| 4 | 햄햄 11종 분류 전면 동의 | 003 브랜치 정밀 검증 후 합리적 판단 확인. `slack_notify` 별개 노드 인정 (박아름 첫 답변 정정) |
| 5 | LLMPort 옵션 A 권장 | Clean Architecture DIP 정합 + LLM 정책 캡슐화 + 박아름 anthropic_chat 패턴과 정합 |

---

## 7. 다음 작업 (5/16+ 예상)

### 박아름 즉시 진행 가능

- ✅ 모두 완료. 박아름 영역 즉시 작업 0건.

### 외부 응답 대기

| 항목 | 대기 대상 | 박아름 다음 행동 |
|---|---|---|
| PR #69 (docs PR) 리뷰 + 머지 | 조장 | approval 후 자동 머지 또는 박아름 셀프 머지 |
| 햄햄 PHASE 1 PR (toolset 5종 Internal Tool 신설) | 햄햄 | 머지 시점 박아름 toolset 정리 PR 진행 트리거 |
| 햄햄 LLMPort 의존성 처리 (옵션 A) | 햄햄 결정 | CLAUDE.md 교차 import 표 추가 — 박아름 docs PR vs 햄햄 PHASE 1 PR |
| 햄햄 PR #54 머지 (Personalization) | 햄햄 | agent_memory 마이그레이션 트리거, 박아름 영역 변경 0건 |
| 조장 baseline 25종 출처 | 조장 카톡 | 11종 vs 25종 결정 (Sprint 4 확장 또는 박아름 메모 오차) |
| 조장 장기/단기 의도 분류 출처 | 조장 카톡 | SSOT 갱신 또는 5가지 intent 유지 결정 |

### 박아름 toolset 정리 PR (햄햄 PR 머지 후)

- `toolset_nodes.py` + `tool_to_node_wrapper.py` 삭제
- `external/` 6 파일 신규 (rest_api / graphql / webhook / email_send / slack_notify / text_template)
- `catalog_registry.py` 갱신 (toolset 14 제거 + external 6 추가)
- `database/seeds/node_definitions.json` 갱신
- DB cleanup (86 → 78 row 예상)
- 단위 테스트 (6 신규 + 14 제거)
- REQ-003 spec line 490 갱신
- **소요 3~4시간**

---

## 8. 5/15 작업 사이클 통계

| 항목 | 값 |
|---|---|
| 머지된 PR | 1건 (PR #68 — `f2e21c5`) |
| 신규 생성한 PR | 1건 (PR #69 — `f5419a2`) |
| 박아름 게시 리뷰 코멘트 | 2건 (PR #68 self-review + PR #60 김진형 리뷰) |
| 햄햄 카톡 사이클 | **5회** (NodeSearchPort + 11종 분류 + LLMPort 의존성 + 분류 변경 정정 + 브랜치 결정) |
| 단체 카톡 발송 | 1건 (노션 보고서 공유 + 4명 담당자별 협의) |
| verification 보고서 갱신 섹션 | 8건 (헤더 / §1.5 / §4.1 / §6 / §7 / §8 / §9 / 종합 결론) |
| 신규 생성 메모리 | 0건 (5/15 새로 생성 안 함, 기존 `project_pending_tasks_2026_05_15.md` 갱신만) |

---

## 9. 참조

- 5/14 보고서: `modules/ai_agent/report/sprint-3-week1-2026-05-14-skills-builder.md`
- 5/13 보고서: `modules/ai_agent/report/sprint-3-week1-2026-05-13-skills-builder.md`
- verification 보고서: `modules/ai_agent/report/2026-05-14-verification-auth-node-skillbuilder.md`
- PR #68: https://github.com/billionaireahreum/Workflow_Automation/pull/68 (MERGED `f2e21c5`)
- PR #69: https://github.com/billionaireahreum/Workflow_Automation/pull/69 (OPEN)
- PR #60: https://github.com/billionaireahreum/Workflow_Automation/pull/60 (박아름 리뷰 코멘트)
- 메모리: `project_pending_tasks_2026_05_15.md` / `feedback_pull_merged_prs.md` / `feedback_req003_branch_basis.md`
