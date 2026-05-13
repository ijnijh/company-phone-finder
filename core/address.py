"""주소 문자열에서 시도/시군구/동을 추출.

네이버 Local API의 `address`(지번)·`roadAddress`(도로명) 어느 쪽이 들어와도 동작.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 17개 광역시도 (네이버는 보통 풀네임을 반환)
_SIDO_LIST = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시",
    "경기도", "강원도", "강원특별자치도",
    "충청북도", "충청남도", "전라북도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
    # 약칭도 받아주기
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

# 시·군·구 토큰: ([가-힣]+)(시|군|구) — 도로명 표기에서 "분당구"처럼 단독 등장 가능
_SIGUNGU_RE = re.compile(r"([가-힣]{1,8})(시|군|구)")

# 읍·면·동: 도로명일 때는 안 나올 수 있어 지번주소 우선
_DONG_RE = re.compile(r"([가-힣0-9]{1,10})(동|읍|면)(?![가-힣])")


@dataclass(frozen=True)
class Address:
    sido: str = ""
    sigungu: str = ""
    dong: str = ""
    full: str = ""

    def is_empty(self) -> bool:
        return not (self.sido or self.sigungu or self.dong)


def parse_address(address: str = "", road_address: str = "") -> Address:
    """지번주소·도로명주소를 받아 (시도, 시군구, 동, full) 반환.

    동(법정동)은 지번주소에서만 안정적으로 얻을 수 있으므로,
    full은 도로명 우선, 동 추출은 지번 우선.
    """
    full = road_address.strip() or address.strip()
    sido = _extract_sido(address) or _extract_sido(road_address)
    sigungu = _extract_sigungu(address) or _extract_sigungu(road_address)
    dong = _extract_dong(address) or _extract_dong(road_address)
    return Address(sido=sido, sigungu=sigungu, dong=dong, full=full)


def _extract_sido(text: str) -> str:
    if not text:
        return ""
    # 긴 것부터 매칭(서울특별시가 서울보다 우선)
    for sido in sorted(_SIDO_LIST, key=len, reverse=True):
        if text.startswith(sido):
            return sido
    return ""


def _extract_sigungu(text: str) -> str:
    if not text:
        return ""
    # 시도 제거 후 첫 시/군/구 매치
    body = text
    for sido in sorted(_SIDO_LIST, key=len, reverse=True):
        if body.startswith(sido):
            body = body[len(sido):].strip()
            break
    matches = list(_SIGUNGU_RE.finditer(body))
    if not matches:
        return ""
    # "성남시 분당구"처럼 시 + 구가 함께 나오는 케이스: 두 토큰을 합쳐서 반환
    first = matches[0]
    result = first.group(0)
    if first.group(2) == "시" and len(matches) >= 2:
        second = matches[1]
        if second.group(2) == "구" and second.start() - first.end() <= 2:
            result = f"{first.group(0)} {second.group(0)}"
    return result


def _extract_dong(text: str) -> str:
    if not text:
        return ""
    m = _DONG_RE.search(text)
    return m.group(0) if m else ""


def region_match(hint: str, address: Address) -> bool:
    """사용자 힌트(예: '서울', '강남구', '성남시 분당구')가 주소에 부합하는지."""
    if not hint or address.is_empty():
        return False
    h = hint.strip()
    # 짧은 약칭도 정상 매칭되도록 정규화
    haystack = f"{address.sido} {address.sigungu} {address.dong} {address.full}"
    if h in haystack:
        return True
    # "서울" → "서울특별시" 약칭 매칭
    if h in {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"}:
        return address.sido.startswith(h)
    return False
