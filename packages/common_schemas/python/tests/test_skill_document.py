from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.skill_document import SkillDocument


class TestSkillDocument:
    def test_create_minimal(self):
        doc = SkillDocument(
            skill_id=uuid4(),
            name="ecommerce-cart-abandonment-recovery",
            description="장바구니 이탈 N시간 후 자동 회복 메일 발송",
            instructions="## When to use\n장바구니 이탈 시...\n## Steps\n1. ...",
        )
        assert doc.name == "ecommerce-cart-abandonment-recovery"

    def test_scripts_templates_default_empty(self):
        doc = SkillDocument(
            skill_id=uuid4(),
            name="skill-name",
            description="설명",
            instructions="본문",
        )
        assert doc.scripts == []
        assert doc.templates == []

    def test_both_instructions_optional(self):
        """노드 지침(instructions)·composer 지침(composer_instructions) 둘 다 optional (#372 detail 3)."""
        doc = SkillDocument(skill_id=uuid4(), name="n", description="d")
        assert doc.instructions == ""
        assert doc.composer_instructions == ""

    def test_composer_instructions_set(self):
        doc = SkillDocument(
            skill_id=uuid4(),
            name="n",
            description="d",
            composer_instructions="이 스킬은 LLM 노드 + Email 노드가 필수입니다.",
        )
        assert doc.composer_instructions.startswith("이 스킬은 LLM 노드")
        assert doc.instructions == ""

    def test_with_scripts_and_templates(self):
        doc = SkillDocument(
            skill_id=uuid4(),
            name="skill-name",
            description="설명",
            instructions="본문",
            scripts=[{"path": "run.py", "content": "print('hi')"}],
            templates=[{"path": "tpl.md", "content": "# {{title}}"}],
        )
        assert doc.scripts[0]["path"] == "run.py"
        assert doc.templates[0]["path"] == "tpl.md"

    def test_frozen(self):
        doc = SkillDocument(
            skill_id=uuid4(),
            name="skill-name",
            description="설명",
            instructions="본문",
        )
        with pytest.raises(ValidationError):
            doc.name = "mutated"

    def test_skill_id_required(self):
        with pytest.raises(ValidationError):
            SkillDocument(name="n", description="d", instructions="i")

    def test_instructions_optional_defaults_empty(self):
        # instructions는 더 이상 필수 아님 (#372 — composer 지침만 있는 스킬 허용)
        doc = SkillDocument(skill_id=uuid4(), name="n", description="d")
        assert doc.instructions == ""

    def test_invalid_skill_id_rejected(self):
        with pytest.raises(ValidationError):
            SkillDocument(
                skill_id="not-a-uuid",
                name="n",
                description="d",
                instructions="i",
            )

    def test_is_common_schemas_class(self):
        from common_schemas import SkillDocument as CSSkillDocument

        assert SkillDocument is CSSkillDocument
