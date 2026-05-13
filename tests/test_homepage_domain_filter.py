"""is_excluded_homepage_domain — link 필드 검증 테스트.

네이버 지도가 link로 place.naver.com 같은 URL을 보낼 때 그것을 회사 홈페이지로
오인하지 않게 막는다.
"""
from core.sources.naver_web import is_excluded_homepage_domain


def test_naver_place_url_excluded():
    assert is_excluded_homepage_domain("https://place.naver.com/restaurant/123") is True
    assert is_excluded_homepage_domain("https://m.place.naver.com/abc") is True


def test_naver_search_url_excluded():
    assert is_excluded_homepage_domain("https://search.naver.com/?q=test") is True


def test_naver_blog_excluded():
    assert is_excluded_homepage_domain("https://blog.naver.com/foo/bar") is True


def test_news_domain_excluded():
    assert is_excluded_homepage_domain("https://www.chosun.com/article/123") is True


def test_jobportal_excluded():
    assert is_excluded_homepage_domain("https://www.jobkorea.co.kr/c/abc") is True


def test_normal_company_domain_passes():
    assert is_excluded_homepage_domain("https://www.dongwonloex.com") is False
    assert is_excluded_homepage_domain("https://www.ilogen.com") is False
    assert is_excluded_homepage_domain("https://www.coupanglogistics.com") is False


def test_empty_url_excluded():
    assert is_excluded_homepage_domain("") is True
    assert is_excluded_homepage_domain("not-a-url") is True
