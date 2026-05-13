"""잡코리아 기업검색 스크래퍼.

# selectors as of 2026-05-12
주의: 비공식 스크래핑이므로 사이트 구조 변경 시 셀렉터 수정 필요.
실패해도 파이프라인 전체가 멈추지 않도록 예외는 호출자에서 받아 무시.
"""
from __future__ import annotations

from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser

from core.phone import extract_phones, is_corporate

_BASE = "https://www.jobkorea.co.kr"
_SEARCH = _BASE + "/Search/?stext={q}&tabType=corp"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9"}


def fetch_phones(company_name: str, timeout: float = 8.0) -> list[str]:
    if not company_name.strip():
        return []
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=_HEADERS, verify=False) as client:
            # 1) 기업 검색 결과 페이지
            search_url = _SEARCH.format(q=quote_plus(company_name))
            resp = client.get(search_url)
            if resp.status_code >= 400:
                return []
            tree = HTMLParser(resp.text)

            # 첫 번째 기업 상세 링크 추출 (구조 변경 가능성 대비 두 가지 셀렉터)
            detail_url = _first_company_link(tree)
            if not detail_url:
                # 검색 결과 페이지 자체 텍스트에서 직접 추출 (가능성 낮음)
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
    # 잡코리아 기업 상세 패턴
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
