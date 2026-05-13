"""기업 홈페이지에서 대표전화 후보 추출.

전략:
1) 홈페이지 루트 GET → HTML 텍스트화 + 전화번호 정규식.
2) 흔한 contact/about/회사소개 경로를 최대 2개까지 추가 GET해 보강.
3) 050X·010 등 개인번호는 phone.is_corporate 필터로 제거.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from core.phone import extract_phones, is_corporate

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5"}

_CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/company", "/intro", "/회사소개", "/contactus"]
_MAX_BYTES = 1_000_000  # 너무 큰 페이지는 잘라서 처리


def fetch_phones(url: str, timeout: float = 8.0, max_extra_pages: int = 2) -> list[str]:
    """홈페이지 URL에서 대표번호 후보를 정규화된 문자열 리스트로 반환."""
    if not url:
        return []

    collected: list[str] = []
    seen: set[str] = set()

    def _ingest(text: str) -> None:
        for ph in extract_phones(text):
            if not is_corporate(ph):
                continue
            if ph not in seen:
                seen.add(ph)
                collected.append(ph)

    base_text = _fetch_text(url, timeout)
    if base_text is None:
        return []
    _ingest(base_text)

    # 푸터·연락처 영역에 자주 있는 경로 추가 탐색
    extra_urls = _candidate_paths(url, base_text, max_extra_pages)
    for extra_url in extra_urls:
        text = _fetch_text(extra_url, timeout)
        if text:
            _ingest(text)

    # 상위 3개로 제한 (홈페이지엔 부서/제휴 번호가 다수 있을 수 있음)
    return collected[:3]


def _fetch_text(url: str, timeout: float) -> str | None:
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=_HEADERS, verify=False) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return None
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype.lower() and "xml" not in ctype.lower() and ctype:
                return None
            body = resp.content[:_MAX_BYTES]
    except (httpx.HTTPError, httpx.InvalidURL):
        return None

    try:
        tree = HTMLParser(body)
        # script/style 제거
        for tag in tree.css("script, style, noscript"):
            tag.decompose()
        text = tree.body.text(separator=" ", strip=True) if tree.body else tree.text(separator=" ", strip=True)
    except Exception:
        try:
            text = body.decode("utf-8", errors="ignore")
        except Exception:
            return None
    return text


def _candidate_paths(base_url: str, html_text: str, limit: int) -> list[str]:
    """홈페이지 텍스트에서 contact/about 류 링크가 발견되면 우선. 못 찾으면 기본 경로."""
    base = _origin(base_url)
    if not base:
        return []
    urls: list[str] = []
    for path in _CONTACT_PATHS:
        if len(urls) >= limit:
            break
        candidate = urljoin(base, path)
        if candidate not in urls and candidate != base_url:
            urls.append(candidate)
    return urls


def _origin(url: str) -> str:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return ""
