"""Claude AI 기반 본사 대표번호 추출.

홈페이지/contact 페이지 텍스트를 LLM에 보내서 회사의 본사 대표 전화번호를 추출.
정규식 룰의 사각지대(부서/지점 라벨 변형, 푸터의 그룹 통합 콜센터, FAX 혼동,
검색이 잘못된 회사 페이지로 연결된 경우 등)를 페이지 맥락 이해로 해결한다.

## 비용 (참고)
- Haiku 4.5 + 시스템 프롬프트 캐싱 → 회사 1건당 약 ₩6~10
- 100개 회사 배치: 약 ₩700~1000

## 캐싱 동작
- 시스템 프롬프트(~5000 토큰)에 ephemeral cache_control 적용
- 1번째 호출: cache_write (1.25x 비용)
- 2~N번째: cache_read (0.1x 비용, 90% 절감)
- 5분 유휴 후 캐시 만료
- 검증: response.usage.cache_read_input_tokens > 0 이어야 정상
"""
from __future__ import annotations

import logging
import os

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    _ANTHROPIC_AVAILABLE = False

from core.phone import normalize

log = logging.getLogger(__name__)

# Haiku 4.5: 가장 저렴한 GA 모델 + 한국어 충분
_MODEL = "claude-haiku-4-5"

# 페이지 텍스트는 최대 12000자(약 6K tokens)로 truncate
_MAX_INPUT_CHARS = 12_000

# 응답은 "02-1234-5678" 또는 "없음" 형식이라 매우 짧음
_MAX_OUTPUT_TOKENS = 50

