"""기업 홈페이지에서 대표전화 후보 추출.

핵심 전략(2026-05-13 강화):
1) 루트 페이지 fetch → 즉시 푸터·연락처 영역의 번호 추출 시도
2) 페이지의 모든 <a> 태그를 분석해 "연락처/Contact/문의/오시는길/회사소개" 같은
   링크를 동적으로 찾아낸다 (정해진 경로 목록에만 의존하지 않음 — 동원로엑스처럼
   표준 경로를 안 쓰는 사이트도 잡아내기 위함)
3) 발견된 contact 후보 URL들을 최대 3개까지 추가 fetch
4) 회사명·라벨 컨텍스트 추출로 푸터의 무관 번호 노이즈 차단
5) 050X·010·블랙리스트 번호 제거
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from core.blacklist import filter_phones
from core.phone import (
    extract_phones,
    extract_phones_with_context,
    is_corporate,
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5"}

# 정적 fallback 경로 (사이트가 위 동적 탐색에서 빠질 때 시도)
_STATIC_PATHS = [
    "/contact", "/contact-us", "/contactus", "/about", "/about-us",
    "/company", "/intro", "/회사소개", "/연락처", "/오시는길",
]

# contact 링크 발견용 키워드 (a 태그의 텍스트 또는 href에서 매칭)
_CONTACT_KEYWORDS = (
    "연락처", "오시는길", "오시는 길", "찾아오시는길", "찾아오시는 길",
    "문의", "고객문의", "고객지원", "고객센터", "지원센터",
    "회사소개", "회사 소개", "기업소개", "기업 정보", "회사정보",
    "본사", "본점", "사무소",
    "contact", "contactus", "about", "aboutus", "company", "location",
)

_MAX_BYTES = 1_500_000
_MAX_PAGES = 4  # 루트 + contact 후보 3개


def fetch_phones(url: str, company_name: str = "", timeout: float = 8.0) -> list[str]:
    """홈페이지에서 회사 대표번호 후보를 정규화 문자열 리스트로 반환.

    company_name이 주어지면 회사명 컨텍스트 검사로 푸터 노이즈를 차단한다.
    """
    if not url:
        return []

    collected: list[str] = []
    seen: set[str] = set()

    def _ingest(phones: list[str]) -> None:
        for ph in phones:
            if not is_corporate(ph) or ph in seen:
                continue
            seen.add(ph)
            collected.append(ph)

    base_html, base_text = _fetch(url, timeout)
    if base_text is None:
        return []

    # 1) 루트 텍스트에서 컨텍스트 추출 우선, 신호 없으면 fallback으로 전체 추출
    primary = extract_phones_with_context(base_text, company_name=company_name, radius=400)
    if primary:
        _ingest(primary)
    else:
        # 컨텍스트 신호가 없으면 페이지 전체에서 시도 (단, 1588/1577 같은 대표번호는
        # 사이트 자체 번호일 가능성을 블랙리스트로 차단)
        _ingest(extract_phones(base_text))

    # 2) <a> 태그에서 contact 후보 링크 동적 발견
    contact_urls = _discover_contact_urls(base_html, url)

    # 3) 못 찾았으면 정적 경로 fallback
    if not contact_urls:
        origin = _origin(url)
        if origin:
            contact_urls = [urljoin(origin, p) for p in _STATIC_PATHS]

    # 4) 후보 URL을 fetch (최대 _MAX_PAGES - 1개)
    visited: set[str] = {url}
    for cu in contact_urls:
        if len(visited) >= _MAX_PAGES:
            break
        if cu in visited or not cu:
            continue
        visited.add(cu)
        _, text = _fetch(cu, timeout)
        if not text:
            continue
        ctx = extract_phones_with_context(text, company_name=company_name, radius=400)
        if ctx:
            _ingest(ctx)
        else:
            _ingest(extract_phones(text))

    # 5) 블랙리스트 + 상위 3건
    return filter_phones(collected)[:3]


def _fetch(url: str, timeout: float) -> tuple[HTMLParser | None, str | None]:
    """URL에서 HTML 파서와 본문 텍스트를 함께 반환."""
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=_HEADERS, verify=False
        ) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return None, None
            ctype = resp.headers.get("content-type", "")
            if ctype and "html" not in ctype.lower() and "xml" not in ctype.lower():
                return None, None
            body = resp.content[:_MAX_BYTES]
    except (httpx.HTTPError, httpx.InvalidURL):
        return None, None

    try:
        tree = HTMLParser(body)
        # script/style 제거
        for node in tree.css("script, style, noscript"):
            node.decompose()
        # 본문 텍스트 추출
        target = tree.body if tree.body else tree
        text = target.text(separator=" ", strip=True)
    except Exception:
        return None, None

    return tree, text


def _discover_contact_urls(tree: HTMLParser | None, base_url: str) -> list[str]:
    """페이지의 모든 <a> 태그에서 contact 키워드를 가진 링크를 추출.

    keyword 매칭 우선순위:
    - a 태그 텍스트 (연락처 / 오시는길 / 회사소개 / Contact 등)
    - href 경로 (contact, about, company 포함 여부)
    """
    if not tree:
        return []
    origin = _origin(base_url)
    if not origin:
        return []

    found: list[tuple[int, str]] = []  # (priority, absolute_url)

    for node in tree.css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            absolute = urljoin(base_url, href)
        except Exception:
            continue
        # 동일 도메인만
        if _origin(absolute) != origin:
            continue

        text = (node.text(strip=True) or "")[:60]
        href_low = href.lower()
        text_low = text.lower()

        # 우선순위 점수: 텍스트에 "연락처/오시는길/문의/회사소개" 등 정확 키워드면 1순위
        priority = 0
        for kw in _CONTACT_KEYWORDS:
            kw_low = kw.lower()
            if kw_low in text_low:
                priority = max(priority, 3 if kw in ("연락처", "오시는길", "오시는 길", "문의", "contact") else 2)
            elif kw_low in href_low:
                priority = max(priority, 2 if kw in ("contact", "about", "company") else 1)
        if priority > 0:
            found.append((priority, absolute))

    # 점수 높은 순, 중복 제거, 상위 N개
    found.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for _p, u in found:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= _MAX_PAGES - 1:
            break
    return out


def _origin(url: str) -> str:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return ""
