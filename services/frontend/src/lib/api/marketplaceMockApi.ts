/**
 * 마켓플레이스 목(mock) API 레이어 — 2단계(프론트 우선).
 *
 * 시안(Flowit.html)의 MARKET_SKILLS 시드와 라이프사이클 전환을 인메모리로 재현한다.
 * 함수 시그니처는 기존 API 레이어(skillApi.ts) 패턴과 동일한 async 형태라,
 * 다음 단계에서 실제 백엔드(skills_marketplace, REQ-013) 엔드포인트로의 교체가
 * 이 모듈 내부에 국한된다.
 *
 * 영속 범위: 모듈 레벨 인메모리 — 세션(탭 전환) 동안 유지되고 새로고침 시 시드로 리셋.
 */

export type MockSkillState = 'draft' | 'review' | 'approved' | 'published' | 'archived';
export type MockScope = 'personal' | 'team' | 'company';

/** [라벨, 배경색, 글자색] */
export type MockTag = [label: string, bg: string, fg: string];

export interface MockSkill {
  id: string;
  name: string;
  desc: string;
  tags: MockTag[];
  version: string;
  meta: string;
  state: MockSkillState;
  /** 내가 소유한(게시한) 스킬인지 — Personal published 카드의 보관 버튼 노출 */
  owner?: boolean;
  /** 게시 스킬 사용 횟수 표시 */
  uses?: string;
  /** 남의 스킬을 내 워크플로우에 도입했는지 */
  added?: boolean;
  scope?: 'Team' | 'Company';
}

type Seed = Record<MockScope, MockSkill[]>;

function seed(): Seed {
  return {
    personal: [
      { id: 'personal-0', name: '슬랙 통합 리포트 마스터', desc: '지정 채널에 일간 주요 실적·장애 내역을 요약 브리핑합니다.', tags: [['마케팅', '#EAF1FB', '#3B73C4'], ['Slack', '#FBE9D8', '#C8860B']], version: 'v0.3', meta: '수정 12분 전', state: 'draft' },
      { id: 'personal-1', name: '문서 자동 분류 봇', desc: '업로드된 PDF를 유형별로 자동 태깅하여 보관함에 정리합니다.', tags: [['문서', '#F1ECE4', '#9C8B7B'], ['OCR', '#E7F6EF', '#10B981']], version: 'v0.3', meta: '요청 1시간 전', state: 'review' },
      { id: 'personal-2', name: '주간 광고 성과 다이제스트', desc: '채널별 광고 지표를 취합해 매주 월요일 요약 메일을 발송합니다.', tags: [['마케팅', '#EAF1FB', '#3B73C4'], ['Ads', '#FBE9D8', '#C8860B']], version: 'v1.0', meta: '승인 방금 전', state: 'approved' },
      { id: 'personal-3', name: '경쟁사 가격 모니터링', desc: '지정 상품군의 외부 가격 변동을 추적해 변화 시 알림을 보냅니다.', tags: [['리서치', '#EAF1FB', '#3B73C4'], ['크롤링', '#F1ECE4', '#9C8B7B']], version: 'v1.2', meta: '게시 2일 전', state: 'published', owner: true, uses: '1,420회' },
    ],
    team: [
      { id: 'team-0', name: '인사 정보 ERP 자동 기입봇', desc: '신입 사원 입사 문서 PDF를 자동 인식하여 사내 ERP에 등록합니다.', tags: [['업무효율', '#E7F6EF', '#10B981'], ['ERP', '#F1ECE4', '#9C8B7B']], version: 'v2.1', meta: 'by 민수진님 · 890회', state: 'published', owner: false, scope: 'Team' },
      { id: 'team-1', name: '회의록 액션아이템 추출', desc: '회의 녹취록에서 담당자·기한이 있는 할 일을 자동 정리합니다.', tags: [['생산성', '#EAF1FB', '#3B73C4'], ['요약', '#FBE9D8', '#C8860B']], version: 'v1.3', meta: 'by 박서연님 · 612회', state: 'published', owner: false, scope: 'Team' },
      { id: 'team-2', name: '경쟁사 광고 효율 모니터링', desc: '지정 도메인의 외부 마케팅 집행 효율 트렌드를 추적·요약합니다.', tags: [['마케팅', '#EAF1FB', '#3B73C4'], ['광고', '#F1ECE4', '#9C8B7B']], version: 'v1.5', meta: 'by 그로스팀 · 530회', state: 'published', owner: false, scope: 'Team', added: true },
    ],
    company: [
      { id: 'company-0', name: '전사 KPI 일일 브리핑', desc: '매일 아침 부서별 핵심 지표를 취합해 경영진 채널에 자동 발송합니다.', tags: [['인기', '#FBE9D8', '#C8860B'], ['리포트', '#EAF1FB', '#3B73C4']], version: 'v3.4', meta: 'by 이준호님 · 2,310회', state: 'published', owner: false, scope: 'Company' },
      { id: 'company-1', name: '사내 규정 Q&A 어시스턴트', desc: '취업규칙·복리후생 문서를 학습해 구성원 질문에 즉시 답변합니다.', tags: [['HR', '#E7F6EF', '#10B981'], ['지식', '#F1ECE4', '#9C8B7B']], version: 'v2.0', meta: 'by 피플팀 · 4,180회', state: 'published', owner: false, scope: 'Company' },
      { id: 'company-2', name: '보안 이상징후 일일 점검', desc: '접근 로그를 분석해 비정상 패턴을 탐지하고 보안팀에 리포트합니다.', tags: [['보안', '#FBEAE8', '#C75146'], ['모니터링', '#EAF1FB', '#3B73C4']], version: 'v4.1', meta: 'by 보안팀 · 1,070회', state: 'published', owner: false, scope: 'Company' },
    ],
  };
}