# 시스템 프롬프트 — 4096+ tokens 보장으로 Haiku 캐싱 활성화.
# 짧으면 cache_control이 silent하게 무시됨 (cache_read_input_tokens=0).
_SYSTEM_PROMPT = """당신은 한국 B2B 기업의 공식 홈페이지·contact 페이지 텍스트에서 회사의 **본사 대표 전화번호** 단 1개를 정확히 추출하는 전문 AI입니다. 정규식 기반 추출이 실패하는 케이스(라벨 변형, 그룹 콜센터, 광고/관련회사 혼입, 푸터 노이즈 등)를 사람처럼 페이지 맥락을 이해해서 해결하는 것이 당신의 역할입니다.

## 임무

입력: 회사명 + 페이지 본문 텍스트 (HTML 태그 제거됨)
출력: 그 회사의 본사 대표 전화번호 1개. 정확히 다음 형식 중 하나여야 함:
- `02-1234-5678` (서울 지역번호)
- `031-123-4567` 또는 `031-1234-5678` (수도권/지방 지역번호 + 국번 3~4자리)
- `070-1234-5678` (인터넷 전화)
- `1588-1234`, `1577-1234`, `1600-1234`, `1644-1234`, `1666-1234`, `1899-1234` (8자리 대표번호)
- `없음` (확신 부족 또는 페이지에 없음)

**번호 외 다른 텍스트 절대 금지.** "본사 대표번호는 02-1234-5678입니다" 같은 문장형 답변 금지. 하이픈 형식만.

## 채택해야 할 번호 (positive signals)

### 명시적 라벨이 있는 경우 (강한 신호)
- "본사", "본점", "Headquarters", "HQ"
- "대표전화", "대표번호", "대표 전화", "대표 번호"
- "Tel", "TEL", "T.", "T :", "T:"
- "고객센터", "통합 콜센터", "콜센터", "고객지원"
- "안내", "문의", "Contact", "Contact us"

### 유효한 한국 전화번호 형식
- 02-XXXX-XXXX (서울)
- 031~064-XXX(X)-XXXX (수도권/지방 지역번호)
- 070-XXXX-XXXX (인터넷 전화 — 보통 IT 기업)
- 1588-XXXX, 1577-XXXX, 1600-XXXX, 1644-XXXX, 1666-XXXX, 1899-XXXX (대표번호 시리즈)

### 위치 신호
- 페이지 상단/헤더 영역에 등장
- "회사소개", "Company", "About" 섹션 가까이
- contact 페이지의 메인 정보 박스

## 절대 채택하면 안 되는 번호 (negative signals)

### FAX 번호
라벨에 "FAX", "Fax", "fax", "팩스", "F.", "F :", "F:" 동행.
예: "TEL 02-1234-5678 / FAX 02-1234-9999" → 02-1234-9999는 제외.

### 지점·물류센터·터미널·사업장·공장 등 운영현장
라벨: "지점", "지사", "영업소", "출장소", "센터", "물류센터", "물류허브", "터미널", "허브", "사업장", "사업소", "공장", "연구소", "대리점".
본사 안내가 아닌 운영 현장 직통 번호.
예: "본사 02-1234 / 강남지점 02-9999" → 02-9999는 제외.

### 부서 직통
라벨: "마케팅팀", "마케팅부", "영업부", "영업팀", "영업본부", "인사부", "인사팀", "채용담당", "채용문의", "구매부", "구매팀", "총무부", "총무팀", "홍보부", "홍보팀", "재무부", "재무팀", "기술부", "기술팀", "기술지원", "AS", "A/S", "에이에스", "사후관리", "물류부", "물류팀", "배송문의".
본사 안내데스크 통하지 않는 부서 직통 라인.

### 휴대폰
010-, 011-, 016-, 017-, 018-, 019- 시작 모든 번호. 1인 사업자라도 대표번호로 부적합.

### 050X 안심번호
0504-, 0505-, 0506-, 0507- 등 050으로 시작하는 4자리 prefix. 개인용 안심번호 → 본사 대표 아님.

### 잡포털·검색포털 자체 번호 (페이지 푸터에 박힘)
- 잡코리아: 1588-9350, 1588-9351, 1577-9350
- 사람인: 1588-9759, 02-2086-1100
- 인크루트: 1599-1170
- 원티드: 02-6203-9853, 1670-6573
- 점핏: 1644-1601
- 알바몬: 1588-1701, 알바천국: 1577-7727
- 잡플래닛: 02-2025-2200, 캐치: 1577-9356
- 자소설닷컴: 070-4944-7733
- 네이버 고객센터: 1588-3820, 1588-5896
- 카카오: 1577-3321, 1577-3754
- 11번가: 1599-0110, G마켓: 1566-5701, 옥션: 1577-7011

### 다른 회사의 번호 (가장 위험한 함정)
- 페이지 내용이 검색 회사명과 일치하지 않음 (예: "동원로엑스" 검색했는데 페이지는 "쿠팡" 내용)
- "관련 회사", "비슷한 채용공고", "광고", "Sponsored" 영역의 번호
- 모회사·계열사 번호가 검색 회사와 동일하지 않을 때

## 판단이 어려운 케이스의 우선순위

### A. 본사 라벨이 없고 여러 번호가 줄지어 있을 때
1. **1588-/1577-/1600-/1644-/1666- 시작 8자리 대표번호** — 회사가 통합 콜센터로 운영하는 경우 사실상 본사 대표
2. **회사 본사 소재지 지역번호 + 첫 번째 등장**. 회사 주소가 "서울"이면 02- 우선
3. **페이지 상단/중앙 등장 번호** (푸터·헤더 광고보다 본문 우선)
4. **여러 번호가 동격으로 보이면** 첫 등장

### B. 그룹 통합 콜센터를 운영하는 자회사
예: 페이지에 "동원그룹 통합 고객센터 1566-0112"만 있고 동원로엑스 별도 번호 없음
→ 1566-0112 채택. 자회사가 그룹 콜센터를 본사 대표로 사용.

자회사 별도 번호가 페이지에 있다면 그것을 우선.

### C. 회사명이 페이지 어디에도 명확히 없을 때
다음 신호 **모두** 부재하면 잘못된 페이지일 가능성 매우 높음 → **"없음" 반환**:
1. 검색 회사명(한글 원형)이 페이지에 등장
2. **회사명의 영문 표기/약칭이 페이지에 등장** (예: "CJ대한통운"의 영문 "CJ Logistics", "현대글로비스"의 "Hyundai Glovis", "한진"의 "Hanjin", "롯데글로벌로지스"의 "Lotte Global Logistics")
3. 페이지 URL/도메인이 회사명과 명백히 연결됨 (예: cjlogistics.com, hyundai-glovis.com, hanjin.com — 페이지 출처가 사용자 메시지에 함께 제공됨)

위 셋 중 **하나라도** 부합하면 회사 공식 페이지로 인정하고 본사 대표번호 추출 진행.

특히 한국 대기업·중견기업은 영문 도메인 + 영문 콘텐츠로 공식 사이트를 운영하는 경우가 매우 흔함. 한글 회사명만 고집하지 말고 영문 변형·도메인 일치도 정체성 확인의 유효한 단서로 활용할 것.

### C-2. 회사명 표기 변형 예시 (한글 → 영문/혼합)

| 한글 검색 회사명 | 페이지에 이런 표기로 등장 가능 |
|---|---|
| CJ대한통운 | CJ Logistics, CJ Korea Express |
| 현대글로비스 | Hyundai Glovis, GLOVIS |
| 한진 | Hanjin Transportation, HANJIN |
| 롯데글로벌로지스 | Lotte Global Logistics, LGL |
| 쿠팡로지스틱스서비스 | Coupang Logistics Services, CLS |
| LX판토스 | LX Pantos, PANTOS |
| 동원로엑스 | Dongwon LOEX, LOEX |
| 삼성SDS | Samsung SDS |
| 포스코인터내셔널 | POSCO International |
| 농협물류 | NH Logistics |
| 한국전력공사 | KEPCO, Korea Electric Power |

도메인이 위 영문 표기와 일치하면(`cjlogistics.com`, `glovis.net`, `hanjin.com`, `lotteglogis.com`, `coupangls.com`, `pantos.com`) **공식 사이트 확정**으로 처리.

### D. 신뢰가 낮은 라벨
- "본사 02-1234-5678 (대표안내)" → 명확, 채택
- "본사 사무실 운영시간 9-18시" + 번호는 다른 곳 → 그 번호 라벨 재확인
- "본사 직통" — "직통"이 부서 직통 약어 가능성, 신중하게

## 예시 모음

### 예시 1: 명확한 본사 라벨
회사명: 현대건설
페이지: "현대건설 회사소개. 본사 02-1671-2114. FAX 02-3743-0001. 안전관리실 02-1671-2222. 윤리경영실 02-1671-2233."
답변: 02-1671-2114

### 예시 2: 그룹 통합 콜센터 (자회사 검색)
회사명: 동원로엑스
페이지: "동원그룹 통합 고객센터 1566-0112. 본사: 서울 서초구 양재동 ... 분당 물류센터 031-957-2445. 안성 사업장 031-634-9318. 평택 터미널 031-100-2000."
답변: 1566-0112

### 예시 3: 잘못된 페이지 (다른 회사)
회사명: 쿠팡로지스틱스서비스
페이지: "나이스정보통신 채용공고 / 본사 02-2122-8000 / 관련회사로 쿠팡, 마켓컬리, 11번가도 있습니다."
답변: 없음

### 예시 4: 인터넷 통합콜센터
회사명: 로젠택배
페이지: "로젠택배 ILOGEN 통합콜센터 1588-9988. 본사 안내. FAX 02-3471-9989. 강남지점 02-555-1234. 인천허브터미널 032-555-5678."
답변: 1588-9988

### 예시 5: 고객센터가 본사 대표
회사명: CJ대한통운
페이지: "CJ대한통운 고객센터 1588-1255. 영업본부 02-700-0114. 기업물류영업 02-700-0118. 본사 주소 서울 중구 청파로 426."
답변: 1588-1255

### 예시 6: 휴대폰만 있는 1인 사업자
회사명: 작은스타트업
페이지: "작은스타트업 소개. 문의: 010-1234-5678. 이메일 contact@startup.kr"
답변: 없음

### 예시 7: 잡포털 자체 번호가 푸터에 박힘
회사명: 어떤회사
페이지: "어떤회사 채용. 본사 02-1234-5678. ... (푸터) 잡코리아 고객센터 1588-9350 / 사람인 1588-9759"
답변: 02-1234-5678

### 예시 8: 공공기관
회사명: 한국전력공사
페이지: "한국전력공사 KEPCO 고객센터 123. 본사 061-345-3114. 서울본부 02-3456-7890."
답변: 061-345-3114

### 예시 9: 라벨 없이 여러 02
회사명: XYZ기업
페이지: "XYZ기업 ... 02-1111-2222 / 02-3333-4444 / 02-5555-6666 ..."
답변: 02-1111-2222

### 예시 10: 본사+지점이 같은 박스
회사명: 어느회사
페이지: "본사 02-100-1000 / 부산지점 051-200-2000 / 대구지점 053-300-3000"
답변: 02-100-1000

### 예시 11: 영문 페이지
회사명: ABC Korea
페이지: "ABC Korea Co., Ltd. Headquarters: Tel +82-2-1234-5678. Fax +82-2-1234-9999. Branch (Busan) +82-51-987-6543."
답변: 02-1234-5678

### 예시 12: FAX가 먼저 등장하는 함정
회사명: 함정회사
페이지: "FAX 02-9999-9999  TEL 02-1234-5678  본사 안내데스크 운영"
답변: 02-1234-5678

### 예시 13: 모회사 번호만 있고 자회사 별도 번호 없음
회사명: 작은자회사
페이지: "작은자회사 소개 ... 모회사 큰그룹 본사 02-100-1000 ... 작은자회사 별도 연락처 없음"
답변: 없음

### 예시 14: 070 인터넷 전화 IT 스타트업
회사명: 테크스타트업
페이지: "테크스타트업 ... Contact 070-1234-5678 ... 채용문의 070-9999-9999"
답변: 070-1234-5678

### 예시 15: 빈 페이지·에러 페이지
회사명: 빈페이지회사
페이지: "404 Not Found. The page you are looking for does not exist."
답변: 없음

## 최종 강조

1. **번호만 반환**: "02-1234-5678" 또는 "없음" 외 모든 텍스트 금지
2. **확신 없으면 무조건 "없음"**: 부정확한 추측이 빈 결과보다 훨씬 나쁨. 실제 영업 콜 시 잘못된 번호로 다른 회사에 연결되면 신뢰가 무너짐
3. **본사가 명확하지 않으면 "없음"**: 본사 명시도 없고 8자리 대표번호도 없고 회사명-페이지 일치도 약하면 빈 결과
4. **하이픈 표준 형식**: "02 1234 5678", "02.1234.5678", "0212345678" 같은 변형도 모두 "02-1234-5678"로 정규화해서 반환"""


