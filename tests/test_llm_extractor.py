"""LLM extractor 테스트 — anthropic SDK monkeypatch로 외부 호출 차단."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.sources import llm_extractor


def _make_fake_response(text: str, cache_read: int = 0, cache_write: int = 0):
    """anthropic.Anthropic().messages.create()의 응답 구조를 흉내내는 fake."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    usage = MagicMock()
    usage.input_tokens = 500
    usage.output_tokens = 12
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_write

    resp = MagicMock()
    resp.content = [block]
    resp.usage = usage
    return resp


def test_no_api_key_returns_none(monkeypatch):
    """ANTHROPIC_API_KEY가 없으면 빈 결과."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_extractor.extract_phone_with_llm("회사", "본사 02-1234-5678") is None


def test_is_available_false_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_extractor.is_available() is False


def test_is_available_true_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm_extractor.is_available() is True


def test_empty_inputs_return_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm_extractor.extract_phone_with_llm("", "텍스트") is None
    assert llm_extractor.extract_phone_with_llm("회사", "") is None
    assert llm_extractor.extract_phone_with_llm("회사", "   ") is None


def test_returns_phone_when_model_responds(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_fake_response("02-1234-5678")
    monkeypatch.setattr(
        llm_extractor.anthropic, "Anthropic", lambda **kw: fake_client
    )
    result = llm_extractor.extract_phone_with_llm("현대건설", "본사 02-1234-5678 ...")
    assert result == "02-1234-5678"


def test_returns_none_for_eobseum_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_fake_response("없음")
    monkeypatch.setattr(
        llm_extractor.anthropic, "Anthropic", lambda **kw: fake_client
    )
    result = llm_extractor.extract_phone_with_llm("회사", "확신 없는 페이지")
    assert result is None


def test_extracts_phone_from_verbose_response(monkeypatch):
    """모델이 가끔 '답변: 02-...' 같이 답해도 정규식 추출로 잡아냄."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_fake_response("답변: 1588-9988입니다.")
    monkeypatch.setattr(
        llm_extractor.anthropic, "Anthropic", lambda **kw: fake_client
    )
    result = llm_extractor.extract_phone_with_llm("로젠택배", "텍스트")
    assert result == "1588-9988"


def test_authentication_error_returns_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-bad")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = llm_extractor.anthropic.AuthenticationError(
        message="bad key",
        response=MagicMock(status_code=401),
        body=None,
    )
    monkeypatch.setattr(
        llm_extractor.anthropic, "Anthropic", lambda **kw: fake_client
    )
    result = llm_extractor.extract_phone_with_llm("회사", "텍스트")
    assert result is None


def test_long_input_is_truncated(monkeypatch):
    """입력 텍스트는 _MAX_INPUT_CHARS로 자르고 API에 보냄."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_fake_response("02-1234-5678")
    monkeypatch.setattr(
        llm_extractor.anthropic, "Anthropic", lambda **kw: fake_client
    )

    long_text = "가" * 100_000  # 10만 자
    llm_extractor.extract_phone_with_llm("회사", long_text)

    # 호출 시 user message의 내용 길이가 _MAX_INPUT_CHARS 안에 들어와야 함
    call_kwargs = fake_client.messages.create.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    # truncate 적용 확인 — 본문 텍스트는 12000자 이하
    assert long_text[:llm_extractor._MAX_INPUT_CHARS] in user_content
    assert long_text not in user_content  # 전체 100K는 안 들어감


def test_system_prompt_has_cache_control(monkeypatch):
    """시스템 프롬프트에 cache_control이 적용되어야 캐싱 활성화."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_fake_response("02-1234-5678")
    monkeypatch.setattr(
        llm_extractor.anthropic, "Anthropic", lambda **kw: fake_client
    )
    llm_extractor.extract_phone_with_llm("회사", "본사 02-1234-5678")

    call_kwargs = fake_client.messages.create.call_args.kwargs
    system = call_kwargs["system"]
    assert isinstance(system, list)
    assert system[0].get("cache_control") == {"type": "ephemeral"}
    assert system[0].get("type") == "text"


def test_model_is_haiku(monkeypatch):
    """가장 저렴한 Haiku 4.5 모델 사용."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_fake_response("02-1234-5678")
    monkeypatch.setattr(
        llm_extractor.anthropic, "Anthropic", lambda **kw: fake_client
    )
    llm_extractor.extract_phone_with_llm("회사", "본사 02-1234-5678")

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5"
