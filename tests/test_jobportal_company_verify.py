"""잡포털 회사명 강제 검증 테스트.

쿠팡로지스틱스서비스 검색 시 잡코리아가 '나이스정보통신' 페이지를 1위로 반환하던
실제 케이스를 재현하고, 우리 검증 로직이 그것을 폐기하는지 확인한다.
"""
from selectolax.parser import HTMLParser

from core.sources.jobkorea import _company_tokens as jk_tokens
from core.sources.jobkorea import _verify_company_match as jk_verify
from core.sources.saramin import _company_tokens as sa_tokens
from core.sources.saramin import _verify_company_match as sa_verify


def test_company_tokens_extract_main_words():
    toks = jk_tokens("쿠팡로지스틱스서비스")
    assert "쿠팡로지스틱스서비스" in toks
    assert "쿠" in toks or "쿠팡" in toks  # 약칭 토큰


def test_jobkorea_verify_rejects_mismatched_company():
    """검색어 '쿠팡로지스틱스서비스' → 페이지가 '나이스정보통신' → False."""
    html = """
    <html>
      <head><title>나이스정보통신 채용공고</title></head>
      <body>
        <h1 class="company-name">나이스정보통신</h1>
        <div>본사 02-2122-8000</div>
      </body>
    </html>
    """
    tree = HTMLParser(html)
    assert jk_verify(tree, "쿠팡로지스틱스서비스") is False


def test_jobkorea_verify_accepts_matched_company():
    html = """
    <html>
      <head><title>쿠팡로지스틱스서비스 채용공고 | 잡코리아</title></head>
      <body>
        <h1>쿠팡로지스틱스서비스 주식회사</h1>
        <div>본사 02-1234-5678</div>
      </body>
    </html>
    """
    tree = HTMLParser(html)
    assert jk_verify(tree, "쿠팡로지스틱스서비스") is True


def test_saramin_verify_mirror():
    html_mismatch = """<html><head><title>다른회사</title></head><body><h1>다른회사</h1></body></html>"""
    html_match = """<html><head><title>쿠팡로지스틱스</title></head><body><h1>쿠팡로지스틱스</h1></body></html>"""
    assert sa_verify(HTMLParser(html_mismatch), "쿠팡로지스틱스") is False
    assert sa_verify(HTMLParser(html_match), "쿠팡로지스틱스") is True


def test_partial_match_via_short_prefix():
    """긴 이름의 약칭(앞 2~3글자)이 페이지에 등장하면 통과."""
    html = """
    <html>
      <head><title>로젠 채용 정보</title></head>
      <body><h1>로젠택배</h1></body>
    </html>
    """
    tree = HTMLParser(html)
    # 검색어가 "로젠택배" → 토큰에 "로젠택배" + "로젠" + "로젠" 등 포함 → 매칭
    assert jk_verify(tree, "로젠택배") is True
