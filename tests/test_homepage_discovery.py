"""홈페이지 contact 링크 동적 탐색 테스트.

실제 HTTP 호출 없이, HTMLParser와 _discover_contact_urls를 직접 점검.
"""
from selectolax.parser import HTMLParser

from core.sources.company_homepage import _discover_contact_urls


def test_korean_text_link_discovered():
    """'연락처' 한글 텍스트 링크가 우선 탐지되어야 한다."""
    html = """
    <html><body>
    <nav>
      <a href="/about.html">회사소개</a>
      <a href="/board/list.php?p=contact">연락처</a>
      <a href="https://other-domain.com/abc">외부 도메인</a>
    </nav>
    </body></html>
    """
    tree = HTMLParser(html)
    urls = _discover_contact_urls(tree, "https://www.dongwonloex.com/main")
    # 동일 도메인 + 연락처 텍스트 우선
    assert any("/board/list.php?p=contact" in u for u in urls)
    # 다른 도메인은 제외
    assert all("other-domain.com" not in u for u in urls)


def test_contact_in_href_only():
    """텍스트에 키워드는 없어도 href에 'contact'가 있으면 탐지."""
    html = """
    <html><body>
    <a href="/contact-us">바로가기</a>
    </body></html>
    """
    tree = HTMLParser(html)
    urls = _discover_contact_urls(tree, "https://example.com/")
    assert any("/contact-us" in u for u in urls)


def test_company_intro_link_picked():
    """'회사소개' 같은 일반적 한글 메뉴도 잡힘."""
    html = """
    <html><body>
    <ul><li><a href="/intro/company">회사소개</a></li></ul>
    </body></html>
    """
    tree = HTMLParser(html)
    urls = _discover_contact_urls(tree, "https://example.com/")
    assert any("/intro/company" in u for u in urls)


def test_ignores_anchor_and_js_links():
    html = """
    <html><body>
    <a href="#section">앵커</a>
    <a href="javascript:void(0)">자스</a>
    <a href="mailto:a@b.c">메일</a>
    <a href="tel:0212345678">전화</a>
    </body></html>
    """
    tree = HTMLParser(html)
    urls = _discover_contact_urls(tree, "https://example.com/")
    assert urls == []
