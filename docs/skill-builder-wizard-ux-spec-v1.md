# Skills Builder Wizard UX Spec v1 — Claude Design 요청용

**작성**: 박아름 (REQ-013 skills_marketplace 담당) | 2026-05-31
**용도**: Claude (claude.ai Artifacts)에게 시켜서 React 컴포넌트 prototype 받기

---

## 1. 작업 요청

LG헬로비전 사내 AI 자동화 플랫폼의 **스킬빌더 Wizard UI**를 React 컴포넌트로 디자인 + 구현해주세요.

현재 staging에 배포된 스킬빌더 화면은 **단순 폼**(이름/설명/지침/태그 사용자 직접 입력)이라 일반 사용자가 어떻게 써야 할지 모릅니다. 백엔드(`BuildFromSOPUseCase`)는 이미 **LLM 자동 분석 + 스킬 후보 추출 + 자동 초안 생성**을 구현해놓았는데, 프론트엔드가 그 흐름을 사용하지 않습니다. 본 spec은 그 백엔드를 활용하는 **단계별 Wizard UI**를 재설계합니다.

타겟 = Anthropic Claude의 "Custom Skills" 수준 UX. 사용자가 문서만 올리면 AI가 분석 → 후보 추천 → 초안 자동 작성 → 사용자 검토/확정.

---

## 2. 첨부 자료 (claude.ai에 같이 보내세요)

- **스크린샷 1**: 현재 스킬빌더 화면 (재설계 대상 — 단순 폼)
- **스크린샷 2**: 홈 화면 ("무엇을 자동화할까요?" 화면 — 디자인 톤 참고용)

---

## 3. 디자인 톤 (스크린샷 2 톤 유지 필수)

| 요소 | 패턴 |
|---|---|
| 전체 스타일 | **Notion 풍 미니멀** + 한국 UI 정돈 |
| Border | **1.5px solid 검은색** (`border-[1.5px] border-[var(--color-ink)]`) |
| Border-radius | **비대칭 라운드** (예: `rounded-[5px_11px_6px_10px]`, `rounded-[4px_8px_4px_8px]` — 손그림 느낌) |
| Background | `bg-paper`(연한 그레이) / `bg-paper2`(약간 더 진한) / `bg-surface`(카드) |
| Typography | 한글 작은 사이즈 (12~14px 본문, 13~15px 강조). bold 위주 강조 |
| Primary 버튼 | 보라색 (`bg-accent` 또는 보라 톤) |
| Ghost 버튼 | 흰 배경 + 1.5px border |
| 카드 | 부드러운 그림자 X, **1.5px border가 핵심** |
| 단계 표시 | 원형 숫자 ⓛⓞⓞⓞ (현재 스크린샷 1 우측 가이드 패널 참고) |
| 인터랙션 | 단계별 전환 부드럽게, 진행 상태 좌측 또는 상단 표시 |

### Tailwind 색상 토큰 (현재 codebase 사용 중)
```
var(--color-paper)     /* 최배경 */
var(--color-paper2)    /* 보조 배경 */
var(--color-surface)   /* 카드 배경 */
var(--color-ink)       /* 본문/border 검은색 */
var(--color-ink3)      /* 보조 텍스트 */
var(--color-ink4)      /* 약한 텍스트 */
var(--color-accent)    /* 보라 primary */
var(--color-risk-low)  /* 안전 톤 */
var(--color-risk-med)  /* 경고 톤 */
var(--color-line-soft) /* 부드러운 구분선 */
```

---

## 4. Wizard 전체 흐름 (7 단계, 2026-06-04 옵션 1 2단계 분리 반영)

```
[Step 1] 문서 업로드 또는 핸드오프 진입
    ↓
[Step 2] AI 문서 분석 — 메타 추출 (SSE stream, 진행 표시)
    ↓
[Step 3] 스킬 후보 추천 (LLM이 추출한 메타 5필드 카드 그리드)
    ↓
[Step 4] 사용자 선택 (후보 카드 클릭) → detail 추출 로딩 (~5-10초)
    ↓
[Step 5] 자동 초안 표시 + 사용자 편집 (detail 응답 폼 prefill, 편집 가능)
    ↓
[Step 6] 미리보기 + 검토
    ↓
[Step 7] confirm → DRAFT 저장 → 완료 화면
```

