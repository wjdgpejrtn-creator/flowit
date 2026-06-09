# 스켈레톤 회귀분자 수정 설계 (ADR-0026 §6.6 후속)

> 상태: Draft · 2026-06-09 · 소유 후보: REQ-004(ai_agent, 신정혜) + 측정/조장(황대원)
> 선행: #439(composer 스켈레톤 통합) 머지·배포 완료 → 양팔 de-noise 측정에서 **순회귀** 발견

---

## 1. 배경 — 측정이 드러낸 것

#439 배포 후 골든셋 32건 × 3-run de-noise 측정 결과, 스켈레톤이 **집계상 순회귀**:

| 지표 | A: 카탈로그+온톨로지 | B: +스켈레톤(#439) | 순효과 | 유의성 |
|------|:---:|:---:|:---:|:---:|
| qa_pass(≥8) | 75.0%±3.6% | 58.3%±2.1% | **−16.7%p** | ✓ robust |
| qa_score 평균 | 8.61±0.21 | 7.73±0.06 | **−0.88** | ✓ robust |
| motif-correctness | 75.0%±0.0% | 58.3%±0.0% | **−16.7%p** | ✓ robust |
| validator-pass | 27.4%±4.1% | 21.4%±3.6% | −6.0%p | ~ |
| avg_retry | 1.33±0.07 | 1.45±0.06 | +0.12 | ~ |
| hallucination | 0.0% | 0.0% | ±0 | · |

**그러나 per-scenario로 보면 "표적 성공 + 비표적 부작용"**:

- **스켈레톤이 살린 케이스** (팀원이 staging에서 라이브 확인한 부류):
  - `lin_sheet_to_mail` "시트 읽어 요약 메일" 5.3→**10.0**
  - `lin_pdf_extract` 6.0→**10.0**, `lin_notify_on_event` 8.0→**10.0**
- **스켈레톤이 죽인 케이스**:
  - 분기: `branch_threshold_alert` 10→4.0, `branch_sentiment` 10→5.3
  - 선형: `lin_doc_to_slack` 10→3.7, `lin_fetch_summarize` 10→4.7, `lin_meeting_notes` 10→7.0
  - 루프: `loop_summary_until_good` 10→5.3, `loop_report_quality` 10→7.7

카테고리별 Δqa: **branch −2.67** (최악) / loop −0.75 / lin −0.50 / chit ±0.

> 결론: 스켈레톤은 정확히 매칭되는 선형 수집-통지 패턴을 **확실히 개선**하지만, 비표적 케이스에 **억지로 발동**해 구조를 망친다. 골든셋(균형 세트)에선 부작용이 평균을 끌어내리나, 실사용이 선형 패턴에 쏠리면 체감은 +일 수 있다(팀원 사례).

---

## 2. 죽은 케이스 해부 (실측 산출 구조)

| 시나리오 | 발화 | A (자유조립) qa | B (스켈레톤) qa | B가 매칭한 스켈레톤 |
|---------|------|:---:|:---:|:---:|
| branch_threshold_alert | "온도 값이 임계치를 **넘으면** 경보 메일을 보내줘" | webhook→**if_condition**→email (10) | schedule→email (4) | scheduled_pipeline ❌ |
| branch_sentiment | "감정을 **분류**해서 **부정이면** 에스컬레이션" | webhook→gemma→**if_condition**→{stop, issue} (10) | schedule→anthropic→**google_docs_write** (5) | scheduled_pipeline ❌ |
| lin_doc_to_slack | "문서를 읽고 **핵심만** 슬랙 공유" | webhook→**gemma_chat**→slack (10) | schedule→slack (4) | scheduled_pipeline |
| lin_fetch_summarize | "이 URL 내용을 **가져와서 요약**" | manual→**rest_api**→gemma (10) | schedule→anthropic→**google_docs_write** (5) | scheduled_pipeline |

---

## 3. 근본 원인 (정정됨 — "분기 스켈레톤 부재"가 아니다)

> ⚠️ 초기 가설("분기 스켈레톤이 없어서")은 **오진**. `branch_on_classification` 스켈레톤
> (`skeleton_library.py:126`)과 `_assemble_branch`(`skeleton_assembler.py:217`)는 **이미 존재**한다.
> 진짜 원인은 아래 3개다.

### RC1 — catch-all 폴백이 비매칭을 삼킴 (가장 큰 레버)

`SkeletonAssembler._select` (`skeleton_assembler.py:70`):

```python
return find_skeleton("scheduled_pipeline") or SKELETONS[0]
```

shape 미감지 + 선형 키워드 0매칭 + 트리거 비-이벤트 → **무조건 scheduled_pipeline 강제**.
죽은 케이스 대부분(branch 2건 + lin_doc/fetch)이 이 폴백 희생자. 자유조립(arm A)은 이들에서 qa 10이므로, **폴백 대신 `None`(LLM 위임)이면 그대로 회복**된다.

### RC2 — 분기 감지 누락 (스켈레톤은 있으나 도달 불가)

`SkeletonEntityExtractor._BRANCH_KEYWORDS` (`skeleton_entity_extractor.py:92`)에
조건 표현 `~으면`/`~이면`이 **의도적으로 제외**돼 있다(주석: "단독 '면'은 빈출이라 금지").
그 결과:
- "임계치를 **넘으면**" → `has_branch=False`
- "부정**이면**" → `이면`이 분기 키워드 `이라면 `과 불일치 → `has_branch=False`

→ `assemble()`의 shape 라우팅(`:141`)이 branch를 못 타고 `_select`로 흘러 RC1 폴백에 먹힌다.

추가로 `_assemble_branch`는 `len(entities.sinks) != 2: return None`(`:224`)로 **정확히 2-sink일 때만** 조립 → 1-sink 조건부("넘으면 경보 보내")는 표현 불가.

### RC3 — scaffold 경직 (advisory가 아니라 authoritative)

`_assemble_linear`는 추출 엔티티를 슬롯에 그대로 박는다. TRANSFORM 슬롯은 `required=False`라
**추출이 놓치면 노드가 사라진다**:
- `lin_doc_to_slack` "핵심만"은 transform 키워드(요약/정리/생성)에 없음 → transform 드롭 → schedule→slack(불완전).
- `lin_fetch_summarize`는 source(rest_api) 미추출 + `_DEFAULT_CONTENT_SINK`(google_docs_write) 오주입(`:29`).

자유조립은 LLM이 이런 누락을 메우지만, 스켈레톤은 추출 결과를 **권위적으로** 고정해 그 보정을 차단한다.

---

## 4. 설계 — 수정 (1)(2)(3)

### (1) catch-all 폴백 제거 → confident-only 발동 [RC1]

- `_select`의 최종 `scheduled_pipeline` 폴백 라인을 **제거**하고, 진짜 매칭 신호가 없으면
  `assemble()`가 `None`을 반환하도록 한다(LLM drafter 위임).
- 발동 조건을 명시화: ① needs_gate → quality_loop ② shape 신호 → 해당 조립 ③ **선형 키워드
  score>0 또는 명확한 schedule 트리거** → scheduled_pipeline/event_response ④ 그 외 → `None`.
- 기대 효과: branch_threshold_alert/branch_sentiment/lin_doc_to_slack/lin_fetch_summarize가
  자유조립으로 회복(arm A 기준 qa 10).

### (2) 분기 — 감지 확장 + 1-sink 조건부 지원 [RC2]

- **분기 키워드 확장**(과활성 가드 필수): `~을 넘으면`/`~이상이면`/`~이하면`/`~보다 크면` 등
  **임계 비교** 표현과 `~이면`/`~면 …아니면` 조건 표현을 추가하되, 빈출 부분문자열 오활성을
  막기 위해 **비교·분류 맥락 토큰과 결합**한 패턴으로 좁힌다(예: 단독 "면" 금지 유지, "넘으면"·
  "이상이면"처럼 비교어 동반만).
- `분류` 단독은 transform이지만 **`분류해서 …이면/아니면`** 처럼 분기 동반 시 branch 우선
  (shape 라우팅에서 transform+branch 공존 허용 — classifier 슬롯이 곧 transform).
- **🆕 `conditional_action`(가드) 스켈레톤 신설** — 현재 라이브러리에 **순수 조건문이 없다**.
  7종(scheduled/event/quality_loop/branch/fan_out/retry/approval) 중 조건부는 branch_on_classification
  (2-way 분류)과 approval_gate(HITL 승인)뿐. "온도 넘으면 경보"(branch_threshold_alert)처럼
  **분류도 승인도 아닌 단일 가드 액션**은 표현 불가 → scheduled_pipeline 폴백으로 if_condition 소실.
  - 구조: `trigger → (source?) → (transform?) → router(if_condition) → [true]→sink / [false]→stop_workflow`.
    approval_gate 구조 재활용하되 **TRANSFORM optional**(가드는 분류기 불필요 — if_condition이 입력
    직접 평가. 자유조립 arm A가 `webhook→if_condition→email`로 푼 모양과 정합).
  - false→stop_workflow 자동 부착으로 router outgoing=2 → motif 판정(branch_on_classification:
    router outgoing≥2 + 무순환) **통과**.
  - 발동: 임계/비교 가드 어휘(`넘으면`/`이상이면`/`초과하면`/`도달하면`/`미만이면`). 승인 어휘면
    approval_gate 우선, 2-sink 양자택일이면 branch_on_classification 우선.

### (3) scaffold 권고화 — 저신뢰 시 LLM 위임 [RC3]

- **누락 가드**: 선형 조립에서 발화가 가공을 함의(예: "요약/핵심/정리/분석"의 광의 표현)하는데
  transform이 비면, 노드를 드롭하지 말고 **`None` 반환(LLM 폴백)** 또는 transform 슬롯을
  default(anthropic_chat)로 채운다(둘 중 측정으로 선택).
- **오주입 제거**: `_DEFAULT_CONTENT_SINK`(google_docs_write) 자동 주입은 발화가 출력 채널을
  명시하지 않은 경우 **부정확**(lin_fetch_summarize). 출력 미언급이면 transform-종단 유지 or
  None 폴백으로 변경(측정 게이트).
- 원칙: **스켈레톤은 "확신할 때만 처리하는 fast-path"** (assembler docstring과 정합). 확신
  못 하면 자유조립이 이긴다는 게 측정 결론.

---

## 5. 결정 — `conditional_action`(가드) 스켈레톤 신설 (2026-06-09 확정)

순수 조건문(guard) 스켈레톤이 라이브러리에 **부재**함이 확인됨(§4-(2) 🆕). "임계치 넘으면 경보"는
분류(branch_on_classification)도 승인(approval_gate)도 아닌 **단일 가드 액션**이라 기존 어느
스켈레톤에도 안 맞고, 폴백으로 if_condition이 소실됐다.

**결정**: 기존 분기를 1-sink로 완화하는 대신 **전용 `conditional_action` 스켈레톤을 신설**한다
(사용자 지시 2026-06-09). 이유: 1-sink 가드를 2-way 분류 스켈레톤에 욱여넣으면 의미가 흐려지고,
가드는 transform optional 등 슬롯 구성이 분류와 다르다. 구조·발동·motif 정합은 §4-(2) 🆕 참조.

> 3종 조건부의 경계(발동 우선순위): 승인 어휘("검토/승인/컨펌") → approval_gate / 2-sink
> 양자택일("아니면/그 외에는" + sink 2개) → branch_on_classification / 임계·비교 가드("넘으면/
> 이상이면") → conditional_action. 셋 다 router(if_condition) outgoing≥2라 motif 통과.

---

## 6. 검증 게이트 (필수 — 측정 없이 머지 금지)

- 단위: `skeleton_entity_extractor` / `skeleton_assembler` 분기 감지·폴백·드롭 가드 테스트 추가.
  특히 **과활성 회귀 테스트**(잡담·일반 발화가 branch로 오분류 안 되는지).
- 라이브: 본 수정 브랜치로 **3-run de-noise** 재측정 → 게이트:
  - **표적 케이스 보존**: lin_sheet_to_mail/pdf_extract/notify_on_event qa ≥ 현 스켈레톤 arm.
  - **회귀분자 회복**: branch_*/lin_doc_to_slack/lin_fetch_summarize qa ≥ 자유조립(arm A) 수준.
  - **집계**: qa_pass가 카탈로그+온톨로지 arm(75%) **이상**, motif ≥ 75%.
- 측정 프로토콜: `ontology_grounding/REPORT.md` 양팔 de-noise(3-run mean±std), `tmp_compare_arms.py` 재사용.

## 7. 롤아웃

- 수정은 `modules/ai_agent/domain/services/` (extractor/assembler/library) — REQ-004 영역(신정혜).
- 측정·게이트는 조장(황대원).
- **#439를 revert하지 않는다** — 표적 케이스(팀원 라이브 확인)를 살리므로 유지하고 본 수정으로
  부작용만 제거. 수정 머지 → release sync → Modal `agent-composer` 재배포 → 재측정.
- 스냅샷 보존: `composer_grounding.run{1,2,3}.json`(카탈로그+온톨로지) / `.skel_run{1,2,3}.json`(현 스켈레톤)이 비교 기준.
