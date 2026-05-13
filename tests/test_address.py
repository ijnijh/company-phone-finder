from core.address import Address, parse_address, region_match


def test_parse_seoul():
    a = parse_address("서울특별시 강남구 역삼동 123-45")
    assert a.sido == "서울특별시"
    assert a.sigungu == "강남구"
    assert a.dong == "역삼동"


def test_parse_gyeonggi_seongnam_bundang():
    a = parse_address("경기도 성남시 분당구 삼평동 123")
    assert a.sido == "경기도"
    assert a.sigungu == "성남시 분당구"
    assert a.dong == "삼평동"


def test_parse_with_road_address():
    a = parse_address(address="서울특별시 강남구 역삼동 123", road_address="서울특별시 강남구 테헤란로 123")
    assert a.sido == "서울특별시"
    assert a.sigungu == "강남구"
    assert a.dong == "역삼동"
    assert "테헤란로" in a.full


def test_region_match_full_name():
    a = Address(sido="서울특별시", sigungu="강남구", dong="역삼동", full="서울특별시 강남구 테헤란로 123")
    assert region_match("서울", a) is True
    assert region_match("강남구", a) is True
    assert region_match("부산", a) is False


def test_region_match_empty():
    a = Address()
    assert region_match("서울", a) is False
