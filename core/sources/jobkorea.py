"""잡코리아 기업검색 스크래퍼.

# selectors as of 2026-05-13
주의사항:
- 잡코리아 사이트 자체 대표번호(1588-9350 등)가 페이지 푸터·헤더에 박혀 있어
  단순 텍스트 추출로는 그것이 회사 번호로 오인됨.
- 따라서 (a) 알려진 사이트 자체 번호는 블랙리스트로 차단,
  (b) 회사명 또는 "대표전화" 라벨 주변에 있는 번호만 채택한다.
"""
from __future__ import annotations

from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser

from core.blacklist import filter_phones
from core.phone import extract_phones, extract_phones_with_context, is_corporate

_BASE = "https://www.jobkorea.co.kr"
_SEARCH = _BASE + "/Search/?stext={q}&tabType=corp"
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
        'a[href*="/Recruit/Co_Read"]',
        'a[href*="/company/"]',
        'a[href*="/Corp/"]',
    ]
    for sel in selectors:
        for node in tree.css(sel):
            href = node.attributes.get("href") or ""
            if href:
                return href
    return ""


def _extract_safely(tree: HTMLParser, company_name: str) -> list[str]:
    """페이지에서 안전하게 회사 번호만 뽑는다.

    1) 푸터(<footer>)와 헤더(<header>) 영역 제거 — 잡코리아 자체 번호의 주 진원지
    2) 남은 텍스트에서 회사명·라벨 주변 번호만 추출
    3) 블랙리스트 적용 + 휴대폰·050X 제외
    """
    if not tree:
        return []
    body = tree.body or tree
    # 푸터·헤더·스크립트·스타일 제거
    for sel in ("footer", "header", ".footer", "#footer", "script", "style", "noscript", ".gnb", ".lnb"):
        try:
            for node in body.css(sel):
                node.decompose()
        except Exception:
            pass

    text = body.text(separator=" ", strip=True) if hasattr(body, "text") else ""
    if not text:
        return []

    # 1차: 회사명·라벨 컨텍스트 안의 번호만
    candidates = extract_phones_with_context(text, company_name=company_name, radius=400)
    # 컨텍스트 신호가 전혀 없으면 — 빈 결과로 두는 게 안전 (잘못된 번호보다 nothing이 낫다)
    if not candidates:
        return []

    # 기업 번호 필터 + 블랙리스트
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
