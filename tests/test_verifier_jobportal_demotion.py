"""잡포털 2중 일치를 자동 검증됨으로 격상하지 않는 룰 테스트."""
from core.verifier import decide


def test_two_jobportals_now_demoted_label():
    """잡코리아+사람인 동일 번호는 '검증됨' 아닌 '잡포털2중확인' 라벨."""
    res = decide({"jobkorea": ["02-1234-5678"], "saramin": ["02-1234-5678"]})
    assert res.confidence == "잡포털2중확인"


def test_jobportal_plus_authority_still_verified():
    """권위 소스(지도 또는 홈페이지)가 끼면 '검증됨'."""
    res = decide({
        "naver_local": ["02-1234-5678"],
        "jobkorea": ["02-1234-5678"],
    })
    assert res.confidence == "검증됨"


def test_homepage_plus_jobkorea_verified():
    res = decide({
        "homepage": ["02-1234-5678"],
        "jobkorea": ["02-1234-5678"],
    })
    assert res.confidence == "검증됨"
