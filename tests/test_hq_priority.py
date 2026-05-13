"""'본사'/'대표전화' 라벨 직후 번호 우선 추출 테스트.

동원로엑스 contact us 페이지처럼 본사+지점·센터 번호가 줄지어 박혀있을 때
본사만 골라내는지 확인.
"""
from core.phone import extract_hq_phones


def test_hq_label_picks_only_hq_number():
    text = """
    본사 02-6363-2600
    영업소 031-957-2445
    물류센터 031-634-9318
    경기지점 031-100-2000
    """
    out = extract_hq_phones(text, radius=60)
    assert "02-6363-2600" in out
    assert "031-957-2445" not in out
    assert "031-634-9318" not in out


def test_daepyo_label_picks_number():
    text = "대표전화 1588-1234 (지점 02-9999-9999는 제외)"
    out = extract_hq_phones(text, radius=60)
    assert "1588-1234" in out
    assert "02-9999-9999" not in out


def test_no_hq_label_returns_empty():
    """본사 라벨이 없으면 빈 결과 (회사명 컨텍스트 추출이 fallback)."""
    text = "그냥 본문 02-1234-5678 있어요"
    out = extract_hq_phones(text)
    assert out == []


def test_branch_label_after_hq_excluded():
    """본사 라벨 옆 번호 추출 시 지점·센터 라벨 옆 번호는 자동 제외(extract_phones 룰)."""
    text = "본사 02-6363-2600 지점 02-9999-9999"
    out = extract_hq_phones(text, radius=200)  # 윈도우 크게 잡아도
    assert "02-6363-2600" in out
    assert "02-9999-9999" not in out


def test_far_number_not_in_window():
    """본사 라벨에서 너무 멀리 떨어진 번호는 제외."""
    text = "본사" + (" 채움 " * 50) + "02-1234-5678"
    out = extract_hq_phones(text, radius=60)
    assert "02-1234-5678" not in out
