"""FAX·부서 직통 라벨 제외 동작 테스트."""
from core.phone import extract_phones


def test_fax_label_excludes_number():
    """TEL과 FAX가 나란히 있을 때 FAX 번호는 제외, TEL만 추출."""
    text = "TEL 02-1234-5678 FAX 02-1234-9999"
    out = extract_phones(text)
    assert "02-1234-5678" in out
    assert "02-1234-9999" not in out


def test_korean_fax_label():
    text = "전화 031-111-2222 / 팩스 031-111-3333"
    out = extract_phones(text)
    assert "031-111-2222" in out
    assert "031-111-3333" not in out


def test_department_label_excludes_number():
    """'마케팅팀' 같은 부서 라벨 옆 번호는 제외."""
    text = "본사 02-1111-2222 마케팅팀 02-3333-4444"
    out = extract_phones(text)
    assert "02-1111-2222" in out
    assert "02-3333-4444" not in out


def test_recruitment_label_excludes_number():
    text = "대표번호 02-1111-2222 채용담당 02-9999-9999"
    out = extract_phones(text)
    assert "02-1111-2222" in out
    assert "02-9999-9999" not in out


def test_after_service_label_excludes():
    text = "TEL 02-1111-2222 A/S 1588-7777"
    out = extract_phones(text)
    assert "02-1111-2222" in out
    assert "1588-7777" not in out


def test_exclude_can_be_disabled():
    """exclude_labelled=False 옵션으로 모든 번호 추출 가능."""
    text = "TEL 02-1111-2222 FAX 02-9999-9999"
    out = extract_phones(text, exclude_labelled=False)
    assert "02-1111-2222" in out
    assert "02-9999-9999" in out
