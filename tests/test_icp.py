from core.icp import load_config, score_category


def test_load_config_basic():
    cfg = load_config()
    assert cfg.positive_flat, "양성 키워드가 비어있으면 안 됨"
    assert cfg.negative_flat, "음성 키워드가 비어있으면 안 됨"
    assert cfg.w("icp_positive", 0) > 0
    assert cfg.w("icp_negative", 0) < 0


def test_score_category_positive():
    cfg = load_config()
    score, pos, neg = score_category("종합건설 본사", cfg)
    assert score > 0
    assert any("건설" in p for p in pos)


def test_score_category_negative():
    cfg = load_config()
    score, pos, neg = score_category("음식점 한식당", cfg)
    assert score < 0
    assert any("음식점" in n for n in neg)


def test_score_category_empty():
    cfg = load_config()
    score, pos, neg = score_category("", cfg)
    assert score == 0
    assert pos == [] and neg == []
