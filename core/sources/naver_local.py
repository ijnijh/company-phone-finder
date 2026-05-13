"""네이버 검색 API - Local(지도) 어댑터.

엔드포인트: https://openapi.naver.com/v1/search/local.json
무료 키 발급 후 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수에 설정.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

_ENDPOINT = "https://openapi.naver.com/v1/search/local.json"
_TAG_RE = re.compile(r"<[^>]+>")  # <b> 태그 제거


@dataclass
class LocalItem:
    title: str          # 태그 제거된 정식 명칭
    category: str
    description: str
    telephone: str
    address: str        # 지번주소
    road_address: str   # 도로명주소
    link: str
    mapx: str
    mapy: str

    @property
    def category_and_title(self) -> str:
        return f"{self.title} {self.category}"


class NaverLocalError(Exception):
    pass


def search(query: str, display: int = 5, timeout: float = 8.0) -> list[LocalItem]:
    """네이버 Local API로 업체명 검색. 응답 items를 LocalItem 리스트로 반환."""
    if not query.strip():
        return []
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise NaverLocalError("NAVER_CLIENT_ID/SECRET이 설정되지 않았습니다.")

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": query, "display": max(1, min(display, 5)), "start": 1, "sort": "random"}

    try:
        resp = httpx.get(_ENDPOINT, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise NaverLocalError(f"네이버 Local API 오류: {e}") from e

    items_raw = resp.json().get("items", []) or []
    return [_to_item(raw) for raw in items_raw]


def _to_item(raw: dict) -> LocalItem:
    return LocalItem(
        title=_strip_tags(raw.get("title", "")),
        category=raw.get("category", ""),
        description=raw.get("description", ""),
        telephone=raw.get("telephone", ""),
        address=raw.get("address", ""),
        road_address=raw.get("roadAddress", ""),
        link=raw.get("link", ""),
        mapx=raw.get("mapx", ""),
        mapy=raw.get("mapy", ""),
    )


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s or "").strip()