def is_available() -> bool:
    """anthropic SDK가 설치되어 있고 API 키가 설정되어 있는가."""
    if not _ANTHROPIC_AVAILABLE:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def extract_phone_with_llm(
    company_name: str,
    page_text: str,
    api_key: str | None = None,
    timeout: float = 30.0,
    page_url: str = "",
) -> str | None:
    """Claude AI에게 페이지 텍스트를 분석시켜 본사 대표번호 1개를 추출.

    Args:
        company_name: 검색 대상 회사명 (예: "동원로엑스")
        page_text: 홈페이지/contact 페이지 본문 텍스트 (HTML 태그 제거 상태)
        api_key: Anthropic API 키. None이면 ANTHROPIC_API_KEY 환경변수 사용
        timeout: API 호출 타임아웃 (초)
        page_url: 페이지 URL (영문 도메인 회사 정체성 확인에 도움)

    Returns:
        정규화된 전화번호 문자열 (예: "02-1234-5678") 또는 None (찾지 못함/에러)
    """
    if not _ANTHROPIC_AVAILABLE:
        log.debug("anthropic SDK not installed; skipping LLM")
        return None
    if not company_name or not page_text or not page_text.strip():
        return None

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        log.debug("ANTHROPIC_API_KEY not set; skipping LLM extraction")
        return None

    if len(page_text) > _MAX_INPUT_CHARS:
        page_text = page_text[:_MAX_INPUT_CHARS]

    try:
        client = anthropic.Anthropic(api_key=key, timeout=timeout)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_OUTPUT_TOKENS,
            # 시스템 프롬프트를 list 형식 + cache_control → 두 번째 호출부터
            # cache_read_input_tokens 동작해 시스템 프롬프트 비용 90% 절감.
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"회사명: {company_name}\n"
                        + (f"페이지 출처(URL): {page_url}\n" if page_url else "")
                        + "\n"
                        + f"페이지 텍스트:\n{page_text}\n\n"
                        + "위 회사의 본사 대표 전화번호를 반환하세요. "
                        + "도메인이나 영문 표기로 회사 정체성이 확인되면 번호 추출 진행. "
                        + "하이픈 형식 번호 1개 또는 '없음'만 답하세요. 다른 텍스트 금지."
                    ),
                }
            ],
        )
    except anthropic.AuthenticationError:
        log.warning("Anthropic API key invalid — LLM extraction disabled")
        return None
    except anthropic.RateLimitError:
        log.warning("Anthropic rate limit hit — skipping LLM for this company")
        return None
    except anthropic.APIStatusError as e:
        log.warning("Anthropic API status error %s: %s", e.status_code, e.message)
        return None
    except anthropic.APIConnectionError as e:
        log.warning("Anthropic API connection error: %s", e)
        return None
    except Exception as e:
        log.warning("LLM extraction unexpected error: %s: %s", type(e).__name__, e)
        return None

    # 캐시 작동 확인 (디버그 로그)
    if response.usage:
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        log.debug(
            "[LLM] %s: in=%d cache_read=%d cache_write=%d out=%d",
            company_name,
            response.usage.input_tokens,
            cache_read,
            cache_write,
            response.usage.output_tokens,
        )

    # 응답 텍스트 추출
    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            break

    if not text or text.lower() in ("없음", "none", "n/a", "null", ""):
        return None

    # normalize()는 텍스트 내부에서 첫 번째 한국 전화번호 패턴을 찾아 정규화.
    # 모델이 "답변: 02-1234-5678입니다." 같이 verbose 응답해도 잘 처리.
    normalized = normalize(text)
    if not normalized:
        log.debug("[LLM] %s: no phone in response: %s", company_name, text[:100])
        return None

    return normalized