**옵션 1 분리(LLM JSON 잘림 해소)**: Step 2는 메타 5필드만(node_type/name/description/category/risk_level) 받아 카드 그리드 표시 — Step 4 카드 선택 시 detail(inputs/outputs/instructions/...)을 별도 호출해 Step 5 폼 prefill.

진입 경로 2가지:
- **A. 문서 핸드오프**: 문서 탭에서 "스킬빌더로 보내기" → `/skills/builder?source_document_id=<UUID>` → Step 2 자동 진입 (Step 1 skip)
- **B. 직접 진입**: `/skills/builder` → Step 1 (문서 선택 또는 업로드) → Step 2

---

## 5. 단계별 상세 명세

### Step 1 — 문서 업로드 또는 선택

```
┌─────────────────────────────────────────────────────────────┐
│ [1] 기반 문서   2 AI 분석   3 후보   4 선택   5 편집   6 미리보기  7 완료 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  스킬빌더                                                    │
│  AI가 문서를 분석해서 스킬을 자동으로 만들어 드려요          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📄 기반 문서 선택                                   │   │
│  │  ─────────────────────────────────────────────────   │   │
│  │  옵션 A — 기존 문서에서 선택                          │   │
│  │  [select dropdown: 문서를 선택하세요]                 │   │
│  │                                                       │   │
│  │  옵션 B — 새 문서 업로드                              │   │
│  │  [업로드 영역: 클릭 또는 드래그 — PDF/DOCX/MD]        │   │
│  │                                                       │   │
│  │  옵션 C — 문서 없이 빈 스킬 만들기 (고급)             │   │
│  │  [작은 링크: "문서 없이 직접 만들기 →"]              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│                              [다음 단계 →]  [취소]            │
└─────────────────────────────────────────────────────────────┘
```

- **컴포넌트**: `<Step1DocumentSelect />`
- **상태**: `document: DocumentResponse | null`
- **API**: `GET /api/v1/documents` (기존, REQ-009 황대원)
- **다음 단계 트리거**: `document` 선택됨 + "다음 단계" 클릭

### Step 2 — AI 문서 분석 (SSE stream)

