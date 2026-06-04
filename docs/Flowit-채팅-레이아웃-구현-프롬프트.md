# Flowit AI 채팅(Composer) 화면 — 구현 프롬프트

> 목적: `Flowit 채팅 레이아웃 샘플.html`의 디자인을 **픽셀/토큰 단위로 그대로** 실제 코드에 구현한다.
> 핵심 원칙: **"대화는 텍스트, 카드는 최소"** (ChatGPT·Gemini식). 채팅 화면에서 박스/말풍선/테두리 장식을 최소화하고, 시각적 무게는 *박스 장식 < 텍스트 가독성* 으로 둔다.

---

## 0. 가장 중요한 규칙 (반드시 100% 준수)

1. **유저 입력만 카드(말풍선)** — 사용자가 보낸 메시지만 오른쪽 정렬 갈색 말풍선(pill). 이게 화면에서 **유일한 채팅 말풍선**이다.
2. **AI 출력은 카드 없이 본문 텍스트로 흐른다** — 에이전트 작업과정(보안 검증·의도 분석·노드 검색 등), 일반 응답, 최종 컨펌(ConfirmCard) **전부** 말풍선/테두리/배경 박스를 두지 않고, 작은 AI 마커 + 평문으로 페이지에 그대로 출력. 진행 중 단계는 **흐릿한 텍스트 + 스피너 한 줄**.
3. **ConfirmCard도 문장으로** — 별도 카드 박스 없이 AI 본문 텍스트로 워크플로우 요약을 서술하되 **권한·위험도·확인 필요 값만 색/굵게**로 강조. 그 아래 저장·편집 액션만 가볍게.
4. **카드(선택지 UI)는 딱 두 순간에만 출력한다** ⚠️ *(이번 요구사항의 핵심 변경점)*
   - **(A) 스킬 선택할 때** — 사용자가 어떤 스킬/분기를 쓸지 고르는 순간
   - **(B) 마지막에 결과를 띄워줄 때** — 최종 산출물에 대해 사용자가 옵션을 고르는 순간
   - ❗ **노드 파라미터를 채우는 선택(예: 슬랙 채널 지정, 발송 시각 지정 등)은 카드로 띄우지 않는다.** 샘플 HTML에 있던 "채널 선택 카드"는 노드 파라미터 입력이므로 **실제 코드에서는 제거**한다. 파라미터 값은 ConfirmCard 본문 문장 안에서 *확인 필요 값*으로 강조해 보여주고, 수정이 필요하면 우측 캔버스의 **편집**으로 유도한다.
   - 즉, 현재 composer 코드의 흐름(스킬 선택 시 / 최종 결과 표시 시에만 옵션 선택)에 정확히 맞춘다.
5. **워크플로우 결과물은 우측 접힘 캔버스(사이드바)** — 평소 얇은 핸들, 클릭 시 펼침. 편집·실행 버튼은 캔버스 패널 **상단**. (현행 유지)
6. **색/타이포는 기존 Flowit 크림·브라운 토큰 그대로.**

---

## 1. 디자인 토큰 (그대로 사용)

```css
:root {
  --color-paper:        #FBF8F2;  /* 본문 배경 (크림) */
  --color-paper2:       #F3EDE3;  /* 옅은 표면 / 사이드바 배경 */
  --color-surface:      #FFFFFF;
  --color-ink:          #463A30;  /* 본문 텍스트 */
  --color-ink2:         #685949;  /* 보조 텍스트 */
  --color-ink3:         #766556;  /* 흐린 보조 (AA 유지) */
  --color-ink4:         #A2917F;  /* 비활성/placeholder/진행중 dim */
  --color-line:         #463A30;
  --color-line-soft:    #ECE3D6;  /* 카드/구분선 테두리 */
  --color-hl:           #FBEBDA;  /* 밝은 피치 (hover) */
  --color-hl2:          #F2D7BE;
  --color-coral-light:  #FDEEE0;  /* AI 마커 배경 / 선택됨 배경 */
  --color-accent:       #8A6240;  /* 메인 갈색 (유저 말풍선, 버튼) */
  --color-accent2:      #9A7150;
  --color-accent3:      #6E4E33;  /* 진갈색 (호버, 권한 강조) */
  --color-accent-coral: #E8945C;  /* 코랄 포인트 (마커/확인값/스피너) */
  --color-danger:       #C75146;
}
```

- **폰트**: 본문 `'Inter','Noto Sans KR', sans-serif`. 코드/식별자/타임스탬프는 `'JetBrains Mono'`(또는 시스템 mono).
- 한글 본문은 `word-break: keep-all;`(어절 단위 줄바꿈) 적용.
- 위험/스킬 priority 색은 기존 규칙 유지: High `#F97316`계열 점, Restricted `#DC2626` + lock, 보통/위험도 강조 `#C8860B`(앰버).

