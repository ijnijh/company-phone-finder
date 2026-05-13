from core.phone import canonical, extract_phones, is_corporate, normalize


def test_extract_seoul_with_paren():
    assert extract_phones("문의: 02)1234-5678") == ["02-1234-5678"]


def test_extract_dot_separator():
    assert extract_phones("연락처 031.123.4567") == ["031-123-4567"]


def test_extract_corporate_4digit():
    assert extract_phones("대표 1588 1234 까지") == ["1588-1234"]
    assert extract_phones("1577-0000") == ["1577-0000"]


def test_extract_multiple_and_dedup():
    text = "본사 02-1234-5678 / 영업 02-1234-5678 / 팩스 02-1111-2222"
    found = extract_phones(text)
    assert "02-1234-5678" in found
    assert "02-1111-2222" in found
    assert len(found) == 2


def test_extract_mobile_still_extracted_but_not_corporate():
    # 추출은 되지만 is_corporate 단계에서 걸러져야 한다
    found = extract_phones("개인 010-1234-5678")
    assert found, "010 번호도 패턴 매칭은 되어야 한다"
    assert is_corporate(found[0]) is False


def test_is_corporate_filters_050x():
    assert is_corporate("0504-1234-5678") is False
    assert is_corporate("02-1234-5678") is True
    assert is_corporate("1588-1234") is True


def test_normalize_single():
    assert normalize("(02) 1234-5678") == "02-1234-5678"
    assert normalize("문자 안에 없음") is None


def test_canonical():
    assert canonical("02-1234-5678") == "0212345678"
    assert canonical("1588 1234") == "15881234"