```
┌─────────────────────────────────────────────────────────────┐
│ ✓ 기반 문서   [2] AI 분석   3 후보   4 선택   5 편집   6 미리보기  7 완료 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📄 PART04_핵심기술_재구성_v3.md                              │
│  ────────────────────────────────────────────────           │
│                                                             │
│      ⠋ AI가 문서를 분석하고 있어요...                       │
│                                                             │
│      ├─ 📑 문서 구조 파악 완료                              │
│      ├─ 🔍 핵심 작업 추출 중                                │
│      └─ ⚙️ 자동화 가능 스킬 후보 생성 중                    │
│                                                             │
│      (이 작업은 보통 10~30초 걸립니다)                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- **컴포넌트**: `<Step2Analyzing />`
- **상태**: `analyzingPhase: "structure" | "extraction" | "candidates"`, `error: string | null`
- **API**: `POST /api/v1/skills/extract` (SSE stream, api_server proxy)
  - payload: `{ "source_document_id": "<UUID>" }` 또는 `{ "template_code": "<str>" }` (XOR)
  - api_server가 agent-skills-builder로 proxy(`source_type="sop"`, `step="metadata"`, `document=<합성/조회된 DocumentBlock>`)
  - 응답 frames:
    - `AgentNodeFrame` (진행 표시 — `agent_node_name="skills_builder.sop.llm_extract_metadata"`)
    - `ResultFrame` (최종 결과 — `payload.skill_metas: SkillMeta[]`, 메타 5필드만)
    - `ErrorFrame` (실패 — code: `E_LLM_GENERATION_FAILED` / `E_NO_SKILLS_EXTRACTED` 등)
- **다음 단계 자동 전환**: `ResultFrame` 수신 → Step 3

### Step 3 — 스킬 후보 추천 (카드 그리드)

```
┌─────────────────────────────────────────────────────────────┐
│ ✓ 기반 문서  ✓ AI 분석   [3] 후보   4 선택   5 편집   6 미리보기  7 완료 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  AI가 이 문서에서 3가지 스킬을 추천했어요                    │
│  마음에 드는 걸 선택하세요                                   │
│                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │
│  │ 📊          │ │ 📝          │ │ 🔍          │         │
│  │             │ │             │ │             │         │
│  │ 발표 덱      │ │ 시스템 흐름  │ │ 6 섹션 구조 │         │
│  │ 자동 생성    │ │ 다이어그램   │ │ 검토 스킬   │         │
│  │             │ │ 추출 스킬    │ │             │         │
│  │ (action)    │ │ (transform) │ │ (utility)   │         │
│  │ 위험도: 낮음 │ │ 위험도: 낮음 │ │ 위험도: 낮음 │         │
│  └─────────────┘ └─────────────┘ └─────────────┘         │
│                                                             │
│                              [← 이전]  [선택 →]              │
└─────────────────────────────────────────────────────────────┘
```

- **컴포넌트**: `<Step3CandidatesGrid candidates={skill_metas} onSelect={...} />`
- **카드 정보** (각 SkillMeta — 메타 5필드만):
  - `name` (제목, 대형)
  - `category` 아이콘 (action/transform/utility 등)
  - `description` 1줄 미리보기
  - `risk_level` 뱃지 (Low=초록, Medium=노랑, High=빨강)
  - (inputs/outputs/instructions는 Step 4 detail 호출에서 받음)
- **상태**: `skill_metas: SkillMeta[]`, `selectedIndex: number | null`
- **다음 단계 트리거**: 카드 선택됨 → Step 4(detail 호출 + 로딩) → Step 5(폼 prefill)

### Step 4 — 사용자 선택 + detail 추출 로딩 (NEW 2026-06-04 옵션 1)

카드 선택 직후 detail 추출 호출 → 로딩 표시(~5-10초) → Step 5로 폼 prefill.

- **API**: `POST /api/v1/skills/extract/detail` (JSON 응답, api_server proxy)
  - payload: `{ "source_document_id"|"template_code", "meta": <선택된 SkillMeta dict> }`
  - api_server가 agent-skills-builder로 proxy(`source_type="sop"`, `step="detail"`, `document=...`, `meta=...`)
  - 응답: `{ "skill_detail": { node_type, instructions, inputs, outputs, required_connections, service_type, staging } }`
  - 에러: 422(LLM/입력 검증 실패) / 502(skills-builder 응답 비정상) / 503(client 미설정)
- **UI**: "선택된 스킬의 상세를 생성 중..." spinner + 진행 단계 표시(입력 스키마/출력 스키마/지침서)
- **다음 단계 자동 전환**: `skill_detail` 수신 → Step 5 (메타 + detail 합쳐서 폼 prefill)

### Step 5 — 자동 초안 표시 + 편집

```
┌─────────────────────────────────────────────────────────────┐
│ ✓ ✓ ✓ ✓   [5] 편집   6 미리보기   7 완료                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  AI가 초안을 자동으로 작성했어요                             │
│  필요한 부분만 수정하세요                                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 스킬 이름                                             │   │
│  │ [발표 덱 자동 생성_______________________________]    │   │
│  │ ⓘ AI가 작성한 이름 — 자유롭게 수정 가능              │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ 설명                                                  │   │
│  │ [textarea: AI 분석 기반 발표 덱 자동 생성 스킬...]   │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ 실행 지침 (SkillDocument body)                        │   │
│  │ [markdown editor — AI가 채운 본문, 편집 가능]         │   │
│  │   # 발표 덱 생성 스킬                                 │   │
│  │   ## 사용 시점                                        │   │
│  │   사용자가 발표 덱 작성을 요청할 때...                │   │
│  │   ...                                                 │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ 카테고리       위험도                                  │   │
│  │ [action ▼]   [Low ▼]                                  │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ 태그 (쉼표로 구분)                                    │   │
│  │ [발표, 자동화, 슬라이드_____________________________]│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│                  [← 이전]  [미리보기 →]                      │
└─────────────────────────────────────────────────────────────┘
```

- **컴포넌트**: `<Step5DraftEditor draft={...} onChange={...} />`
- **핵심**: 모든 필드가 **AI 자동 채워진 상태**로 시작. 사용자는 빈칸 채울 필요 없이 검토/수정만.
- **상태**: `draft: ExtractedSkillNode` (편집 중)
- **API**: 없음 (클라이언트 상태)

### Step 6 — 미리보기 + 검토

```
┌─────────────────────────────────────────────────────────────┐
│ ✓ ✓ ✓ ✓ ✓   [6] 미리보기   7 완료                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  생성될 스킬을 확인하세요                                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 📊 발표 덱 자동 생성                                  │   │
│  │ ────────────────────────                              │   │
│  │ category: action  ·  risk: Low                        │   │
│  │ AI 분석 기반 발표 덱 자동 생성 스킬                   │   │
│  │                                                       │   │
│  │ 태그: 발표, 자동화, 슬라이드                          │   │
│  │ 기반 문서: PART04_핵심기술_재구성_v3.md               │   │
│  │                                                       │   │
│  │ ── 실행 지침 미리보기 ──                              │   │
│  │ # 발표 덱 생성 스킬                                   │   │
│  │ ## 사용 시점                                          │   │
│  │ ...                                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ⚠ 이 스킬은 DRAFT 상태로 저장됩니다.                       │
│  ⚠ 마켓플레이스 등록은 별도 "검토 제출" 단계가 필요해요.    │
│                                                             │
│                  [← 수정]  [DRAFT 저장 →]                    │
└─────────────────────────────────────────────────────────────┘
```

- **컴포넌트**: `<Step6Preview draft={...} sourceDoc={...} onConfirm={...} />`

### Step 7 — confirm → DRAFT 저장 → 완료

```
┌─────────────────────────────────────────────────────────────┐
│ ✓ ✓ ✓ ✓ ✓ ✓   [7] 완료                                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                          ✓                                  │
│                                                             │
│              스킬이 생성됐습니다!                            │
│              [DRAFT 뱃지]                                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 이름   발표 덱 자동 생성                              │   │
│  │ 설명   AI 분석 기반 발표 덱 자동 생성 스킬             │   │
│  │ 태그   [발표] [자동화] [슬라이드]                      │   │
│  │ ID     skill_abc123... (모노스페이스)                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│   [스킬 보기 →]  [새 스킬 만들기]  [마켓플레이스로 →]         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- **컴포넌트**: `<Step7Complete skill={...} />`
- **API**: `POST /api/v1/agents/skills_builder/confirm` (황대원 신규)
  - payload: `{ "source_type": "sop", "step": "confirm", "skills": [{ ...편집된 draft }] }`
  - 응답: `ResultFrame(payload.skill_ids)`