---

## 2. 전체 레이아웃

- 화면은 가로 2분할: **좌측 대화 컬럼(flex-1)** + **우측 접힘 캔버스(aside)**. 높이 `100vh`(상단 글로벌 헤더가 있으면 그만큼 제외), `overflow:hidden`.
- 대화 컬럼 내부는 세로 3단:
  1. (선택) 상단 얇은 세션 헤더 — 세션명 + 우측 히스토리/더보기 아이콘. `border-b border-line-soft/70`, 패딩 `px-6 py-3`.
  2. **스크롤 대화 영역** — `flex-1 overflow-y-auto`. 안쪽 콘텐츠는 **`max-width:720px; margin:0 auto; padding:32px 24px;`** 로 가운데 정렬(ChatGPT식 읽기 폭). 메시지 사이 세로 간격 `36px`(`space-y-9`).
  3. **하단 입력창** — 고정(`flex-shrink-0`), `max-width:720px` 가운데. 그 아래 회색 보조문구 한 줄.
- 스크롤바: 폭 7px, thumb `--color-hl2`, hover `--color-accent`, track 투명.

---

## 3. 메시지 타입별 마크업 규격

### 3-1. 유저 입력 (유일한 말풍선)
- 우측 정렬(`flex justify-end`). 말풍선:
  - 배경 `--color-accent`, 글자 `#FCF7EF`.
  - `border-radius: 20px; border-bottom-right-radius: 8px;`(우하단만 각짐 → 화자 방향).
  - 패딩 `10px 16px`, 폰트 `14.5px / weight 500 / line-height 1.6`, `max-width: 78%`.
  - 그림자 `0 2px 8px -2px rgba(70,58,48,.3)`.

### 3-2. AI 출력 (카드 없음, 마커 + 평문)
- 행 구조: `display:flex; gap:12px;`
  - **AI 마커**(좌측): `28px` 원형, 배경 `--color-coral-light`, 테두리 `1px --color-hl2`, 안에 `sparkles` 아이콘 `14px` 색 `--color-accent-coral`. 같은 화자의 연속 블록에서는 마커 자리만 비워 정렬 유지(빈 `28px` 박스).
  - **본문**(우측, `flex:1`): 배경/테두리/그림자 **전부 없음**. 페이지에 그냥 텍스트.
- **에이전트 작업과정 (완료 단계)**: 각 줄 `flex items-center gap-2`, 폰트 `12.5px / 700`, 색 `--color-ink3`(흐릿). 앞에 `check` 아이콘 `14px` 색 `--color-accent`. 강조 토큰(예: 분석 결과)만 `--color-ink`로.
  - 예: `✓ 보안 검증 완료 · 외부 전송 권한 확인됨` / `✓ 의도 분석 — 주간 리포트 자동화` / `✓ 노드 검색 — 3개 매칭`
- **진행 중 단계 (한 줄)**: `flex items-center gap-2`, 색 `--color-ink4`(dim), 앞에 **CSS 스피너**(아래) 한 개. 텍스트 끝에 `…`.
  - 스피너: `13px` 원, `border:2px solid --color-hl2; border-top-color: --color-accent-coral; border-radius:50%; animation: spin .7s linear infinite;`
- **일반 응답 본문**: `.ai-prose` — `font-size:14.5px; line-height:1.75; color:--color-ink; word-break:keep-all;` 문단 간격 `p + p { margin-top:10px; }`.
- **노드 체인 표기도 박스 없이 인라인**: mono 폰트 `12.5px`, 색 `--color-ink2`, 노드명 사이 화살표 `→`(색 `--color-ink4`). 예: `google_sheets_read → text_template → slack_notify`. (별도 배경 칩/보더 두지 말 것.)

### 3-3. ConfirmCard = 본문 문장 (카드 박스 금지)
- 위에 작은 라벨 줄: `sparkles`(14px coral) + `최종 확인`(11px/700/ink3, uppercase, letter-spacing) + 우측으로 늘어나는 `1px` 가로 구분선(`--color-line-soft`).
- 본문은 `.ai-prose`(15px 권장, line-height 1.8) 한~세 문단으로 **서술**. 강조는 다음 인라인 토큰만 사용:
  - **확인 필요 값**(`.em-val`): 색 `--color-accent-coral`, `font-weight:700`, `border-bottom:1.5px solid --color-hl2`. (예: 발송 시각, 대상 채널 등 사용자가 검토해야 할 파라미터 값)
  - **권한**(`.em-perm`): 색 `--color-accent3`, `font-weight:700`. (예: Google Sheets 읽기, Slack 메시지 쓰기)
  - **위험도**(`.em-risk`): 색 `#C8860B`, `font-weight:700`. (예: 보통/높음)
