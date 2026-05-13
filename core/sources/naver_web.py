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

# 공식 홈페이지로 보지 않을 도메인 (소문자 비교)
_EXCLUDE_DOMAINS = {
    "blog.naver.com", "cafe.naver.com", "post.naver.com", "news.naver.com",
    "youtube.com", "youtu.be", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "tistory.com", "brunch.co.kr", "medium.com",
    "jobkorea.co.kr", "saramin.co.kr", "wanted.co.kr", "incruit.com", "jumpit.co.kr",
    "namu.wiki", "wikipedia.org", "ko.wikipedia.org",
    "kr.indeed.com", "indeed.com",
    "alba.co.kr", "albamon.com",
    "diningcode.com", "mangoplate.com",
    "smartstore.naver.com", "search.naver.com", "map.naver.com",
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
    """업체명으로 검색해 공식 홈페이지로 추정되는 첫 URL을 반환. 못 찾으면 ''."""
    queries = [
        f"{company_name} 공식 홈페이지",
        f"{company_name} 회사소개",
        company_name,
    ]
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
            return item.link
    return ""


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s or "").strip()
