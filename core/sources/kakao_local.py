"""카카오맵 키워드 검색 API 어댑터.

엔드포인트: https://dapi.kakao.com/v2/local/search/keyword.json
인증: Authorization: KakaoAK {REST_API_KEY}
무료 한도: 300,000 calls/day

네이버 지도와 다른 데이터셋이라 보완적. 응답의 phone 필드를 직접 활용.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

_ENDPOINT = "https://dapi.kakao.com/v2/local/search/keyword.json"


@dataclass
class KakaoPlace:
    place_name: str          # 상호명
    category_name: str        # 카테고리 (예: "물류,운송 > 택배회사")
    phone: str               # 전화번호 (있는 경우)
    address_name: str        # 지번주소
    road_address_name: str   # 도로명주소
    place_url: str           # 카카오맵 상세 페이지 URL
    x: str                   # 경도
    y: str                   # 위도

    @property
    def category_and_name(self) -> str:
        return f"{self.place_name} {self.category_name}"


class KakaoLocalError(Exception):
    pass


def is_available() -> bool:
    """KAKAO_REST_API_KEY가 설정되어 있는가."""
    return bool(os.environ.get("KAKAO_REST_API_KEY", "").strip())


def search(query: str, size: int = 5, timeout: float = 8.0) -> list[KakaoPlace]:
    """카카오 키워드 검색. 응답 documents를 KakaoPlace 리스트로 반환."""
    if not query.strip():
        return []
    key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    if not key:
        raise KakaoLocalError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    headers = {"Authorization": f"KakaoAK {key}"}
    params = {"query": query, "size": max(1, min(size, 15))}

    try:
        resp = httpx.get(_ENDPOINT, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise KakaoLocalError(f"카카오맵 API 오류: {e}") from e

    docs = resp.json().get("documents", []) or []
    return [_to_place(d) for d in docs]


def _to_place(raw: dict) -> KakaoPlace:
    return KakaoPlace(
        place_name=(raw.get("place_name") or "").strip(),
        category_name=(raw.get("category_name") or "").strip(),
        phone=(raw.get("phone") or "").strip(),
        address_name=(raw.get("address_name") or "").strip(),
        road_address_name=(raw.get("road_address_name") or "").strip(),
        place_url=(raw.get("place_url") or "").strip(),
        x=(raw.get("x") or "").strip(),
        y=(raw.get("y") or "").strip(),
    )


# 회사명 정규화 (entity_matcher와 동일 원리)
_NAME_NOISE_RE = re.compile(
    r"\(주\)|주식회사|㈜|\(유\)|유한회사|\(재\)|재단법인|\(사\)|사단법인"
    r"|[(（][^()（）]*[)）]|\s+"
)


def fetch_phones(company_name: str, hints: dict | None = None, timeout: float = 8.0) -> list[str]:
    """카카오맵 검색 결과에서 회사 대표번호 후보 추출.

    회사명 정규화 매칭 + (있다면) 지역 힌트 일치로 정확도 보강.
    각 결과의 phone 필드만 사용 — 추가 페이지 fetch 없음.
    """
    from core.blacklist import filter_phones
    from core.phone import is_corporate, normalize

    if not company_name or not company_name.strip():
        return []
    if not is_available():
        return []

    try:
        places = search(company_name, size=5, timeout=timeout)
    except KakaoLocalError:
        return []
    except Exception:
        return []

    if not places:
        return []

    norm_query = _NAME_NOISE_RE.sub("", company_name).lower()
    region_hint = (hints or {}).get("region", "").strip()

    candidates: list[tuple[int, str]] = []  # (점수, 정규화된 번호)
    for p in places:
        if not p.phone:
            continue
        # 회사명 매칭 점수
        norm_place = _NAME_NOISE_RE.sub("", p.place_name).lower()
        score = 0
        if norm_place == norm_query:
            score += 3
        elif norm_query and (norm_query in norm_place or norm_place in norm_query):
            score += 1
        elif norm_query:
            # 토큰 일부라도 겹치면 약하게
            tokens = [t for t in norm_query.split() if len(t) >= 2]
            if tokens and any(t in norm_place for t in tokens):
                score += 0  # 약한 매치 (제외 대상)
        # 회사명 매칭이 약하면 후보에서 제외
        if score == 0:
            continue
        # 지역 힌트 일치 시 가산점
        if region_hint:
            full_addr = f"{p.address_name} {p.road_address_name}"
            if region_hint in full_addr:
                score += 2
        # 본사·본점 표시 시 가산점
        if any(m in p.place_name for m in ("본사", "본점", "주식회사", "(주)", "㈜")):
            score += 1
        # 지점·영업소 표시 시 감점
        if any(m in p.place_name for m in ("지점", "영업소", "출장소", "센터", "지사")):
            score -= 1

        ph = normalize(p.phone)
        if ph and is_corporate(ph):
            candidates.append((score, ph))

    if not candidates:
        return []

    # 점수 높은 순으로 정렬, 상위 3개 반환
    candidates.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for _, ph in candidates:
        if ph in seen:
            continue
        seen.add(ph)
        out.append(ph)
        if len(out) >= 3:
            break
    return filter_phones(out)