- 그 아래 **액션은 가볍게 두 개만**:
  - `저장하고 활성화` — `--color-accent` 배경, 흰 글자, `border-radius:12px`, 패딩 `8px 16px`, `12.5px/700`, 앞 `check` 아이콘.
  - `편집` — 테두리 `--color-line-soft` + 투명 배경, hover `--color-paper2`, 글자 `--color-ink2`, 앞 `edit-3` 아이콘. **클릭 시 우측 캔버스를 펼친다(openCanvas).**
- ❗ 노드 파라미터(채널/시각 등)는 여기 **문장 안 `.em-val`로만** 보여주고, 수정은 캔버스 편집으로. 별도 입력 카드/폼을 채팅에 띄우지 않는다.

### 3-4. 선택지 카드 — **스킬 선택 / 최종 결과 선택, 두 순간에만**
> 이게 채팅에서 유저 말풍선 외 등장하는 **유일한 카드(상호작용 surface)** 다. AI 마커 정렬을 따르되, 본문 자리에 카드를 둔다.

공통 규격:
- 컨테이너: `background:--color-surface; border:1px solid rgba(70,58,48,.15); border-radius:16px; padding:12px; box-shadow:0 4px 16px -8px rgba(70,58,48,.25);`
- 상단 라벨: `mouse-pointer-click` 아이콘(14px coral) + 안내문(11px/700/ink3 uppercase). 카드의 역할(선택해야 함)을 시각적으로 구분.
- 옵션 행(`.choice-opt`): `border:1px solid --color-line-soft; border-radius:12px; padding:10px 14px;` `transition:.15s`.
  - hover: `border-color:--color-accent-coral; background:--color-hl;`
  - 선택됨(`.is-picked`): `border-color:--color-accent; background:--color-coral-light;` + 우측 `check-circle-2`(accent) 표시.
- 옵션 여러 개는 **flex/grid + gap**(`gap:6px`)로 배치(인라인 흐름 금지).
- 카드 아래 작은 도움말 한 줄(10.5px/700/ink4) + `info` 아이콘 — "선택이 필요한 분기에서만 등장합니다." 류.

**언제 띄우나 (2곳):**
- **(A) 스킬 선택**: AI가 의도에 맞는 스킬/분기 후보를 제시. 각 옵션 = 스킬 아이콘 + 스킬명 + 짧은 설명(부제). 예: 여러 매칭 스킬 중 택1, 또는 "새로 만들기 / 기존 스킬 사용" 분기.
- **(B) 최종 결과 선택**: 산출물 표시 후 사용자가 고를 옵션. 예: 생성된 워크플로우 후보 택1, 또는 결과에 대한 분기 선택. 선택 즉시 우측 캔버스 결과물/ConfirmCard 본문에 반영.
- 선택을 마치면, 그 결과는 **유저 말풍선(3-1)** 으로 한 번 더 에코하거나(택1 결과 표시), 곧바로 다음 AI 본문으로 진행한다. (현행 composer 흐름에 맞춰 둘 중 택1.)
- 대안 표현: 동일 규격을 **중앙 모달 팝업**으로 띄워도 됨(선택 surface임을 더 강하게 구분하고 싶을 때). 모달일 경우 뒤 본문은 약간 dim 처리. *기본은 인라인 카드 권장.*

> ⚠️ **하지 말 것**: 채널/시간/수신자 등 *노드 파라미터 입력*을 위한 선택 카드. 이런 값은 ConfirmCard 문장의 `.em-val`로 노출 + 캔버스 편집으로만 수정.

---

## 4. 우측 접힘 캔버스 (현행 유지)

- `aside#canvas-panel`: `border-left:1px solid --color-line-soft; background:--color-paper2/40;` 폭 transition `width .32s cubic-bezier(.4,0,.2,1)`.
- **접힘(기본) — 폭 52px**: 전체를 덮는 세로 핸들 버튼.
  - 위에서부터: `chevron-left`(ink3, hover accent) → 세로 텍스트 `워크플로우 캔버스`(`writing-mode:vertical-rl;` 11px/700, letter-spacing 넓게) → 하단 `8px` 코랄 점(작업 있음 표시, `animate-pulse`).
  - hover 시 배경 살짝 진하게.
- **펼침 — 폭 320px**: `#canvas-body` 표시.
  - **상단 바**(`border-b`): 좌측 `chevron-right`(접기) + `워크플로우 결과물`(12px/700). 우측 **편집/실행 버튼**:
    - `편집` — 테두리 + 흰 배경, `edit-3` 아이콘, 11px/700.
    - `실행` — `--color-accent` 배경, 흰 글자, `play` 아이콘.
  - **본문**: 점격자 배경(`radial-gradient(#D8CBB8 1.2px, transparent 1.2px); background-size:18px 18px;`). 노드 칩들을 세로로 나열하고 사이에 `arrow-down`(ink4).
    - 노드 칩(`.node-chip`): `background:--color-surface; border:1px solid --color-line-soft; border-radius:12px; padding:12px;` 안에 `32px` 아이콘 박스(`bg:#F7F1E8`, 보더 line-soft) + 노드 표시명(12.5px/700) + 타입 식별자(10px mono ink4). High 위험은 우상단 `6px` 오렌지 점.
  - **하단 바**: `git-branch` + `N개 노드 · 초안 저장됨`(10px/700/ink4).
