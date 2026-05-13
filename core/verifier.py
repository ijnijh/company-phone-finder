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


def _confidence_label(best: dict) -> str:
    """단일·복수 소스 상황을 명시적으로 구분한 라벨.

    여러 소스가 같은 번호를 반환했을 때만 "검증됨". 단일 소스인 경우엔
    어느 소스에서 발견했는지를 라벨에 그대로 노출해서 사용자가 신뢰도를
    스스로 판단할 수 있게 한다. (이전 버전의 "의심"은 너무 두루뭉술해서
    홈페이지 단독 발견 케이스와 잡포털 단독 발견 케이스가 한 통에 묶였음.)
    """
    sources = best["sources"]
    if len(sources) >= 2:
        return "검증됨"
    if not sources:
        return "찾지못함"
    src = sources[0]
    if src == "naver_local":
        return "지도확인"
    if src == "homepage":
        return "홈페이지확인"
    if src in ("jobkorea", "saramin"):
        return "잡포털확인"
    return "찾지못함"


def _source_priority(sources: list[str]) -> int:
    """동점일 때 네이버 지도가 들어있는 후보가 이기도록 tie-breaker."""
    if "naver_local" in sources:
        return 2
    if "homepage" in sources:
        return 1
    return 0