---

## 6. Backend API 매핑 (박아름이 정확히 아는 영역)

### 6.1 Skills Builder Agent (이미 구현됨, Modal sub-agent)

위치: `services/agents/agent-skills-builder/main.py`

```python
# SOP wizard 3단계 (ADR-0020 Q8 + 옵션 1 2단계 분리, 2026-06-04)
if source_type == "sop":
    step = payload.get("step", "metadata")
    if step == "metadata":
        document = DocumentBlock.model_validate(payload["document"])
        stream = use_case.extract_metadata(req.user_id, document, req.personal_memory)
    elif step == "detail":
        document = DocumentBlock.model_validate(payload["document"])
        stream = use_case.extract_detail(req.user_id, document, payload.get("meta", {}), req.personal_memory)
    elif step == "confirm":
        stream = use_case.confirm(req.user_id, payload.get("skills", []))
```

### 6.2 `BuildFromSOPUseCase` 동작 (이미 구현됨, 옵션 1 2단계 분리)

위치: `modules/ai_agent/application/agents/skills_builder/build_from_sop_use_case.py`

**extract_metadata** (1단계 — 카드 그리드용):
- 입력: `DocumentBlock + personal_memory`
- 처리: JSON prompt → `LLM.generate_structured(prompt, _ExtractedSkillNodeMetaList)` (메타 5필드만 요구)
- 출력: `ResultFrame(payload.skill_metas)` (사용자 카드 그리드용, 저장 X)
- LLM이 생성하는 필드 (`_ExtractedSkillNodeMeta`): `node_type / name / description / category / risk_level`

