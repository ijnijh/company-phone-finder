"""LLM 소스가 verifier의 권위 소스로 동작하는지 검증."""
from core.verifier import decide


def test_llm_alone_labelled_ai():
    """LLM 단독 결과는 'AI확인' 라벨."""
    res = decide({"llm": ["02-1234-5678"]})
    assert res.confidence == "AI확인"
    assert res.best_phone == "02-1234-5678"


def test_llm_plus_homepage_verified():
    """LLM + 홈페이지 일치 → 검증됨."""
    res = decide({"llm": ["02-1234-5678"], "homepage": ["02-1234-5678"]})
    assert res.confidence == "검증됨"


def test_llm_plus_naver_local_verified():
    res = decide({"llm": ["02-1234-5678"], "naver_local": ["02-1234-5678"]})
    assert res.confidence == "검증됨"


def test_llm_outweighs_jobportal():
    """LLM 결과(weight=4)가 잡포털(weight=1)보다 우선."""
    res = decide({
        "llm": ["02-1111-1111"],
        "jobkorea": ["02-9999-9999"],
    })
    assert res.best_phone == "02-1111-1111"
