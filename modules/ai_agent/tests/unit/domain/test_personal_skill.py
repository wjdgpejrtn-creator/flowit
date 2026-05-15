from uuid import uuid4

import pytest

from ai_agent.domain.entities.personal_skill import PersonalSkill


class TestPersonalSkill:
    def test_create_minimal(self):
        skill = PersonalSkill(
            user_id=uuid4(),
            skill_type="user",
            name="role",
            description="사용자 역할",
            body="데이터 엔지니어",
        )
        assert skill.embedding is None
        assert skill.updated_at.tzinfo is not None

    def test_all_skill_types(self):
        for stype in ("user", "feedback", "project", "reference"):
            skill = PersonalSkill(
                user_id=uuid4(),
                skill_type=stype,
                name="test",
                description="desc",
                body="body",
            )
            assert skill.skill_type == stype

    def test_invalid_skill_type_raises(self):
        with pytest.raises(Exception):
            PersonalSkill(
                user_id=uuid4(),
                skill_type="unknown",  # type: ignore[arg-type]
                name="test",
                description="desc",
                body="body",
            )

    def test_with_embedding(self):
        vec = [0.1] * 768
        skill = PersonalSkill(
            user_id=uuid4(),
            skill_type="feedback",
            name="pref",
            description="선호도",
            body="슬랙 알림 선호",
            embedding=vec,
        )
        assert skill.embedding == vec
        assert len(skill.embedding) == 768

    def test_immutable(self):
        skill = PersonalSkill(
            user_id=uuid4(),
            skill_type="user",
            name="test",
            description="desc",
            body="body",
        )
        with pytest.raises(Exception):
            skill.name = "changed"  # type: ignore[misc]