- JS 동작: `openCanvas()` → 폭 320px, 핸들 숨김, body flex 표시. `closeCanvas()` → 폭 52px, body 숨김, 핸들 표시. (ConfirmCard의 "편집" 버튼도 `openCanvas()` 호출.)

---

## 5. 하단 입력창

- `flex items-end gap-2`, 컨테이너 `background:#fff; border:1px solid --color-line-soft; border-radius:16px; padding:8px 12px; box-shadow:0 4px 16px -10px rgba(70,58,48,.35);` `focus-within:border-accent`.
- 좌측 `paperclip` 아이콘 버튼(첨부) → 가운데 `input`(14px/500, placeholder `--color-ink4`) → 우측 전송 버튼(`32px` 정사각, `--color-accent` 배경, 흰 `arrow-up`).
- 아래 가운데 보조문구(10px/700/ink4): "Flowit은 실수할 수 있어요. 권한이 필요한 작업은 항상 확인 후 실행됩니다." 류.

---

## 6. 토스트 (피드백)

- 하단 중앙 고정. 등장 시 `translateY(0)+opacity 1`, 2.2초 후 사라짐.
- 배경 `--color-accent3`, 흰 글자 13px/700, `border-radius:18px`, 좌측 `check-circle-2` 아이콘, 그림자 `0 14px 34px -10px rgba(70,52,35,.55)`.
- 사용처: 저장/활성화, 선택 완료 등.

---

## 7. 상호작용 정리 (의사코드)

```
on 사용자 전송:
  대화영역에 유저 말풍선 추가 (3-1)

on AI 처리 시작:
  AI 블록 추가 (마커 + 본문 컨테이너)
  완료 단계는 흐린 체크 줄로, 현재 단계는 dim 텍스트 + 스피너 한 줄 (3-2)

if 스킬 선택 분기 필요(A):
  본문 자리에 '선택지 카드' 렌더 (3-4) — 스킬 후보 목록
  사용자 선택 → (선택 결과를 유저 말풍선으로 에코하거나 다음 단계로)

... (노드 파라미터는 카드로 묻지 않음. AI가 추론/기본값으로 채우고 ConfirmCard 문장에서 확인값으로 노출) ...

on 결과 준비 완료:
  ConfirmCard를 '본문 문장'으로 출력 (3-3): 권한/위험도/확인필요값만 강조
  [저장하고 활성화] [편집] 액션
  우측 캔버스에 결과 노드 그래프 채움 (4)

if 최종 결과에 대한 선택 분기 필요(B):
  본문 자리에 '선택지 카드' 렌더 (3-4) — 결과 옵션
  선택 → ConfirmCard 본문/캔버스에 반영

on 편집 클릭: openCanvas()
on 저장 클릭: toast('워크플로우가 활성화되었습니다') + 상태 갱신
```

---

## 8. 수용 기준 (체크리스트)

- [ ] 채팅 화면의 **유일한 말풍선**은 우측 갈색 유저 입력뿐이다.
- [ ] AI의 모든 출력(작업과정·일반응답·ConfirmCard)에 **테두리/배경 박스/말풍선이 없다.**
- [ ] 진행 중 단계는 **dim 텍스트 + 스피너 한 줄**로 표시된다.
- [ ] ConfirmCard는 **문장 서술** + 권한/위험도/확인값 **인라인 강조**만, 그 아래 저장·편집 두 액션만 있다.
- [ ] **선택지 카드는 (A)스킬 선택, (B)최종 결과 선택 두 순간에만** 나타난다.
- [ ] **노드 파라미터 입력용 선택 카드는 어디에도 없다.**
- [ ] 우측 캔버스는 기본 52px 핸들, 클릭 시 320px 펼침, 상단에 편집/실행.
- [ ] 모든 색/폰트가 위 토큰과 일치한다.
- [ ] 옵션/버튼 그룹은 inline 흐름이 아니라 **flex/grid + gap**으로 배치된다.

---

### 참고
구현 기준 디자인 파일: `Flowit 채팅 레이아웃 샘플.html` (이 문서와 1:1 대응). 단, 위 4번(선택지 카드 출현 시점)과 "노드 파라미터 카드 제거"는 **이 프롬프트가 우선**한다.
