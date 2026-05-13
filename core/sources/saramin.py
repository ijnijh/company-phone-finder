"""사람인 기업검색 스크래퍼.

# selectors as of 2026-05-13
jobkorea.py와 동일한 안전 전략: 푸터·헤더 제거 + 회사명/라벨 컨텍스트 추출
+ 블랙리스트 + **회사명 강제 검증**.
"""
from __future__ import annotations

import re
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
                return []

            full = urljoin(_BASE, detail_url)
            detail_resp = client.get(full)
            if detail_resp.status_code >= 400:
                return []
            detail_tree = HTMLParser(detail_resp.text)

            if not _verify_company_match(detail_tree, company_name):
                return []

            return _extract_safely(detail_tree, company_name)
    except (httpx.HTTPError, httpx.InvalidURL):
        return []
    except Exception:
        return []


def _verify_company_match(tree: HTMLParser, company_name: str) -> bool:
    """jobkorea와 동일: <title>/<h1>/회사명 클래스만 검사 (본문 광고 노이즈 회피)."""
    if not tree:
        return False
    tokens = _strict_company_tokens(company_name)
    if not tokens:
        return True
    haystacks: list[str] = []
    try:
        title_node = tree.css_first("title")
        if title_node:
            haystacks.append(title_node.text(strip=True))
    except Exception:
        pass
    for sel in ("h1", "h2", ".company-name", ".corp-name",
                "[class*='company']", "[class*='corp']", "[class*='Corp']",
                "[class*='Name']", "[class*='name']"):
        try:
            for n in tree.css(sel)[:5]:
                t = n.text(strip=True)
                if t:
                    haystacks.append(t)
        except Exception:
            continue
    big = " ".join(haystacks).lower()
    return any(t in big for t in tokens)


def _strict_company_tokens(name: str) -> set[str]:
    cleaned = _NAME_NOISE.sub("", name).strip()
    if not cleaned:
        return set()
    out: set[str] = set()
    low = cleaned.lower()
    out.add(low)
    no_space = re.sub(r"\s+", "", low)
    out.add(no_space)
    for w in re.split(r"\W+", low):
        if len(w) >= 3:
            out.add(w)
    if len(no_space) >= 5 and re.match(r"^[가-힣]+$", no_space):
        out.add(no_space[:3])
    return out


_NAME_NOISE = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사")


def _company_tokens(name: str) -> set[str]:
    cleaned = _NAME_NOISE.sub("", name).strip()
    if not cleaned:
        return set()
    out: set[str] = set()
    low = cleaned.lower()
    out.add(low)
    no_space = re.sub(r"\s+", "", low)
    out.add(no_space)
    for w in re.split(r"\W+", low):
        if len(w) >= 2:
            out.add(w)
    if len(no_space) >= 4:
        out.add(no_space[:2])
        out.add(no_space[:3])
    return out


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
