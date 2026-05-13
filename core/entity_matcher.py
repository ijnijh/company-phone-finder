"""네이버 지도 검색 결과(동명 업체 N개)에서 1개 본사·사업장을 선정.

핵심 로직: ICP 카테고리·사용자 힌트·명칭 일치·본사/지점 마커를 합산해 점수화.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from core.address import Address, parse_address, region_match
from core.icp import IcpConfig, score_category
from core.sources.naver_local import LocalItem

# 명칭 정규화에서 제거할 토큰
_NAME_NOISE_RE = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사|\(재\)|재단법인|\(사\)|사단법인|\s+")
_BRANCH_MARKERS = ("지점", "영업소", "출장소", "센터", "매장", "지사", "사무소")
_HEADQUARTERS_MARKERS = ("본사", "본점", "주식회사", "(주)", "㈜")


@dataclass
class ScoredCandidate:
    item: LocalItem
    address: Address
    score: float
    detail: dict[str, float] = field(default_factory=dict)


@dataclass
class MatchResult:
    status: str                                   # 매칭확정 / 확정필요 / 매칭약함 / 업체매칭실패
    chosen: Optional[ScoredCandidate]
    alternates: list[ScoredCandidate]
    note: str = ""


def normalize_name(s: str) -> str:
    return _NAME_NOISE_RE.sub("", s or "").lower()


def select(
    query: str,
    items: list[LocalItem],
    hints: dict[str, str],
    config: IcpConfig,
) -> MatchResult:
    """동명 후보 N개에 대해 점수를 매기고 분기 결과를 반환.

    hints 예: {"region": "서울 강남", "category": "건설"}
    """
    if not items:
        return MatchResult(status="업체매칭실패", chosen=None, alternates=[], note="네이버 지도 검색 결과 없음")

    norm_query = normalize_name(query)
    scored: list[ScoredCandidate] = []
    rejected_by_name: list[ScoredCandidate] = []

    for it in items:
        addr = parse_address(it.address, it.road_address)
        score, detail = _score_one(norm_query, it, addr, hints, config)
        cand = ScoredCandidate(item=it, address=addr, score=score, detail=detail)
        if detail.get("name_match", 0) <= 0 and detail.get("partial_name", 0) <= 0:
            # 검색어와 명칭이 거의 무관하면 제외 (네이버가 가끔 무관 결과를 섞음)
            rejected_by_name.append(cand)
            continue
        scored.append(cand)

    # 명칭 매칭 통과 후보가 하나도 없으면 실패
    if not scored:
        return MatchResult(
            status="업체매칭실패",
            chosen=None,
            alternates=rejected_by_name[:3],
            note="검색어와 일치하는 업체명 없음",
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    best = scored[0]
    runner_up = scored[1].score if len(scored) >= 2 else float("-inf")

    threshold = config.t("match_threshold", 1.0)
    gap = config.t("ambiguous_gap", 2.0)

    if best.score < threshold:
        status = "매칭약함"
        note = "ICP·힌트 신호가 약함 — 결과 확인 권장"
    elif (best.score - runner_up) < gap and len(scored) >= 2:
        status = "확정필요"
        note = "동명 후보 점수 근접 — 후보 시트에서 직접 선택 권장"
    else:
        status = "매칭확정"
        note = ""

    return MatchResult(status=status, chosen=best, alternates=scored[:3], note=note)


def _score_one(
    norm_query: str,
    item: LocalItem,
    address: Address,
    hints: dict[str, str],
    config: IcpConfig,
) -> tuple[float, dict[str, float]]:
    detail: dict[str, float] = {}
    total = 0.0

    # 1) 명칭 일치
    norm_title = normalize_name(item.title)
    if norm_title and norm_query and norm_title == norm_query:
        w = config.w("exact_name", 2.0)
        detail["name_match"] = w
        total += w
    elif norm_query and (norm_query in norm_title or norm_title in norm_query):
        w = config.w("partial_name", 1.0)
        detail["partial_name"] = w
        total += w
    else:
        # 토큰 일부라도 겹치면 약하게 인정
        q_tokens = [t for t in norm_query.split() if t]
        if q_tokens and any(t in norm_title for t in q_tokens):
            w = config.w("partial_name", 1.0) * 0.5
            detail["partial_name"] = w
            total += w

    # 2) 본사/지점 마커
    title = item.title or ""
    if any(m in title for m in _HEADQUARTERS_MARKERS):
        w = config.w("headquarters_marker", 1.0)
        detail["hq"] = w
        total += w
    if any(m in title for m in _BRANCH_MARKERS):
        w = config.w("branch_marker", -1.0)
        detail["branch"] = w
        total += w

    # 3) ICP 카테고리
    icp_score, pos_kw, neg_kw = score_category(item.category_and_title, config)
    if icp_score:
        detail["icp"] = icp_score
        total += icp_score
    if pos_kw:
        detail["icp_pos_keywords"] = float(len(pos_kw))
    if neg_kw:
        detail["icp_neg_keywords"] = float(len(neg_kw))

    # 4) 사용자 힌트
    region_hint = (hints.get("region") or "").strip() if hints else ""
    if region_hint and region_match(region_hint, address):
        w = config.w("hint_address_match", 5.0)
        detail["hint_region"] = w
        total += w

    category_hint = (hints.get("category") or "").strip() if hints else ""
    if category_hint:
        # 카테고리 힌트는 토큰 단위로 검사
        cat_text = item.category_and_title
        hits = sum(1 for tok in re.split(r"[\s,·/]+", category_hint) if tok and tok in cat_text)
        if hits:
            w = config.w("hint_category_match", 3.0) * min(hits, 2)
            detail["hint_category"] = w
            total += w

    return total, detail
