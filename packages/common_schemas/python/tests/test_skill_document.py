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

    def test_instructions_required(self):
        with pytest.raises(ValidationError):
            SkillDocument(skill_id=uuid4(), name="n", description="d")

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
