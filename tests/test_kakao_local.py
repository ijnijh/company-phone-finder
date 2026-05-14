"""카카오맵 어댑터 테스트 — 외부 API는 monkeypatch로 차단."""
from unittest.mock import MagicMock

from core.sources import kakao_local
from core.sources.kakao_local import KakaoPlace


def test_no_api_key_returns_empty(monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    assert kakao_local.fetch_phones("회사") == []
    assert kakao_local.is_available() is False


def test_is_available_with_key(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    assert kakao_local.is_available() is True


def test_fetch_phones_exact_name_match(monkeypatch):
    """정확매칭 + phone 있음 → 채택."""
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr(kakao_local, "search", lambda q, size=5, timeout=8.0: [
        KakaoPlace(
            place_name="현대건설",
            category_name="건설/시공 > 종합건설",
            phone="02-1671-2114",
            address_name="서울 종로구 율곡로 75",
            road_address_name="서울 종로구 율곡로 75",
            place_url="https://place.map.kakao.com/123",
            x="127", y="37",
        ),
    ])
    out = kakao_local.fetch_phones("현대건설")
    assert "02-1671-2114" in out


def test_fetch_phones_branch_penalized(monkeypatch):
    """본사보다 지점이 후순위. 본사가 먼저 와야 함."""
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr(kakao_local, "search", lambda q, size=5, timeout=8.0: [
        KakaoPlace(
            place_name="ABC회사 강남지점",
            category_name="제조업",
            phone="02-9999-9999",
            address_name="서울 강남구",
            road_address_name="",
            place_url="", x="", y="",
        ),
        KakaoPlace(
            place_name="ABC회사 본사",
            category_name="제조업",
            phone="02-1111-2222",
            address_name="서울 종로구",
            road_address_name="",
            place_url="", x="", y="",
        ),
    ])
    out = kakao_local.fetch_phones("ABC회사")
    # 본사 가산점 + 지점 감점 → 본사 번호가 1순위
    assert out[0] == "02-1111-2222"


def test_fetch_phones_region_hint_boosts(monkeypatch):
    """지역 힌트가 일치하는 후보가 우선."""
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr(kakao_local, "search", lambda q, size=5, timeout=8.0: [
        KakaoPlace(
            place_name="동방회사",
            category_name="제조업",
            phone="051-100-1000",  # 부산
            address_name="부산 해운대구",
            road_address_name="",
            place_url="", x="", y="",
        ),
        KakaoPlace(
            place_name="동방회사",
            category_name="제조업",
            phone="02-200-2000",  # 서울
            address_name="서울 강남구",
            road_address_name="",
            place_url="", x="", y="",
        ),
    ])
    out = kakao_local.fetch_phones("동방회사", hints={"region": "서울"})
    assert out[0] == "02-200-2000"


def test_fetch_phones_filters_mobile_numbers(monkeypatch):
    """휴대폰 번호는 채택 안 함."""
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr(kakao_local, "search", lambda q, size=5, timeout=8.0: [
        KakaoPlace(
            place_name="작은가게",
            category_name="소매",
            phone="010-1234-5678",
            address_name="서울",
            road_address_name="", place_url="", x="", y="",
        ),
    ])
    out = kakao_local.fetch_phones("작은가게")
    assert out == []


def test_fetch_phones_unrelated_name_excluded(monkeypatch):
    """검색어와 전혀 다른 이름은 후보에서 제외."""
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr(kakao_local, "search", lambda q, size=5, timeout=8.0: [
        KakaoPlace(
            place_name="완전다른회사",
            category_name="제조업",
            phone="02-1234-5678",
            address_name="서울",
            road_address_name="", place_url="", x="", y="",
        ),
    ])
    out = kakao_local.fetch_phones("쿠팡로지스틱스")
    assert out == []
