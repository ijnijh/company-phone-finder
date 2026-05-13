"""네이버 검색 API - Web(웹문서) 어댑터.

목적: 업체명 + "공식 홈페이지" 키워드로 검색해 회사 홈페이지 URL을 찾는다.
잡포털·뉴스·블로그·SNS 도메인은 결과에서 제외.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx



_ENDPOINT = "https://openapi.naver.com/v1/search/webkr.json"
_TAG_RE = re.compile(r"<[^>]+>")

# 공식 홈페이지로 보지 않을 도메인 (소문자 비교, 서브도메인 일치는 endswith로)
_EXCLUDE_DOMAINS = {
    # 네이버 자체 서비스
    "blog.naver.com", "cafe.naver.com", "post.naver.com", "news.naver.com",
    "kin.naver.com", "smartstore.naver.com", "search.naver.com", "map.naver.com",
    "shopping.naver.com", "place.naver.com", "m.place.naver.com",
    # SNS
    "youtube.com", "youtu.be", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "pinterest.com", "tiktok.com",
    # 블로그·미디어 플랫폼
    "tistory.com", "brunch.co.kr", "medium.com", "velog.io", "github.io",
    "egloos.com", "blogspot.com", "wordpress.com",
    # 뉴스 (광범위)
    "chosun.com", "donga.com", "joongang.co.kr", "hankyung.com", "mk.co.kr",
    "edaily.co.kr", "fnnews.com", "mt.co.kr", "etnews.com", "zdnet.co.kr",
    "yna.co.kr", "yonhapnews.co.kr", "newsis.com", "news1.kr",
    "ohmynews.com", "pressian.com", "khan.co.kr", "hani.co.kr",
    # 잡포털·HR
    "jobkorea.co.kr", "saramin.co.kr", "wanted.co.kr", "incruit.com", "jumpit.co.kr",
    "alba.co.kr", "albamon.com", "kr.indeed.com", "indeed.com",
    "jobplanet.co.kr", "catch.co.kr", "jasoseol.com", "linkareer.com",
    # 위키
    "namu.wiki", "wikipedia.org", "ko.wikipedia.org",
    # 음식점·리뷰
    "diningcode.com", "mangoplate.com", "siksinhot.com",
    # 쇼핑 마켓플레이스 (회사 공식이 아닌 입점 페이지)
    "11st.co.kr", "gmarket.co.kr", "auction.co.kr", "coupang.com",
    "interpark.com", "lotteimall.com",  # 본 회사가 검색되는 경우는 별도 처리
}


@dataclass
class WebItem:
    title: str
    link: str
    description: str

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.link).netloc.lower()
        except Exception:
            return ""


class NaverWebError(Exception):
    pass


def search(query: str, display: int = 10, timeout: float = 8.0) -> list[WebItem]:
    if not query.strip():
        return []
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise NaverWebError("NAVER_CLIENT_ID/SECRET이 설정되지 않았습니다.")

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": query, "display": max(1, min(display, 30)), "start": 1}

    try:
        resp = httpx.get(_ENDPOINT, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise NaverWebError(f"네이버 Web API 오류: {e}") from e

    raw_items = resp.json().get("items", []) or []
    return [
        WebItem(
            title=_strip_tags(it.get("title", "")),
            link=it.get("link", ""),
            description=_strip_tags(it.get("description", "")),
        )
        for it in raw_items
    ]


def find_homepage(company_name: str, timeout: float = 8.0) -> str:
    """업체명으로 검색해 **공식 홈페이지로 강하게 추정되는** 첫 URL을 반환.

    검증 강화 (2026-05):
    - 알려진 제외 도메인(블로그·뉴스·잡포털·SNS·마켓플레이스 등) 차단
    - 회사명 핵심 토큰이 **도메인 또는 페이지 제목**에 등장하는 결과만 채택
      (광고 LP, 무관한 회사 비교 페이지 등을 걸러냄)
    """
    if not company_name.strip():
        return ""

    queries = [
        f"{company_name} 공식 홈페이지",
        f"{company_name} 회사소개",
        company_name,
    ]
    norm_tokens = _name_tokens(company_name)

    for q in queries:
        try:
            items = search(q, display=10, timeout=timeout)
        except NaverWebError:
            continue
        for item in items:
            domain = item.domain
            if not domain:
                continue
            if any(domain == d or domain.endswith("." + d) for d in _EXCLUDE_DOMAINS):
                continue
            if not _looks_like_official(item, domain, norm_tokens):
                continue
            return item.link
    return ""


# 법인 형태 표기만 제거 (공백은 보존 — 영문 토큰 분리에 필요)
_NAME_NOISE_RE = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사")


def _name_tokens(company_name: str) -> set[str]:
    """회사명에서 의미 있는 토큰을 추출.

    예:
        "(주)동원로엑스"  → {"동원로엑스", "동원"}
        "LG Chem"        → {"lg chem", "lgchem", "lg", "chem"}
    """
    cleaned = _NAME_NOISE_RE.sub("", company_name).strip()
    if not cleaned:
        return set()
    tokens: set[str] = set()
    low = cleaned.lower()
    tokens.add(low)                       # "lg chem"
    tokens.add(re.sub(r"\s+", "", low))   # "lgchem" (공백 제거 본)
    # 단어 단위 토큰 (\W로 split → 영문은 공백·하이픈으로 자연 분리)
    for w in re.split(r"\W+", low):
        if len(w) >= 2:
            tokens.add(w)                 # "lg", "chem"
    # 한글 약칭 (4글자 이상이면 앞 2글자도)
    no_space = re.sub(r"\s+", "", cleaned)
    if len(no_space) >= 4:
        tokens.add(no_space[:2].lower())
    return tokens


def _looks_like_official(item: WebItem, domain: str, name_tokens: set[str]) -> bool:
    """도메인 또는 페이지 제목에 회사명 토큰이 등장하는지."""
    if not name_tokens:
        return True  # 토큰을 못 뽑았으면 검증 통과 (회사명이 비정상적으로 짧은 경우)
    domain_l = domain.lower()
    title_l = (item.title or "").lower()
    for tok in name_tokens:
        if tok in domain_l or tok in title_l:
            return True
    return False


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s or "").strip()
