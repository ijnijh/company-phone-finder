"""대표번호 후보들에 대해 소스별 가중치·다수결로 1개 확정."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.phone import canonical, normalize


# 소스명 → 가중치 (높을수록 신뢰)
SOURCE_WEIGHTS: dict[str, int] = {
    "naver_local": 3,
    "homepage": 2,
    "jobkorea": 1,
    "saramin": 1,
}


@dataclass
class VerifyResult:
    best_phone: str = ""
    # 검증됨(2소스 이상 일치) / 지도확인(지도 단독) / 홈페이지확인(홈페이지 단독)
    # / 잡포털확인(잡코리아·사람인 단독) / 찾지못함
    confidence: str = "찾지못함"
    sources: list[str] = field(default_factory=list)   # best_phone을 반환한 소스들
    score: int = 0
    candidates: list[tuple[str, int, list[str]]] = field(default_factory=list)  # (phone, score, sources) 상위 후보들


def decide(by_source: dict[str, list[str]]) -> VerifyResult:
    """소스별 후보번호 dict를 받아 최종 확정 결과를 반환.

    by_source 예: {"naver_local": ["02-1234-5678"], "homepage": ["02-1234-5678", "1588-0000"], ...}
    """
    # phone(canonical) → 정보
    bucket: dict[str, dict] = {}
    for source, phones in by_source.items():
        weight = SOURCE_WEIGHTS.get(source, 1)
        for raw in phones:
            ph = normalize(raw) or raw
            key = canonical(ph)
            if not key:
                continue
            slot = bucket.setdefault(key, {"phone": ph, "score": 0, "sources": []})
            slot["score"] += weight
            if source not in slot["sources"]:
                slot["sources"].append(source)

    if not bucket:
        return VerifyResult()

    ranked = sorted(bucket.values(), key=lambda v: (v["score"], _source_priority(v["sources"])), reverse=True)
    best = ranked[0]
    confidence = _confidence_label(best)

    candidates_summary = [(b["phone"], b["score"], b["sources"]) for b in ranked[:3]]

    return VerifyResult(
        best_phone=best["phone"],
        confidence=confidence,
        sources=best["sources"],
        score=best["score"],
        candidates=candidates_summary,
    )


_JOB_PORTAL_SOURCES = {"jobkorea", "saramin"}
_AUTHORITY_SOURCES = {"naver_local", "homepage"}


def _confidence_label(best: dict) -> str:
    """단일·복수 소스 상황을 명시적으로 구분한 라벨.

    - 권위 소스(지도·홈페이지)가 1개 이상 + 다른 소스 1개 이상 일치 → "검증됨"
    - 잡코리아 + 사람인만 일치(둘 다 채용 DB라 사실상 단일 출처)
        → "잡포털2중확인" (검증됨보다 약함, 채용 담당자 직통일 가능성)
    - 단일 소스 → 그 소스의 라벨
    - 빈 후보 → "찾지못함"
    """
    sources = best["sources"]
    if not sources:
        return "찾지못함"

    has_authority = any(s in _AUTHORITY_SOURCES for s in sources)
    jobportal_sources = [s for s in sources if s in _JOB_PORTAL_SOURCES]

    if len(sources) >= 2 and has_authority:
        return "검증됨"

    if len(sources) >= 2 and len(jobportal_sources) >= 2 and not has_authority:
        # 잡코리아+사람인만 일치 — 독립 검증이 아니므로 격하
        return "잡포털2중확인"

    # 단일 소스
    src = sources[0]
    if src == "naver_local":
        return "지도확인"
    if src == "homepage":
        return "홈페이지확인"
    if src in _JOB_PORTAL_SOURCES:
        return "잡포털확인"
    return "찾지못함"


def _source_priority(sources: list[str]) -> int:
    """동점일 때 네이버 지도가 들어있는 후보가 이기도록 tie-breaker."""
    if "naver_local" in sources:
        return 2
    if "homepage" in sources:
        return 1
    return 0
