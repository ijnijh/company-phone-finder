"""3차 강화된 홈페이지 추출 로직 테스트.

- JSON-LD telephone 파싱
- <a href="tel:..."> 추출
- 푸터 영역 직접 추출 (회사명/라벨 없이도 OK)
"""
from core.sources.company_homepage import (
    _extract_from_footer,
    _extract_jsonld_phones,
    _extract_tel_links,
)
from selectolax.parser import HTMLParser


def test_jsonld_organization_telephone():
    html = b"""
    <html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      "name": "Acme",
      "telephone": "+82-2-1234-5678"
    }
    </script>
    </head><body></body></html>
    """
    phones = _extract_jsonld_phones(html)
    assert "02-1234-5678" in phones


def test_jsonld_nested_telephone():
    html = b"""
    <html><body>
    <script type="application/ld+json">
    {"@graph": [{"@type":"LocalBusiness","telephone":"02-3333-4444"}]}
    </script>
    </body></html>
    """
    phones = _extract_jsonld_phones(html)
    assert "02-3333-4444" in phones


def test_tel_link_extraction():
    html = """
    <html><body>
      <a href="tel:0212345678">전화걸기</a>
      <a href="tel:+82-31-555-0000">지점</a>
      <a href="mailto:a@b.c">메일</a>
    </body></html>
    """
    tree = HTMLParser(html)
    phones = _extract_tel_links(tree)
    assert "02-1234-5678" in phones
    assert "031-555-0000" in phones


def test_footer_extracted_without_label():
    """푸터 영역의 번호는 라벨/회사명 없이도 채택."""
    html = """
    <html><body>
      <main>본문 내용...</main>
      <footer>
        <div class="copyright">(주)동원로엑스 02-6363-2600</div>
      </footer>
    </body></html>
    """
    tree = HTMLParser(html)
    phones = _extract_from_footer(tree)
    assert "02-6363-2600" in phones


def test_footer_excludes_fax_even_without_label_requirement():
    """푸터라도 FAX 키워드 옆 번호는 여전히 제외."""
    html = """
    <html><body>
      <footer>
        TEL 02-1111-2222 FAX 02-9999-9999
      </footer>
    </body></html>
    """
    tree = HTMLParser(html)
    phones = _extract_from_footer(tree)
    assert "02-1111-2222" in phones
    assert "02-9999-9999" not in phones


def test_no_footer_returns_empty():
    html = "<html><body><div>그냥 본문</div></body></html>"
    tree = HTMLParser(html)
    assert _extract_from_footer(tree) == []