**extract_detail** (2단계 — 폼 prefill용, NEW 2026-06-04):
- 입력: `DocumentBlock + 선택된 meta dict + personal_memory`
- 처리: JSON prompt(target_skill_meta 명시) → `LLM.generate_structured(prompt, _ExtractedSkillNodeDetail)` (detail 5필드만 요구)
- 출력: `ResultFrame(payload.skill_detail)` — detail + `NodeSpecStaging`(메타의 category/risk_level + detail의 input/output 합친 결과)
- LLM이 생성하는 필드 (`_ExtractedSkillNodeDetail`): `inputs / outputs / required_connections / service_type / instructions(SKILL.md markdown)`

**confirm** (3단계):
- 입력: 사용자 편집된 `skills` 리스트 (메타 + detail 합쳐서 + 편집)
- 처리: `embed(description) + CreateDraftSkillUseCase → DRAFT 저장`
- 출력: `ResultFrame(payload.skill_ids)`

**왜 2단계 분리?** 한 응답에 노드 N개 × (긴 inputs/outputs JSON Schema + instructions markdown) 전체를 받으면 `max_tokens=4096`을 초과해 JSON EOF 잘림 발생(라인 220~250 col 부근). 메타만 받고 사용자 선택 후 detail 별도 호출로 응답당 토큰을 줄임. `_STRUCTURED_MAX_TOKENS`도 8192로 상향(안전망).

### 6.3 api_server SSE/JSON proxy 라우트 (이미 구현됨)

위치: `services/api_server/app/routers/skills.py`

```python
# wizard 1단계: 메타 추출 (SSE)
@router.post("/extract")
async def extract_skill_from_document(...) -> StreamingResponse:
    # source_document_id XOR template_code → DocumentBlock 합성/조회
    # → agent-skills-builder /v1/agent/route 프록시 (source_type="sop", step="metadata")
    # → 응답: SSE — payload.skill_metas (5필드)

# wizard 1.5단계: 선택된 메타의 detail 추출 (JSON)
@router.post("/extract/detail", response_model=ExtractSkillDetailResponse)
async def extract_skill_detail(...) -> ExtractSkillDetailResponse:
    # body: source(document_id|template_code) + meta(1차 선택분 5필드)
    # → agent-skills-builder 프록시 (step="detail", meta payload)
    # → SSE 봉투에서 ResultFrame collect → JSON 응답 (payload.skill_detail)
    # 에러: 422(LLM/입력 검증) / 502(응답 없음) / 503(client 미설정)

# wizard 3단계 (저장): POST /skills/personal (기존 라우트 재사용 — 박아름·황대원 합의)
```

---

## 7. 상태 관리 (Zustand 권장 — codebase 패턴)

```typescript
type WizardStep = 1 | 2 | 3 | 4 | 5 | 6 | 7;
type AnalyzingPhase = "structure" | "extraction" | "candidates";

// 1차 메타 (Step 2 응답, 카드 그리드용)
interface SkillMeta {
  node_type: string;
  name: string;
  description: string;
  category: "trigger" | "action" | "condition" | "transform" | "ai" | "integration" | "utility" | "output";
  risk_level: "Low" | "Medium" | "High" | "Restricted";
}

// 2차 detail (Step 4.5 응답, 폼 prefill용)
interface SkillDetail {
  node_type: string;                  // echo
  instructions: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  required_connections: string[];
  service_type: string | null;
  staging: Record<string, unknown>;   // NodeSpecStaging 직렬화 — POST /skills/personal에 그대로 전달
}

// 메타 + detail 합쳐 폼 prefill 후 편집 (Step 5)
interface DraftFormState extends SkillMeta, Omit<SkillDetail, "node_type" | "staging"> {
  staging: Record<string, unknown>;
}

interface WizardState {
  currentStep: WizardStep;
  document: DocumentResponse | null;     // Step 1
  analyzingPhase: AnalyzingPhase;        // Step 2
  skill_metas: SkillMeta[];              // Step 3 (메타만)
  selectedIndex: number | null;          // Step 4
  detail_loading: boolean;               // Step 4 (NEW — detail 호출 중)
  draft: DraftFormState | null;          // Step 5/6 (메타+detail 합치고 사용자 편집)
  createdSkillId: string | null;         // Step 7
  error: string | null;

  // actions
  setDocument: (doc: DocumentResponse) => void;
  startExtract: () => Promise<void>;       // Step 1 → 2 (SSE — skill_metas 수신)
  selectMeta: (index: number) => Promise<void>;  // Step 3 → 4 → 5 (detail JSON 호출 + draft 채움)
  updateDraft: (patch: Partial<DraftFormState>) => void;
  goToPreview: () => void;                 // Step 5 → 6
  confirmDraft: () => Promise<void>;       // Step 6 → 7 (POST /skills/personal)
  reset: () => void;
  goPrev: () => void;
  goNext: () => void;
}
```

