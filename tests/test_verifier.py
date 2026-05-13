from core.verifier import decide


def test_all_sources_agree():
    res = decide({
        "naver_local": ["02-1234-5678"],
        "homepage": ["02-1234-5678"],
        "jobkorea": ["02-1234-5678"],
        "saramin": ["02-1234-5678"],
    })
    assert res.best_phone == "02-1234-5678"
    assert res.confidence == "검증됨"
    assert set(res.sources) == {"naver_local", "homepage", "jobkorea", "saramin"}


def test_only_naver_local():
    res = decide({"naver_local": ["02-1234-5678"]})
    assert res.best_phone == "02-1234-5678"
    assert res.confidence == "지도확인"


def test_only_homepage_now_distinct_label():
    """이전엔 '의심'에 묻혔던 홈페이지 단독 케이스가 '홈페이지확인'으로 명확히 분리."""
    res = decide({"homepage": ["02-1234-5678"]})
    assert res.best_phone == "02-1234-5678"
    assert res.confidence == "홈페이지확인"


def test_only_jobkorea_labelled_jobportal():
    res = decide({"jobkorea": ["02-9999-9999"]})
    assert res.confidence == "잡포털확인"


def test_only_saramin_labelled_jobportal():
    res = decide({"saramin": ["02-9999-9999"]})
    assert res.confidence == "잡포털확인"


def test_two_jobportals_same_number_demoted():
    """잡코리아+사람인은 사실상 단일 출처(채용 DB 공유)이므로 자동 검증됨 불가.
    새 정책: '잡포털2중확인' 라벨로 격하."""
    res = decide({"jobkorea": ["02-1234-5678"], "saramin": ["02-1234-5678"]})
    assert res.confidence == "잡포털2중확인"


def test_empty_returns_not_found():
    res = decide({})
    assert res.best_phone == ""
    assert res.confidence == "찾지못함"


def test_tie_breaker_naver_local_wins():
    # 동일 점수에서 네이버 지도가 들어있는 후보가 우선
    res = decide({
        "naver_local": ["02-1234-5678"],   # 지도 단독 score=3
        "homepage": ["02-9999-9999"],      # 홈페이지 단독 score=2
    })
    assert res.best_phone == "02-1234-5678"
    assert res.confidence == "지도확인"


def test_two_distinct_sources_verified():
    res = decide({"naver_local": ["02-1234-5678"], "homepage": ["02-1234-5678"]})
    assert res.confidence == "검증됨"
    assert "naver_local" in res.sources and "homepage" in res.sources
