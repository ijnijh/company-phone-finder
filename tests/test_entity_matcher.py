from core.entity_matcher import select
from core.icp import load_config
from core.sources.naver_local import LocalItem


def _item(title, category, address="", road="", tel=""):
    return LocalItem(
        title=title, category=category, description="", telephone=tel,
        address=address, road_address=road, link="", mapx="", mapy="",
    )


def test_select_picks_hq_over_restaurant_and_branch():
    cfg = load_config()
    items = [
        _item("한국건설 본사", "토목공사업>종합건설", "서울특별시 강남구 역삼동 1"),
        _item("한국건설식당", "한식,분식", "서울특별시 마포구 합정동 2"),
        _item("한국건설미용실", "미용실", "부산광역시 해운대구 우동 3"),
        _item("한국건설 학원", "입시학원,학원", "경기도 수원시 영통구 4"),
        _item("한국건설 강남지점", "전문건설", "서울특별시 강남구 신사동 5"),
    ]
    res = select("한국건설", items, hints={}, config=cfg)
    assert res.chosen is not None
    assert "본사" in res.chosen.item.title


def test_region_hint_disambiguates_same_industry():
    cfg = load_config()
    items = [
        _item("동방건설", "종합건설", "서울특별시 강남구 역삼동 1"),
        _item("동방건설", "종합건설", "부산광역시 해운대구 우동 1"),
    ]
    res_busan = select("동방건설", items, hints={"region": "부산"}, config=cfg)
    assert res_busan.chosen.address.sido.startswith("부산")
    res_seoul = select("동방건설", items, hints={"region": "서울"}, config=cfg)
    assert res_seoul.chosen.address.sido.startswith("서울")


def test_all_negative_yields_weak_match():
    cfg = load_config()
    items = [
        _item("XYZ", "음식점,한식", "서울특별시 강남구 역삼동"),
        _item("XYZ", "카페", "서울특별시 강남구 삼성동"),
    ]
    res = select("XYZ", items, hints={}, config=cfg)
    # 매칭약함이거나 확정필요로 라벨링 — 매칭확정이 아니어야 핵심
    assert res.status != "매칭확정"


def test_empty_items_returns_failure():
    cfg = load_config()
    res = select("아무거나", [], hints={}, config=cfg)
    assert res.status == "업체매칭실패"
    assert res.chosen is None


def test_close_scores_become_ambiguous():
    cfg = load_config()
    # 두 본사가 점수가 거의 같게 나오도록 같은 카테고리·같은 본사 마커
    items = [
        _item("동양물산 본사", "종합건설업", "서울특별시 강남구 역삼동"),
        _item("동양물산 본사", "종합건설업", "부산광역시 해운대구 우동"),
    ]
    res = select("동양물산", items, hints={}, config=cfg)
    # 힌트가 없고 두 후보가 비슷하니 확정필요로 가야 한다
    assert res.status in ("확정필요", "매칭약함")
    assert len(res.alternates) >= 2
