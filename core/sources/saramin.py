"""사람인 기업검색 스크래퍼.

# selectors as of 2026-05-12
"""
from __future__ import annotations

from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser

from core.phone import extract_phones, is_corporate

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
                return _filter(extract_phones(tree.body.text(separator=" ", strip=True) if tree.body else ""))

            full = urljoin(_BASE, detail_url)
            detail_resp = client.get(full)
            if detail_resp.status_code >= 400:
                return []
            detail_tree = HTMLParser(detail_resp.text)
            text = detail_tree.body.text(separator=" ", strip=True) if detail_tree.body else detail_tree.text(separator=" ", strip=True)
            return _filter(extract_phones(text))
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


def _filter(phones: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ph in phones:
        if not is_corporate(ph) or ph in seen:
            continue
        seen.add(ph)
        out.append(ph)
        if len(out) >= 3:
            break
    return out
