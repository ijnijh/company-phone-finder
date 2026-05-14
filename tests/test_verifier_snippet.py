"""naver_snippet 소스 검증."""
from core.verifier import decide


def test_snippet_alone_labelled():
    res = decide({"naver_snippet": ["02-1234-5678"]})
    assert res.confidence == "검색결과확인"
    assert res.best_phone == "02-1234-5678"


def test_snippet_plus_homepage_verified():
    res = decide({
        "naver_snippet": ["02-1234-5678"],
        "homepage": ["02-1234-5678"],
    })
    assert res.confidence == "검증됨"


def test_snippet_outweighs_jobportal():
    """snippet (weight=2) > jobportal (weight=1)"""
    res = decide({
        "naver_snippet": ["02-1111-1111"],
        "jobkorea": ["02-9999-9999"],
    })
    assert res.best_phone == "02-1111-1111"


def test_llm_outweighs_snippet():
    """LLM (weight=4) > snippet (weight=2)"""
    res = decide({
        "llm": ["02-1111-1111"],
        "naver_snippet": ["02-9999-9999"],
    })
    assert res.best_phone == "02-1111-1111"
