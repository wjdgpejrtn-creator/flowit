"""_build_vision_llm seam — env-gated 안전 기본값 회귀 테스트 (REQ-007).

vision은 DOC_PARSER_VISION_ENABLED + LLM_BASE_URL이 갖춰질 때만 HTTP 비전 클라이언트를
반환한다. 그 전엔 None(텍스트 전용, 현 동작)으로 안전하게 degrade해야 한다.
Modal 토큰은 불필요(HTTP 경로) — worker가 이미 LLM_BASE_URL을 가짐.
"""
from src.adapters.document_tasks import _build_vision_llm
from src.adapters.vision_llm_client import HttpVisionLLM


def test_vision_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DOC_PARSER_VISION_ENABLED", raising=False)
    assert _build_vision_llm() is None


def test_vision_flag_off_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("DOC_PARSER_VISION_ENABLED", "false")
    assert _build_vision_llm() is None


def test_vision_enabled_without_llm_base_url_degrades_to_none(monkeypatch) -> None:
    monkeypatch.setenv("DOC_PARSER_VISION_ENABLED", "true")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    # URL 없으면 None으로 degrade (분석은 텍스트로 계속)
    assert _build_vision_llm() is None


def test_vision_enabled_with_url_returns_http_client(monkeypatch) -> None:
    monkeypatch.setenv("DOC_PARSER_VISION_ENABLED", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm-base.example.run.app")
    llm = _build_vision_llm()
    assert isinstance(llm, HttpVisionLLM)
    # /v1/generate 엔드포인트로 구성
    assert llm._url == "https://llm-base.example.run.app/v1/generate"


def test_http_client_builds_payload(monkeypatch) -> None:
    """generate가 prompt+kwargs(images/max_tokens 등)를 /v1/generate JSON으로 POST."""
    captured: dict = {}

    class _FakeResp:
        def raise_for_status(self) -> None:  # noqa: D401
            return None

        def json(self) -> dict:
            return {"generated_text": "표: 손익계산서"}

    class _FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

        def post(self, url, json):  # noqa: A002
            captured["url"] = url
            captured["json"] = json
            return _FakeResp()

    monkeypatch.setattr("src.adapters.vision_llm_client.httpx.Client", _FakeClient)
    llm = HttpVisionLLM("https://llm-base.example.run.app")
    result = llm.generate("describe", images=["data:image/png;base64,AAA"], max_tokens=1024)

    assert captured["url"].endswith("/v1/generate")
    assert captured["json"]["prompt"] == "describe"
    assert captured["json"]["images"] == ["data:image/png;base64,AAA"]
    assert captured["json"]["max_tokens"] == 1024
    assert result["generated_text"] == "표: 손익계산서"
