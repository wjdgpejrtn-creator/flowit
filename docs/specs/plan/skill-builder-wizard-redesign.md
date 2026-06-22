# 스킬빌더 위저드 재설계 — 문서 有無 분기 + default(seed) SOP 경로

2026-06-01 ~ / 담당: 황대원(api_server·frontend 조립) · 박아름 영역(skills-builder extract) 협의

> 본 문서는 **설계안**이다. 코드 변경 전 방향 합의용. REQ-010/013, ADR-0020(Q8 wizard) 후속.

---

## 1. 배경 — 왜 다시 그리나

스킬빌더의 제품 본질: **대상은 도메인 전문가만이 아니라 벤처 초기·소규모 사업가(비전문가)도 포함**한다. 비전문가가 인터뷰(검토·편집)만으로 자기 업무에 맞는 스킬을 얻는 것이 가치다.

현재 어긋난 지점:

| 계층 | 현재 | 문제 |
|---|---|---|
| 프론트 스킬빌더 | 수동 폼 (+#278 sop 문서경로) | 첫 화면 분기 없음. 비전문가가 빈 폼 앞에서 막힘 |
| 백엔드 `industry_default`/`functional_domain` | seed를 전역 카탈로그에 **즉시 PUBLISHED upsert** | 인터뷰도 커스텀도 없는 "완성품 박기". 위저드 아님 |
| seed 데이터 | 산업 6 + 직무 5 JSON | **본래 의도 = 아무것도 없는 사용자에게 제공하는 SOP 문서 재료**(황대원 확정). 그런데 이 용도로 안 쓰이고 있었음 |

## 2. 목표 흐름

```
스킬빌더 진입
  │
  ├─ [첫 화면] "업무 관련 문서가 있으신가요?"
  │     │
  │     ├─ 예, 있어요 ─────────────► [문서 위저드]
  │     │      내 문서 선택
  │     │        → POST /skills/extract { source_document_id }
  │     │
  │     └─ 아니요, 직접 만들게요 ──► [default 위저드]
  │            업종/직무 선택 (ecommerce, 요식업, 마케팅 …)
  │              → POST /skills/extract { template_code }
  │              (서버가 seed → DocumentBlock(SOP 텍스트) 합성 후 추출)
  │
  └─ [공통 합류 — 추출 이후 동일]
        AI 추출 진행(SSE) → 추출 초안 목록
          → 1건 선택 → 폼 prefill(name/description/instructions)
          → 사용자 검토·편집 (= 1차 인터뷰)
          → [스킬 생성] POST /skills/personal
          → personal DRAFT (GCS SKILL.md + source_document_id/template 출처)
```

핵심 원칙: **두 갈래는 "추출 입력을 무엇으로 만드느냐"만 다르고, 추출(LLM)·검토·편집·확정은 완전히 동일**하다. default도 LLM 추출을 거쳐 전문 SKILL.md(`instructions`)를 생성한다 — seed에는 instructions가 없으므로 LLM 생략은 불가(원래 문제 재발).

## 3. 결정 사항 (확정)

- **D1. default 재료 = 기존 seed 재사용.** 신규 템플릿 작성 X. `modules/ai_agent/seeds/{industry_defaults,functional_domain_defaults}/*.json`.
- **D2. seed는 SOP "문서"로 취급** → DocumentBlock으로 합성해 sop extract(LLM)에 태운다. (황대원: "seed는 아무것도 없는 사용자에게 우리가 SOP 문서로 제공하려고 만든 것")
- **D3. 인터뷰 깊이 1차 = 추출 초안 검토·편집 수준.** Q&A 대화형은 산출물 본 뒤 추후 결정(미착수).
- **D4. 첫 화면 = 문서 有無 분기**로 시작. 문서 입력이 첫 화면이 아니다.

## 4. 미결 (구현 착수 시 확정)

- **O1. 기존 즉시-upsert 경로**(`build_from_industry_default_use_case`, `build_from_functional_domain_use_case`) 운명: 잠정 = **사용자 위저드에선 미사용**, 관리자/전역 카탈로그 시딩 도구로 존치. 폐기 여부는 별도.
- **O2. seed → SOP 텍스트 합성 형태**: skill_nodes를 어떤 markdown 구조로 풀어 LLM에 줄지(노드별 "작업명/설명/입력·출력" 섹션 등). extract 프롬프트 품질에 영향.
- **O3. template 선택 UI 위치**: 첫 화면에서 "직접 만들게요" → 업종/직무 그리드 선택. 산업 6 + 직무 5 = 11개 카드.

## 5. 구현 단계 (Phase) — 코드 착수 시

### Phase 0 — 백엔드: seed 노출 + extract template 입력
- `GET /api/v1/skills/templates` — 사용 가능한 default 목록(industry 6 + functional 5: code/name/description). seed 메타만 읽어 반환(읽기 전용).
- `POST /api/v1/skills/extract` 확장: 기존 `source_document_id`에 더해 **`template_code`** 입력 허용(둘 중 하나, 배타). template_code면 서버가 seed 로드 → DocumentBlock(SOP 텍스트, O2) 합성 → 기존 extract 프록시 경로에 투입.
  - skills-builder 계약은 무변경(여전히 sop/extract + document 수신) — api_server가 seed→document 합성을 책임진다(composition root).
- 단위 테스트: templates 목록, template_code→extract 프록시(seed 합성 포함), source_document_id/template_code 배타 검증.

### Phase 1 — 프론트: 첫 화면 분기
- `/skills/builder` 첫 진입 = "업무 관련 문서가 있으신가요?" (예 / 아니요).
- `?source_document_id=` 핸드오프 진입은 자동으로 "문서 위저드" 분기로(첫 화면 스킵).
- "예" → 내 문서 선택(기존 select) → 문서 위저드.
- "아니요" → 업종/직무 카드 그리드(`GET /templates`) → default 위저드.

### Phase 2 — 프론트: 추출 이후 공통 위저드 통합
- 문서/template 어느 쪽이든 `POST /skills/extract` 호출(template이면 template_code, 문서면 source_document_id) → 동일 추출초안 목록·prefill·편집·생성 흐름(#278 구현분 재사용).
- 위저드 단계 표시(1.재료선택 → 2.추출·검토 → 3.생성) 시각화.

### Phase 3 — 정리
- O1 결정 반영(즉시-upsert 경로 분리/표시 정리).
- 문서: ADR-0020 / REQ-013 spec에 "default=seed-as-SOP" 흐름 반영.

## 6. 재사용 vs 신규

**재사용 (이미 있음):**
- `POST /skills/extract`(#278) + skills-builder `step=extract` + 추출초안 prefill/편집 UI
- 확정 저장 `POST /skills/personal`(instructions→GCS SKILL.md + source_document_id, #249)

**신규:**
- `GET /skills/templates`(seed 메타 노출)
- extract의 `template_code` 분기 + seed→DocumentBlock 합성(api_server)
- 첫 화면 분기 UI + 업종/직무 선택 그리드

## 7. ownership
- extract 엔진(BuildFromSOPUseCase)=박아름(휴가 위임). seed=박아름. api_server·프론트 조립=황대원. seed→document 합성을 api_server에 두면 skills-builder(박아름 영역) 무변경 — 크로스오너 마찰 최소. PR body 사후 통지.

## 8. 본질 체크 (잊지 말 것)
- 이 기능의 가치: **비전문가가 빈 화면 앞에서 막히지 않고**, 문서가 있으면 그걸로, 없으면 우리 SOP(seed)로 시작해 **검토·편집만으로 전문 SKILL.md를 가진 스킬**을 얻는 것.
- "코드 짜는 것도 좋지만 어떤 가치를 제공하려는지 본질을 잊지 말자"(황대원 2026-06-01).
