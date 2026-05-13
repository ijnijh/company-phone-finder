"""기업 홈페이지에서 대표전화 후보 추출 (3차 강화, 2026-05-13).

전략:
1) **JSON-LD telephone** 메타데이터 우선 — schema.org 표준이라 가장 신뢰
2) **<a href="tel:...">** 직접 추출 — 모바일 친화 사이트는 거의 다 보유
3) **푸터 영역 우선 추출** — <footer>, .footer, #footer 안의 corporate 번호는
   라벨·회사명 컨텍스트 없이도 채택 (푸터의 정의가 회사 정보 영역)
4) 본문 영역에서는 회사명/라벨 컨텍스트로 추출
5) contact 페이지 동적 탐색은 보조적으로
6) FAX/부서 라벨 옆 번호는 제외, 블랙리스트 적용
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from core.blacklist import filter_phones
from core.phone import (
    canonical,
    extract_hq_phones,
    extract_phones,
    extract_phones_with_context,
    is_corporate,
    normalize,
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5"}

_STATIC_PATHS = [
    "/contact", "/contact-us", "/contactus", "/about", "/about-us",
    "/company", "/intro", "/회사소개", "/연락처", "/오시는길",
]

_CONTACT_KEYWORDS = (
    "연락처", "오시는길", "오시는 길", "찾아오시는길", "찾아오시는 길",
    "문의", "고객문의", "고객지원", "고객센터", "지원센터",
    "회사소개", "회사 소개", "기업소개", "기업 정보", "회사정보",
    "본사", "본점", "사무소",
    "contact", "contactus", "contact us", "about", "aboutus", "about us",
    "company", "location",
)

_FOOTER_SELECTORS = (
    "footer", ".footer", "#footer", ".site-footer", ".global-footer",
    ".gfooter", "[role='contentinfo']", ".foot", "#foot",
)

_MAX_BYTES = 1_500_000
_MAX_PAGES = 4


def fetch_phones(url: str, company_name: str = "", timeout: float = 8.0) -> list[str]:
    """홈페이지에서 회사 대표번호 후보 반환.

    중요 정책 (2026-05 개정):
    - contact 페이지를 **항상** 탐색해서 우선순위 위쪽에 둔다.
      (메인 푸터에는 그룹 통합 콜센터가 박혀있고 본사 직통은 contact us
       페이지에만 있는 케이스 — 동원로엑스 — 를 잡기 위함)
    - 발견 순서:
        ① contact 페이지의 회사명 컨텍스트 매칭 번호  (가장 신뢰)
        ② contact 페이지의 JSON-LD / tel / 푸터 / 본문 번호
        ③ 메인 페이지의 JSON-LD / tel
        ④ 메인 페이지의 회사명 컨텍스트 매칭 번호
        ⑤ 메인 페이지의 푸터 번호
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

    base_html_bytes, tree, body_text = _fetch(url, timeout)
    if tree is None:
        return []

    # ─── contact 페이지 우선 탐색 ──────────────────────────────────
    contact_urls = _discover_contact_urls(tree, url)
    if not contact_urls:
        origin = _origin(url)
        if origin:
            contact_urls = [urljoin(origin, p) for p in _STATIC_PATHS]

    visited: set[str] = {url}
    for cu in contact_urls:
        if len(visited) >= _MAX_PAGES:
            break
        if cu in visited or not cu:
            continue
        visited.add(cu)
        page_bytes, page_tree, page_text = _fetch(cu, timeout)
        if page_tree is None:
            continue
        # ⓪ "본사"/"대표전화" 라벨 직후 번호 — contact 페이지의 최강 신호
        #    (여러 지점·센터 번호가 같이 박혀있을 때 본사만 골라내기)
        if page_text:
            hq = extract_hq_phones(page_text, radius=60)
            if hq:
                _ingest(hq)
        # ① contact 페이지의 회사명 컨텍스트
        if page_text:
            ctx = extract_phones_with_context(page_text, company_name=company_name, radius=400)
            if ctx:
                _ingest(ctx)
        # ② contact 페이지의 JSON-LD/tel/푸터
        _ingest(_extract_jsonld_phones(page_bytes or b""))
        _ingest(_extract_tel_links(page_tree))
        _ingest(_extract_from_footer(page_tree))

    # ─── 메인 페이지 추출 ─────────────────────────────────────────
    # ③ 본사 라벨 직후 번호
    if body_text:
        _ingest(extract_hq_phones(body_text, radius=60))
    # ④ JSON-LD
    _ingest(_extract_jsonld_phones(base_html_bytes or b""))
    # ④ tel: 링크
    _ingest(_extract_tel_links(tree))
    # ⑤ 메인 본문 회사명 컨텍스트
    if body_text:
        ctx = extract_phones_with_context(body_text, company_name=company_name, radius=400)
        if ctx:
            _ingest(ctx)
    # ⑥ 메인 푸터 (가장 후순위 — 그룹 통합 콜센터 같은 노이즈 가능성)
    _ingest(_extract_from_footer(tree))

    # 블랙리스트 + 상위 3건
    return filter_phones(collected)[:3]