let store: Seed = seed();

/** 테스트/리셋용 — 시드 상태로 되돌린다. */
export function __resetMarketplaceMock(): void {
  store = seed();
}

function clone(s: MockSkill): MockSkill {
  return { ...s, tags: s.tags.map((t) => [...t] as MockTag) };
}

function findById(id: string): { skill: MockSkill; arr: MockSkill[]; index: number } | null {
  for (const scope of Object.keys(store) as MockScope[]) {
    const arr = store[scope];
    const index = arr.findIndex((s) => s.id === id);
    if (index > -1) return { skill: arr[index], arr, index };
  }
  return null;
}

// ── 조회 ───────────────────────────────────────────────────────────────────

export async function listSkills(scope: MockScope): Promise<MockSkill[]> {
  return store[scope].map(clone);
}

// ── 라이프사이클 전환 (시안 transition 로직 그대로) ──────────────────────────

export async function submitReview(id: string): Promise<void> {
  const f = findById(id);
  if (!f) return;
  f.skill.state = 'review';
  f.skill.meta = '요청 방금 전';
}

export async function requestPublish(id: string): Promise<void> {
  const f = findById(id);
  if (!f) return;
  f.skill.state = 'published';
  f.skill.owner = true;
  f.skill.uses = '0회';
  f.skill.meta = '게시 방금 전';
}

export async function deleteSkill(id: string): Promise<void> {
  const f = findById(id);
  if (!f) return;
  f.arr.splice(f.index, 1);
}

export async function archiveSkill(id: string): Promise<void> {
  const f = findById(id);
  if (!f) return;
  f.skill.state = 'archived';
  f.skill.meta = '보관 방금 전';
}

export async function restoreSkill(id: string): Promise<void> {
  const f = findById(id);
  if (!f) return;
  f.skill.state = 'published';
  f.skill.owner = true;
  f.skill.meta = '복원 방금 전';
}

export async function addToWorkflow(id: string): Promise<void> {
  const f = findById(id);
  if (!f) return;
  f.skill.added = true;
}
