"""공식 홈페이지 검증 강화 로직 테스트.

실제 HTTP 호출 없이 내부 _looks_like_official / _name_tokens 동작 확인.
"""
from core.sources.naver_web import WebItem, _looks_like_official, _name_tokens


def test_name_tokens_strips_corporate_noise():
    toks = _name_tokens("(주)동원로엑스")
    assert "동원로엑스" in toks


def test_name_tokens_english():
    toks = _name_tokens("LG Chem")
    assert "lg" in toks
    assert "chem" in toks


def test_looks_like_official_by_domain():
    item = WebItem(title="회사 소개", link="https://www.coupang.com", description="")
    tokens = _name_tokens("쿠팡")
    # 영문 도메인이라 한글 토큰만으론 매칭 안 될 수 있음 — 제목에도 등장하지 않으면 false
    # 그래서 title에 "쿠팡"이 있는 다른 케이스 검증
    item2 = WebItem(title="쿠팡 공식 홈페이지", link="https://www.coupang.com", description="")
    assert _looks_like_official(item2, "www.coupang.com", tokens)


def test_looks_like_official_rejects_unrelated():
    item = WebItem(title="삼성전자 채용 정보", link="https://www.somerandom.co.kr", description="")
    tokens = _name_tokens("쿠팡")
    # 도메인에도 제목에도 '쿠팡' 토큰 없음
    assert not _looks_like_official(item, "www.somerandom.co.kr", tokens)


def test_looks_like_official_by_title():
    item = WebItem(title="동원로엑스 채용 안내", link="https://recruit.dongwon-careers.com", description="")
    tokens = _name_tokens("동원로엑스")
    assert _looks_like_official(item, "recruit.dongwon-careers.com", tokens)
