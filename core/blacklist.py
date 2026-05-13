"""사이트 자체의 대표번호 블랙리스트.

잡코리아·사람인 같은 외부 사이트를 스크래핑할 때 페이지 푸터·헤더에 그 사이트의
자체 대표번호(예: 잡코리아 1588-9350)가 텍스트에 섞여 들어와 회사 번호로 오인되는
문제를 막는다. canonical(숫자만) 키로 비교한다.
"""
from __future__ import annotations

from core.phone import canonical


# 알려진 잡포털·검색포털·HR 플랫폼 자체 대표번호.
# 운영하면서 새로 발견되면 이 세트에 한 줄 추가만 하면 즉시 차단됨.
_KNOWN_PORTAL_NUMBERS = {
    # 잡코리아
    "1588-9350", "1588-9351", "1577-9350",
    # 사람인
    "1588-9759", "02-2086-1100",
    # 인크루트
    "1599-1170",
    # 원티드
    "02-6203-9853", "1670-6573",
    # 점핏(Jumpit)
    "1644-1601",
    # 알바몬 / 알바천국 / 알바콜
    "1588-1701", "1577-7727", "1577-1233",
    # 잡플래닛
    "02-2025-2200",
    # 캐치(Catch)
    "1577-9356",
    # 자소설닷컴
    "070-4944-7733",
    # 링커리어
    "070-4334-8000",
    # 인디드(Indeed)
    "02-6022-8000",
    # 네이버 고객센터·관련
    "1588-3820", "1588-5896",
    # 다음/카카오
    "1577-3321", "1577-3754",
    # 11번가·G마켓·옥션·쿠팡 등 마켓플레이스 고객센터 (회사 검색 시 푸터에 박힘)
    "1599-0110",  # 11번가
    "1566-5701",  # G마켓
    "1599-5601",  # 쿠팡 고객센터
    "1577-7011",  # 옥션
    # 잡코리아 페이지에서 두 다른 회사 검색에 동일하게 등장한 노이즈 번호
    # (관찰 2026-05-13: 쿠팡로지스틱스서비스·동원로엑스 검색 모두 잡코리아=02-3771-1514 반환)
    "02-3771-1514",
}


def _normalize_set(raws: set[str]) -> set[str]:
    out: set[str] = set()
    for r in raws:
        c = canonical(r)
        if c:
            out.add(c)
    return out


_BLACKLIST_CANONICAL = _normalize_set(_KNOWN_PORTAL_NUMBERS)


def is_blacklisted(phone: str) -> bool:
    """해당 번호가 알려진 사이트 자체 번호인가."""
    c = canonical(phone)
    return bool(c) and c in _BLACKLIST_CANONICAL


def filter_phones(phones: list[str]) -> list[str]:
    """블랙리스트 번호를 제거한 새 리스트 반환."""
    return [p for p in phones if not is_blacklisted(p)]
