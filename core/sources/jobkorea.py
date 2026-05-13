"""잡코리아 기업검색 스크래퍼.

# selectors as of 2026-05-13
주의사항:
- 잡코리아 사이트 자체 대표번호(1588-9350 등)가 페이지 푸터·헤더에 박혀 있어
  단순 텍스트 추출로는 그것이 회사 번호로 오인됨.
- 잡코리아 검색은 부정확해서 검색어와 다른 회사를 첫 결과로 노출하는 경우가
  많음 (예: "쿠팡로지스틱스서비스" 검색 → "나이스정보통신"). 따라서 회사
  상세 페이지의 회사명이 검색어와 일치하는지 강제로 검증한다.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser

from core.blacklist import filter_phones
from core.phone import extract_phones_with_context, is_corporate

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
                return []  # 상세 페이지 못 찾으면 검색 결과만으론 채택 안 함

            full = urljoin(_BASE, detail_url)
            detail_resp = client.get(full)
            if detail_resp.status_code >= 400:
                return []
            detail_tree = HTMLParser(detail_resp.text)

            # ★ 회사명 강제 검증 — 상세 페이지가 정말 그 회사인지 확인
            if not _verify_company_match(detail_tree, company_name):
                return []

            return _extract_safely(detail_tree, company_name)
    except (httpx.HTTPError, httpx.InvalidURL):
        return []
    except Exception:
        return []


def _verify_company_match(tree: HTMLParser, company_name: str) -> bool:
    """상세 페이지의 회사명 표시 영역에 검색어 토큰이 등장하는지 **엄격** 검증.

    페이지 본문은 광고·관련 회사 추천 등으로 노이즈가 많아 토큰이 우연히
    포함될 수 있으므로 다음 좁은 영역만 검사한다:
      - <title> 태그
      - <h1>, <h2> 헤더
      - 회사명 전용 클래스 (.company-name, .corp-name, [class*="company"] 등)

    토큰은 회사명 핵심 단어 (앞 2자 약칭은 제외 — 너무 자주 우연 매칭).
    """
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
    """엄격 검증용 토큰 — 약칭(앞 2자) 같이 우연 매칭 가능한 것은 제외."""
    cleaned = _NAME_NOISE.sub("", name).strip()
    if not cleaned:
        return set()
    out: set[str] = set()
    low = cleaned.lower()
    out.add(low)
    no_space = re.sub(r"\s+", "", low)
    out.add(no_space)
    # 단어 단위 토큰 (영문 회사명 분리용) — 단, 3글자 이상만
    for w in re.split(r"\W+", low):
        if len(w) >= 3:
            out.add(w)
    # 한글 회사명은 4글자 이상이면 앞 3글자(약칭이 아닌 의미있는 부분)도 인정
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
