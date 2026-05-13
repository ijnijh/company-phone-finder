"""pipeline의 격상 룰 통합 테스트.

외부 네트워크(naver_local, naver_web, 잡포털 등)는 monkeypatch로 차단하고,
entity_matcher가 매칭확정 + ICP 양성을 반환했을 때 verifier의 단일 권위소스
결과가 "검증됨"으로 격상되는지 확인.
"""
from __future__ import annotations

import pytest

from core import pipeline as pipeline_mod
from core.excel_io import InputRow
from core.icp import load_config
from core.sources.naver_local import LocalItem


def _item(title, category, address, road="", tel=""):
    return LocalItem(
        title=title, category=category, description="", telephone=tel,
        address=address, road_address=road, link="", mapx="", mapy="",
    )


def _stub_naver_local(items):
    def _fn(query, display=5):
        return items
    return _fn


def _stub_find_homepage(url):
    def _fn(name, timeout=8.0):
        return url
    return _fn


def _stub_fetch_phones(phones):
    def _fn(*args, **kwargs):
        return phones
    return _fn


def test_promotion_homepage_only_with_strong_icp(monkeypatch):
    """매칭확정 + ICP 양성 + 홈페이지 단독 → 검증됨으로 격상."""
    monkeypatch.setattr(
        pipeline_mod.naver_local, "search",
        _stub_naver_local([
            _item("현대건설(주) 본사", "종합건설업", "서울특별시 종로구 율곡로 75"),
        ]),
    )
    monkeypatch.setattr(pipeline_mod.naver_web, "find_homepage", _stub_find_homepage("https://example.com"))
    monkeypatch.setattr(pipeline_mod.company_homepage, "fetch_phones", _stub_fetch_phones(["02-1234-5678"]))
    monkeypatch.setattr(pipeline_mod.jobkorea, "fetch_phones", _stub_fetch_phones([]))
    monkeypatch.setattr(pipeline_mod.saramin, "fetch_phones", _stub_fetch_phones([]))

    row = InputRow(row_index=2, company_name="현대건설", region_hint="", category_hint="")
    res = pipeline_mod._process_one(row, load_config(), lambda m: None)

    assert res.result_row["매칭상태"] == "매칭확정"
    assert res.result_row["대표번호"] == "02-1234-5678"
    assert res.result_row["신뢰도"] == "검증됨"
    assert "단일 권위소스 자동 격상" in res.result_row["비고"]


def test_no_promotion_when_icp_weak(monkeypatch):
    """ICP 양성 신호가 없으면 격상하지 않고 '홈페이지확인' 유지."""
    monkeypatch.setattr(
        pipeline_mod.naver_local, "search",
        _stub_naver_local([
            # 이름은 일치하지만 ICP 양성 키워드가 없는 카테고리
            _item("아무회사", "기타", "서울특별시 강남구 역삼동 1"),
        ]),
    )
    monkeypatch.setattr(pipeline_mod.naver_web, "find_homepage", _stub_find_homepage("https://example.com"))
    monkeypatch.setattr(pipeline_mod.company_homepage, "fetch_phones", _stub_fetch_phones(["02-1234-5678"]))
    monkeypatch.setattr(pipeline_mod.jobkorea, "fetch_phones", _stub_fetch_phones([]))
    monkeypatch.setattr(pipeline_mod.saramin, "fetch_phones", _stub_fetch_phones([]))

    row = InputRow(row_index=2, company_name="아무회사", region_hint="", category_hint="")
    res = pipeline_mod._process_one(row, load_config(), lambda m: None)

    # ICP 양성 키워드가 없으므로 격상하지 않음
    assert res.result_row["신뢰도"] in ("홈페이지확인", "잡포털확인")
    assert "자동 격상" not in res.result_row["비고"]


def test_two_sources_already_verified(monkeypatch):
    """지도+홈페이지가 같은 번호 → 격상 룰 거치지 않아도 이미 검증됨."""
    monkeypatch.setattr(
        pipeline_mod.naver_local, "search",
        _stub_naver_local([
            _item("현대건설(주) 본사", "종합건설업", "서울특별시 종로구 율곡로 75", tel="02-1234-5678"),
        ]),
    )
    monkeypatch.setattr(pipeline_mod.naver_web, "find_homepage", _stub_find_homepage("https://example.com"))
    monkeypatch.setattr(pipeline_mod.company_homepage, "fetch_phones", _stub_fetch_phones(["02-1234-5678"]))
    monkeypatch.setattr(pipeline_mod.jobkorea, "fetch_phones", _stub_fetch_phones([]))
    monkeypatch.setattr(pipeline_mod.saramin, "fetch_phones", _stub_fetch_phones([]))

    row = InputRow(row_index=2, company_name="현대건설", region_hint="", category_hint="")
    res = pipeline_mod._process_one(row, load_config(), lambda m: None)

    assert res.result_row["신뢰도"] == "검증됨"
    # 이미 두 소스로 검증됐으므로 격상 비고 없음
    assert "자동 격상" not in res.result_row["비고"]
