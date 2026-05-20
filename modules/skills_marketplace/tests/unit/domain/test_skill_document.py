from uuid import uuid4

from skills_marketplace.domain.entities import SkillDocument


def test_skill_document_minimal():
    doc = SkillDocument(
        skill_id=uuid4(),
        name="ecommerce-cart-abandonment-recovery",
        description="장바구니 이탈 N시간 후 자동 회복 메일 발송",
        instructions="## When to use\n장바구니 이탈 시...\n## Steps\n1. ...",
    )
    assert doc.name == "ecommerce-cart-abandonment-recovery"
    assert doc.scripts == []
    assert doc.templates == []


def test_skill_document_with_scripts_templates():
    doc = SkillDocument(
        skill_id=uuid4(),
        name="skill-name",
        description="설명",
        instructions="본문",
        scripts=[{"path": "run.py", "content": "print('hi')"}],
        templates=[{"path": "tpl.md", "content": "# {{title}}"}],
    )
    assert len(doc.scripts) == 1
    assert doc.scripts[0]["path"] == "run.py"


def test_skill_document_store_port_is_abc():
    from abc import ABC

    from skills_marketplace.domain.ports import SkillDocumentStore

    assert issubclass(SkillDocumentStore, ABC)
    # 추상 메서드 미구현 시 인스턴스화 불가
    import pytest

    with pytest.raises(TypeError):
        SkillDocumentStore()
