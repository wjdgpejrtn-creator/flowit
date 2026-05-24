-- departments.sql: 데모용 팀 seed (경로 1 — departments 테이블을 팀 레지스트리로 사용).
-- '개발팀' = 단일 데모 팀. users.department_id 와 team_skills.team_id 가 이 UUID를 공유하며,
-- 스킬 마켓플레이스 team scope 인가(actor.department_id == skill.team_id)의 기준이 된다.
-- 회사(liftup)는 단일 테넌트라 별도 테이블 없이 앱 상수로 둔다.
INSERT INTO departments (department_id, name)
VALUES (
    '00000000-0000-0000-0000-0000000000d1',
    '개발팀'
) ON CONFLICT (name) DO NOTHING;
