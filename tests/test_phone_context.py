"""extract_phones_with_context의 핵심 동작: 회사명·라벨 컨텍스트 밖의
번호(예: 잡코리아 푸터의 자체 번호)는 채택하지 않는다.
"""
from core.phone import extract_phones_with_context


def test_company_name_window_picks_nearby_number():
    text = "대형 채용 공고 모음 ... 쿠팡 풀필먼트 서비스 본사 대표번호 02-1234-5678 ... 기타 안내"
    out = extract_phones_with_context(text, company_name="쿠팡")
    assert "02-1234-5678" in out


def test_footer_unlabeled_number_far_from_company_name_excluded():
    """라벨 없이 회사명에서 멀리 떨어진 번호는 채택 안 됨.

    (잡포털 사이트 자체 번호처럼 '고객센터' 라벨이 동행하는 경우는
    이 컨텍스트 휴리스틱으로는 못 막고, 블랙리스트가 최종 방어선이다.
    그 부분은 test_blacklist.py에서 따로 검증함.)
    """
    text = (
        "쿠팡 회사 정보 영역. 채용 공고 모음. "
        + ("정보 " * 600)
        + "회사 카피라이트 표기 02-9999-9999"  # 라벨 없는 푸터 번호
    )
    out = extract_phones_with_context(text, company_name="쿠팡", radius=300)
    assert "02-9999-9999" not in out


def test_label_only_works_without_company_name():
    """회사명을 모르더라도 '대표전화' 라벨 옆 번호는 채택."""
    text = "기타 텍스트 ... 대표전화 031-555-1234 ... 다른 정보"
    out = extract_phones_with_context(text, company_name="")
    assert "031-555-1234" in out


def test_no_anchor_returns_empty():
    """회사명도 라벨도 없으면 빈 결과 (잘못된 번호보다 nothing이 안전)."""
    text = "그냥 임의의 번호 02-1111-2222가 본문에 있음"
    out = extract_phones_with_context(text, company_name="ABCXYZ")
    assert out == []


def test_company_name_normalization():
    """'쿠팡(주)'으로 검색해도 본문의 '쿠팡' 주변 번호를 찾는다."""
    text = "쿠팡 대표번호 02-1234-5678 입니다."
    out = extract_phones_with_context(text, company_name="(주)쿠팡")
    assert "02-1234-5678" in out
