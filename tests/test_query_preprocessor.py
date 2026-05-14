"""검색어 전처리 테스트."""
from core.query_preprocessor import expand_query_candidates


def test_simple_query_returns_single_candidate():
    assert expand_query_candidates("쿠팡") == ["쿠팡"]


def test_parenthesis_with_department_stripped():
    """'이마트 (물류본부)' → 원본 + 괄호제거본"""
    out = expand_query_candidates("이마트 (물류본부)")
    assert "이마트 (물류본부)" in out
    assert "이마트" in out


def test_compact_parenthesis_with_alias():
    """'컬리(Kurly)' → 원본 + 괄호제거(컬리) + 괄호안(Kurly)"""
    out = expand_query_candidates("컬리(Kurly)")
    assert "컬리(Kurly)" in out
    assert "컬리" in out
    assert "Kurly" in out


def test_two_korean_names_in_parenthesis():
    """'경동물류(경동택배)' → 둘 다 시도"""
    out = expand_query_candidates("경동물류(경동택배)")
    assert "경동물류" in out
    assert "경동택배" in out


def test_corporate_form_preserved_then_stripped():
    """'(주)쿠팡' → 원본 + (주) 제거"""
    out = expand_query_candidates("(주)쿠팡")
    assert "(주)쿠팡" in out
    assert "쿠팡" in out


def test_generic_inner_word_not_extracted():
    """'대상 (물류)' → '물류'는 generic이라 후보에서 제외, '대상'만 채택"""
    out = expand_query_candidates("대상 (물류)")
    assert "대상" in out
    # "물류"는 너무 generic이라 별도 후보로 안 만들어짐
    assert "물류" not in out


def test_empty_or_whitespace_returns_empty():
    assert expand_query_candidates("") == []
    assert expand_query_candidates("   ") == []
    assert expand_query_candidates(None) == []  # type: ignore[arg-type]


def test_no_duplicates():
    """동일 결과가 여러 변환에서 나와도 중복 제거."""
    out = expand_query_candidates("쿠팡")
    assert len(out) == len(set(out))