# ─────────────────────────── 추출 헬퍼 ───────────────────────────


def _extract_jsonld_phones(html_bytes: bytes) -> list[str]:
    """HTML 내 <script type="application/ld+json"> 블록에서 telephone 필드 추출."""
    if not html_bytes:
        return []
    try:
        tree = HTMLParser(html_bytes)
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for tel in _walk_jsonld_for_telephone(data):
            ph = _normalize_intl(tel)
            if ph and ph not in seen:
                seen.add(ph)
                out.append(ph)
    return out


def _normalize_intl(raw: str) -> str | None:
    """+82(국가코드) 포함 표기를 0XX 형식으로 정규화한 뒤 normalize()."""
    if not raw:
        return None
    s = raw.strip()
    # +82-2-..., +82 2 ..., 0082-2-..., 82-2-... 모두 처리
    s = re.sub(r"^(?:\+?82|0082)[-\s.)]?", "0", s)
    return normalize(s)


def _walk_jsonld_for_telephone(node) -> list[str]:
    """재귀적으로 dict/list를 순회하며 telephone 필드 값을 모은다."""
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and k.lower() in ("telephone", "phone", "phonenumber"):
                if isinstance(v, str):
                    found.append(v)
                elif isinstance(v, list):
                    for x in v:
                        if isinstance(x, str):
                            found.append(x)
            else:
                found.extend(_walk_jsonld_for_telephone(v))
    elif isinstance(node, list):
        for it in node:
            found.extend(_walk_jsonld_for_telephone(it))
    return found


def _extract_tel_links(tree: HTMLParser) -> list[str]:
    """<a href="tel:..."> 링크에서 번호 추출."""
    if not tree:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for node in tree.css('a[href^="tel:"]'):
        href = (node.attributes.get("href") or "")[len("tel:"):]
        if not href:
            continue
        ph = _normalize_intl(href)
        if ph and ph not in seen:
            seen.add(ph)
            out.append(ph)
    return out


def _extract_from_footer(tree: HTMLParser) -> list[str]:
    """푸터 영역에서 전화번호 추출. 푸터 정의상 회사 정보 영역이라 라벨/회사명
    컨텍스트 없이도 채택한다.
    """
    if not tree:
        return []
    body = tree.body or tree

    text_chunks: list[str] = []
    for sel in _FOOTER_SELECTORS:
        try:
            for node in body.css(sel):
                t = node.text(separator=" ", strip=True)
                if t:
                    text_chunks.append(t)
        except Exception:
            continue

    if not text_chunks:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for chunk in text_chunks:
        # 푸터 영역은 라벨 없이도 OK, 하지만 FAX/부서 라벨 옆은 여전히 제외
        for ph in extract_phones(chunk, exclude_labelled=True):
            if ph not in seen:
                seen.add(ph)
                out.append(ph)
    return out


def _fetch(url: str, timeout: float):
    """URL fetch → (raw_bytes, HTMLParser, body_text)."""
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=_HEADERS, verify=False
        ) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return None, None, None
            ctype = resp.headers.get("content-type", "")
            if ctype and "html" not in ctype.lower() and "xml" not in ctype.lower():
                return None, None, None
            body = resp.content[:_MAX_BYTES]
    except (httpx.HTTPError, httpx.InvalidURL):
        return None, None, None

    try:
        tree = HTMLParser(body)
        # script/style은 텍스트 추출 전 제거 (단, JSON-LD는 raw bytes에서 별도 파싱하므로 OK)
        for node in tree.css("script, style, noscript"):
            node.decompose()
        target = tree.body if tree.body else tree
        text = target.text(separator=" ", strip=True)
    except Exception:
        return None, None, None
    return body, tree, text


def _discover_contact_urls(tree: HTMLParser | None, base_url: str) -> list[str]:
    if not tree:
        return []
    origin = _origin(base_url)
    if not origin:
        return []

    found: list[tuple[int, str]] = []
    for node in tree.css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            absolute = urljoin(base_url, href)
        except Exception:
            continue
        if _origin(absolute) != origin:
            continue
        text = (node.text(strip=True) or "")[:60]
        href_low = href.lower()
        text_low = text.lower()
        priority = 0
        for kw in _CONTACT_KEYWORDS:
            kw_low = kw.lower()
            if kw_low in text_low:
                priority = max(priority, 3 if kw in ("연락처", "오시는길", "문의", "contact", "contact us") else 2)
            elif kw_low in href_low:
                priority = max(priority, 2 if kw in ("contact", "about", "company") else 1)
        if priority > 0:
            found.append((priority, absolute))

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
