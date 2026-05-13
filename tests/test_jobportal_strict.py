"""잡포털 회사명 검증이 본문 광고 노이즈를 통과시키지 않는지 확인."""
from selectolax.parser import HTMLParser

from core.sources.jobkorea import _strict_company_tokens, _verify_company_match


def test_token_short_prefix_not_included():
    """약칭(앞 2자)은 우연 매칭이 잦아 토큰에서 제외."""
    toks = _strict_company_tokens("쿠팡로지스틱스서비스")
    assert "쿠팡" not in toks  # 2글자 약칭 차단
    assert "쿠팡로지스틱스서비스" in toks
    assert "쿠팡로" in toks  # 3글자 접두는 의미있어 허용


def test_body_text_advertising_no_longer_passes():
    """본문에 '쿠팡' 광고 텍스트가 있어도 title/h1에 없으면 거부."""
    html = """
    <html>
      <head><title>나이스정보통신 채용공고</title></head>
      <body>
        <h1>나이스정보통신</h1>
        <div>관련 회사: 쿠팡, 마켓컬리, 11번가도 채용 중</div>
      </body>
    </html>
    """
    tree = HTMLParser(html)
    assert _verify_company_match(tree, "쿠팡로지스틱스서비스") is False


def test_title_match_passes():
    html = """
    <html>
      <head><title>쿠팡로지스틱스서비스 채용 | 잡코리아</title></head>
      <body><h1>다른회사</h1></body>
    </html>
    """
    tree = HTMLParser(html)
    assert _verify_company_match(tree, "쿠팡로지스틱스서비스") is True


def test_h1_match_passes():
    html = """
    <html>
      <head><title>잡코리아 채용공고</title></head>
      <body><h1>쿠팡로지스틱스서비스 주식회사</h1></body>
    </html>
    """
    tree = HTMLParser(html)
    assert _verify_company_match(tree, "쿠팡로지스틱스서비스") is True
