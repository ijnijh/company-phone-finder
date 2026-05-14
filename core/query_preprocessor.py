"""검색어 전처리 — 네이버 지도 매칭 실패 케이스를 줄이기 위한 정규화·확장.

200건 검증에서 매칭실패가 41.5% (83건) 발생. 주요 원인:
- 괄호 안 부서/별칭 표기: "이마트 (물류본부)", "경동물류(경동택배)"
- 두 가지 이름 병기: "컬리(Kurly)", "제때(Jette)"
- 모회사+부서: "삼성SDS (물류)", "CJ프레시웨이 (물류)"

해결: 1차 검색 실패 시 정규화된 검색어로 자동 재시도.
"""
from __future__ import annotations

import re

# 회사 형태 표기 (검색어 정규화에서 제거하지 않고 유지 — 회사명 일부일 수 있음)
# 단 괄호 안의 부서명·별칭은 제거 후 재시도


def expand_query_candidates(query: str) -> list[str]:
    """원본 검색어에서 우선순위가 있는 검색어 후보 리스트를 반환.

    호출자는 이 리스트를 순회하며 첫 번째로 매칭에 성공하는 검색어를 사용.

    Returns:
        ["원본", "괄호제거본", "괄호안내용", ...] 순서 (가장 가능성 높은 것 먼저)
    """
    if not query or not query.strip():
        return []

    raw = query.strip()
    candidates: list[str] = [raw]
    seen: set[str] = {raw}

    # 1) 괄호 안 내용 제거: "이마트 (물류본부)" → "이마트"
    stripped = _strip_parentheses(raw)
    if stripped and stripped != raw and stripped not in seen:
        candidates.append(stripped)
        seen.add(stripped)

    # 2) 괄호 안 내용 추출: "컬리(Kurly)" → "Kurly" (영문 별칭이 진짜 회사명일 수도)
    inner = _extract_parenthesis_inner(raw)
    if inner and inner not in seen:
        candidates.append(inner)
        seen.add(inner)

    # 3) 회사 형태 토큰 제거: "(주)동원로엑스" → "동원로엑스"
    no_form = _strip_corporate_form(stripped or raw)
    if no_form and no_form not in seen:
        candidates.append(no_form)
        seen.add(no_form)

    return candidates


_PAREN_RE = re.compile(r"\s*[(（][^()（）]*[)）]\s*")
_INNER_RE = re.compile(r"[(（]([^()（）]+)[)）]")
_CORP_FORM_RE = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사|\(재\)|재단법인|\(사\)|사단법인")


def _strip_parentheses(s: str) -> str:
    """모든 괄호 + 그 안의 내용 제거. 공백 정리."""
    if not s:
        return ""
    # 회사형태 표기는 임시 보존
    placeholder = "_CORPFORM_"
    protected = _CORP_FORM_RE.sub(placeholder, s)
    cleaned = _PAREN_RE.sub(" ", protected)
    cleaned = cleaned.replace(placeholder, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_parenthesis_inner(s: str) -> str:
    """첫 괄호 안 내용을 반환 (회사 형태 표기는 제외).

    예: "컬리(Kurly)" → "Kurly", "(주)쿠팡" → "" (회사 형태라 제외)
    """
    if not s:
        return ""
    for m in _INNER_RE.finditer(s):
        inner = m.group(1).strip()
        # 회사 형태 표기 자체는 의미 없음
        if inner in ("주", "유", "재", "사"):
            continue
        if "주식회사" in inner or "유한회사" in inner:
            continue
        # 너무 짧거나 일반 명사는 제외 (예: "물류", "본부")
        if len(inner) <= 2 and re.fullmatch(r"[가-힣]+", inner):
            generic = {"물류", "본부", "본사", "지사", "지점", "센터", "사업부"}
            if inner in generic:
                continue
        return inner
    return ""


def _strip_corporate_form(s: str) -> str:
    """회사 형태 표기 제거."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", _CORP_FORM_RE.sub("", s)).strip()
