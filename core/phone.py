"""한국 전화번호 추출·정규화·기업번호 판별."""
from __future__ import annotations

import re

# 한국 전화번호 패턴 (캡처 그룹: 지역/사업자 코드, 국번, 가입자번호)
# 02 (서울 2자리), 0[3-6][1-4] (지역 3자리), 070, 1XXX 대표번호, 050X 개인번호, 010 휴대폰
_PATTERNS = [
    # 1588/1577/1600/1644/1666/1899 등 8자리 대표번호
    re.compile(r"(?<!\d)(1[5-9]\d{2})\s*[-.\s)]?\s*(\d{4})(?!\d)"),
    # 02-XXX(X)-XXXX
    re.compile(r"(?<!\d)(02)\s*[)\-.\s]?\s*(\d{3,4})\s*[-.\s]?\s*(\d{4})(?!\d)"),
    # 0XX-XXX(X)-XXXX (지역번호 3자리, 070, 050X 등) — 캡처 그룹 통일을 위해 별도 처리
    re.compile(r"(?<!\d)(0\d{2})\s*[)\-.\s]?\s*(\d{3,4})\s*[-.\s]?\s*(\d{4})(?!\d)"),
    # 050X-XXXX-XXXX (4자리 안심번호 프리픽스)
    re.compile(r"(?<!\d)(050\d)\s*[-.\s]?\s*(\d{4})\s*[-.\s]?\s*(\d{4})(?!\d)"),
]

# 대표번호로 보지 않는 프리픽스
_MOBILE_PREFIXES = {"010", "011", "016", "017", "018", "019"}
_PERSONAL_SAFE_PREFIXES = ("050",)  # 050X 안심번호 — 개인용으로 간주

# 1588/1577 등 대표번호 prefix
_CORPORATE_4DIGIT_PREFIXES = {"1588", "1577", "1600", "1644", "1666", "1899", "1522", "1566", "1670", "1811", "1855", "1877", "1899", "1330"}


def extract_phones(text: str) -> list[str]:
    """텍스트에서 한국 전화번호 패턴을 모두 추출해 정규화된 문자열 리스트로 반환.

    중복은 보존 순서대로 제거된다. 출현 빈도 분석은 호출자가 별도로 수행.
    """
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            normalized = _normalize_match(m.groups())
            if normalized and normalized not in seen:
                seen.add(normalized)
                found.append(normalized)
    return found


def normalize(raw: str) -> str | None:
    """단일 번호 문자열을 정규화. 매칭 실패 시 None."""
    phones = extract_phones(raw)
    return phones[0] if phones else None


def is_corporate(phone: str) -> bool:
    """대표번호 후보로 사용 가능한지. 휴대폰/050X 안심번호는 False."""
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return False
    # 휴대폰
    if any(digits.startswith(p) for p in _MOBILE_PREFIXES):
        return False
    # 050X 안심번호
    if digits.startswith("050"):
        return False
    return True


def _normalize_match(groups: tuple[str, ...]) -> str | None:
    """정규식 그룹을 표준형 'XX-XXXX-XXXX' 또는 'XXXX-XXXX'로."""
    parts = [g for g in groups if g]
    if len(parts) == 2:
        # 1588-XXXX 형식
        return f"{parts[0]}-{parts[1]}"
    if len(parts) == 3:
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    return None


def canonical(phone: str) -> str:
    """비교용 캐노니컬 형태(숫자만)."""
    return re.sub(r"\D", "", phone or "")


# 회사명 컨텍스트 추출에서 사용할 키워드 (라벨이 있으면 강한 신호)
_LABEL_KEYWORDS = (
    "대표전화", "대표번호", "본사", "본점", "전화", "연락처", "TEL", "tel",
    "Tel", "T.", "T :", "T:", "고객센터", "문의", "상담",
)


def extract_phones_with_context(
    text: str,
    company_name: str = "",
    radius: int = 500,
) -> list[str]:
    """텍스트에서 전화번호를 추출하되, **회사명 또는 명시적 전화 라벨 주변**에 있는
    번호만 채택한다.

    푸터·헤더에 박힌 사이트 자체 대표번호(예: 잡코리아 1588-9350)가 페이지 텍스트에
    있어도 회사명 근처가 아니라면 채택하지 않는다.

    Args:
        text: 정규화 안 된 페이지 텍스트
        company_name: 회사명. 빈 문자열이면 라벨만 검사
        radius: 회사명/라벨 위치 좌우 N자 안에 있는 번호만 인정

    Returns:
        정규화된 전화번호 리스트 (순서·중복 제거)
    """
    if not text:
        return []

    # 회사명·라벨이 등장하는 모든 위치를 모음
    anchor_positions: list[int] = []
    if company_name:
        # 회사명의 핵심 토큰만 (괄호·"(주)"·공백 제거)
        norm_name = _NAME_TOKEN_RE.sub("", company_name)
        if norm_name:
            for m in re.finditer(re.escape(norm_name), text):
                anchor_positions.append(m.start())
    for kw in _LABEL_KEYWORDS:
        for m in re.finditer(re.escape(kw), text):
            anchor_positions.append(m.start())

    if not anchor_positions:
        # 회사명·라벨 어디에도 없으면 컨텍스트 신호가 약함 → 빈 결과
        # (호출자가 fallback으로 전체 추출을 시도할 수 있음)
        return []

    # 각 anchor 주변 텍스트에서 번호 추출
    found: list[str] = []
    seen: set[str] = set()
    for pos in anchor_positions:
        start = max(0, pos - radius)
        end = min(len(text), pos + radius)
        window = text[start:end]
        for ph in extract_phones(window):
            if ph not in seen:
                seen.add(ph)
                found.append(ph)
    return found


_NAME_TOKEN_RE = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사|\s+")