---

## 8. 에러 처리

| 시나리오 | 처리 |
|---|---|
| Step 2 LLM fail (`E_LLM_GENERATION_FAILED`) | 에러 배너 + "다시 시도" 버튼 + 이전 단계로 |
| Step 2 후보 0건 (`E_NO_SKILLS_EXTRACTED`) | "이 문서에서 자동화 가능한 작업을 찾지 못했어요. 다른 문서를 시도해보세요" + Step 1로 |
| Step 7 DRAFT 저장 fail (500 등) | 에러 배너 + "다시 시도" 버튼 (Step 6 유지) |
| Network error | 일반 에러 메시지 + retry |
| 페이지 새로고침 | LocalStorage에 상태 백업 → 복원 시 currentStep 유지 |

---

## 9. 컴포넌트 분리 권장

```
src/app/skills/builder/
├── page.tsx                      # 진입점, WizardOrchestrator 렌더
├── WizardOrchestrator.tsx        # currentStep 기반 라우팅 + state machine
├── WizardProgress.tsx            # 상단 7단계 진행 표시
├── steps/
│   ├── Step1DocumentSelect.tsx
│   ├── Step2Analyzing.tsx
│   ├── Step3CandidatesGrid.tsx
│   ├── Step5DraftEditor.tsx
│   ├── Step6Preview.tsx
│   └── Step7Complete.tsx
└── stores/
    └── wizardStore.ts            # Zustand store
```

---

## 10. 출력 요구사항 (claude.ai에게)

- **React + TypeScript**
- **Tailwind CSS** (현재 codebase 사용 중)
- **Zustand** state management (codebase 패턴)
- **단계별 state machine** (currentStep: 1~7)
- **전 단계/다음 단계** 버튼 + 진행 표시 (1/7, 2/7 형식)
- **에러 처리** UI (ErrorBanner 컴포넌트 — codebase에 이미 있음 `@/components/common/ErrorBanner`)
- **각 단계 wireframe + 인터랙션 + API 호출 stub** 포함
- **실제 동작 가능한 prototype** (state + UI만, backend mock OK — `fetch` mock으로 LLM 응답 시뮬)
- **반응형** (데스크탑 위주, 최소 1024px 기준)

### Artifacts 출력 형식
- 단일 파일 또는 컴포넌트 분리 (위 §9 구조)
- mock API client 함수 포함 (`mockExtract()`, `mockConfirm()`)
- 실제 동작 가능한 7단계 흐름 (Step 1 → 7 끝까지 클릭 가능)

---

## 11. 참고 — 현재 staging URL + codebase 위치

- staging frontend: (박아름 별도로 알고 있음, 이 spec에 명시 X — 보안 정책)
- 현재 스킬빌더 (재설계 대상): `services/frontend/src/app/skills/builder/page.tsx` (347줄)
- 박아름 backend (이미 구현): `modules/ai_agent/application/agents/skills_builder/build_from_sop_use_case.py`
- Modal sub-agent: `services/agents/agent-skills-builder/main.py`
- 디자인 토큰: `services/frontend/src/app/globals.css` (또는 tailwind config)

---

## 12. 분담

- **박아름** (REQ-013): backend `BuildFromSOPUseCase` extract/confirm — ✅ 이미 구현
- **황대원** (REQ-010 + REQ-009):
  - `api_server/app/routers/agents.py`에 `/skills_builder/extract` + `/skills_builder/confirm` SSE proxy 라우트 신규
  - `frontend/src/app/skills/builder/` Wizard UI 7단계 구현 (본 spec 기반)
- **claude.ai (본 spec 결과)**: React 컴포넌트 prototype → 황대원이 styling 다듬어서 staging 적용

---

## 끝

이 spec 그대로 claude.ai (Max plan + Artifacts)에 paste + 스크린샷 2장 첨부 → Artifacts로 React 컴포넌트 prototype 받기 → 황대원에게 전달.
