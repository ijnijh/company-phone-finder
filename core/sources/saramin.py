"""사람인 기업검색 스크래퍼.

# selectors as of 2026-05-13
jobkorea.py와 동일한 안전 전략: 푸터·헤더 제거 + 회사명/라벨 컨텍스트 추출 + 블랙리스트.
"""
from __future__ import annotations

from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser

from core.blacklist import filter_phones
from core.phone import extract_phones_with_context, is_corporate

_BASE = "https://www.saramin.co.kr"
_SEARCH = _BASE + "/zf_user/search/company?searchword={q}"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9"}


def fetch_phones(company_name: str, timeout: float = 8.0) -> list[str]:
    if not company_name.strip():
        return []
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=_HEADERS, verify=False) as client:
            search_url = _SEARCH.format(q=quote_plus(company_name))
            resp = client.get(search_url)
            if resp.status_code >= 400:
                return []
            tree = HTMLParser(resp.text)
            detail_url = _first_company_link(tree)
            if not detail_url:
                return _extract_safely(tree, company_name)

            full = urljoin(_BASE, detail_url)
            detail_resp = client.get(full)
            if detail_resp.status_code >= 400:
                return []
            detail_tree = HTMLParser(detail_resp.text)
            return _extract_safely(detail_tree, company_name)
    except (httpx.HTTPError, httpx.InvalidURL):
        return []
    except Exception:
        return []


def _first_company_link(tree: HTMLParser) -> str:
    selectors = [
        'a[href*="/company-info/"]',
        'a[href*="/zf_user/company-info/"]',
        'a[href*="/company-review/"]',
    ]
    for sel in selectors:
        for node in tree.css(sel):
            href = node.attributes.get("href") or ""
            if href:
                return href
    return ""


def _extract_safely(tree: HTMLParser, company_name: str) -> list[str]:
    if not tree:
        return []
    body = tree.body or tree
    for sel in ("footer", "header", ".footer", "#footer", "script", "style", "noscript", ".gnb", ".lnb"):
        try:
            for node in body.css(sel):
                node.decompose()
        except Exception:
            pass

    text = body.text(separator=" ", strip=True) if hasattr(body, "text") else ""
    if not text:
        return []

    candidates = extract_phones_with_context(text, company_name=company_name, radius=400)
    if not candidates:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for ph in candidates:
        if not is_corporate(ph):
            continue
        if ph in seen:
            continue
        seen.add(ph)
        out.append(ph)
    out = filter_phones(out)
    return out[:3]
