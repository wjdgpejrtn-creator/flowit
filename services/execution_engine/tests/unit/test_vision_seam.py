"""_build_vision_llm seam — env-gated 안전 기본값 회귀 테스트 (REQ-007).

vision은 워커에 Modal 토큰이 주입되고 DOC_PARSER_VISION_ENABLED가 켜질 때만 활성.
그 전엔 None(텍스트 전용, 현 동작)으로 안전하게 degrade해야 한다.
"""
from src.adapters.document_tasks import _build_vision_llm


def test_vision_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DOC_PARSER_VISION_ENABLED", raising=False)
    assert _build_vision_llm() is None


def test_vision_flag_off_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("DOC_PARSER_VISION_ENABLED", "false")
    assert _build_vision_llm() is None


def test_vision_enabled_without_modal_token_degrades_to_none(monkeypatch) -> None:
    monkeypatch.setenv("DOC_PARSER_VISION_ENABLED", "true")
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    # 토큰 없으면 Modal 클라이언트를 만들지 않고 None으로 degrade (분석은 텍스트로 계속)
    assert _build_vision_llm() is None


def test_vision_enabled_partial_token_degrades_to_none(monkeypatch) -> None:
    monkeypatch.setenv("DOC_PARSER_VISION_ENABLED", "1")
    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-xxx")
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    assert _build_vision_llm() is None
