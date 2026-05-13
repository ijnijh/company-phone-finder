# 업체 대표번호 자동 검색 웹 앱 (음주측정기 ICP 인지형)

엑셀(A열=업체명)을 업로드하면 네이버 지도·기업 홈페이지·잡코리아·사람인을 교차분석해
**음주측정기 ICP에 부합하는 본사**의 대표번호와 주소(동 단위)를 자동으로 채워주는 Streamlit 앱.

## 빠른 시작

```powershell
# 1) 의존성 설치 (Python 3.10+)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2) 네이버 API 키 설정
copy .env.example .env
# .env 파일을 열어 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 값을 채운다.

# 3) 실행
streamlit run app.py
```

## 네이버 API 키 발급

1. https://developers.naver.com 로그인 → "Application 등록"
2. 사용 API에서 **검색** 체크 → 등록
3. 발급된 Client ID / Client Secret을 `.env`에 붙여넣기
4. 무료 한도: 25,000 calls/day (업체 100개 처리 시 약 200콜 사용)

## 입력 엑셀 형식

- **A열 = 업체명** (필수)
- 선택 컬럼 (헤더에 다음 키워드가 들어 있으면 자동 인식하여 동명 업체 식별에 활용):
  - `주소`, `소재지`, `지역` → 지역 힌트
  - `시도`, `광역시` → 시도 힌트
  - `시군구`, `구`, `시` → 시군구 힌트
  - `업종`, `카테고리`, `분야`, `산업` → 업종 힌트

## 출력 엑셀 구조

원본 시트의 우측에 다음 컬럼이 추가됩니다:

| 컬럼 | 내용 |
|---|---|
| 매칭상태 | 매칭확정 / 확정필요 / 매칭약함 / 업체매칭실패 |
| 매칭된업체명 | 네이버 지도가 반환한 정식 명칭 |
| ICP점수 | 음주측정기 잠재 구매 가능성 점수 |
| 대표번호 | 교차검증된 대표번호 |
| 신뢰도 | 검증됨 / 지도확인 / 홈페이지확인 / 잡포털확인 / 찾지못함 |
| 출처 | "지도+홈페이지+잡코리아" 등 |
| 주소_시도 / 주소_시군구 / 주소_동 / 주소_전체 | 매칭된 업체 주소 (동까지) |
| 후보번호 | 다른 후보들 (`;` 구분) |
| 비고 | 에러·확정필요 안내 |

`확정필요`/`업체매칭실패` 케이스는 추가로 `_후보업체` 시트에 동명 후보 상위 3개가 기록되어
사용자가 눈으로 선택할 수 있도록 합니다.

## 신뢰도 라벨 의미

| 라벨 | 발생 조건 |
|---|---|
| **검증됨** | 서로 다른 2곳 이상의 소스가 같은 번호를 반환했거나, 매칭확정 + ICP 양성 신호 강함 + 권위 소스(지도·홈페이지) 단독 반환 |
| **지도확인** | 네이버 지도만 단독으로 번호 제공 (다른 소스에선 못 찾음) |
| **홈페이지확인** | 공식 홈페이지에서만 번호 발견 |
| **잡포털확인** | 잡코리아·사람인 한 곳에서만 번호 발견 (가장 신중하게 봐야 함) |
| **찾지못함** | 어느 소스도 번호를 반환하지 않음 |

"검증됨"으로 끌어올리는 가장 빠른 방법:
1. 엑셀에 **지역(B열)·업종(C열) 힌트**를 채워 entity matcher의 정확도를 높입니다.
2. `data/icp_keywords.yaml`의 `positive` 섹션에 자주 다루는 업종 키워드를 추가하면 잡포털까지 자동 호출되어 교차검증 가능성이 올라갑니다.

## ICP 사전 수정

`data/icp_keywords.yaml` 파일을 직접 편집하면 양성/음성 키워드, 가중치를 조정할 수 있습니다.
앱 재배포 없이 즉시 반영.

## 폴더 구조

```
core/                 # 비즈니스 로직
  phone.py            # 한국 전화번호 정규식·정규화
  address.py          # 주소 → (시도, 시군구, 동) 추출
  icp.py              # 카테고리 점수
  entity_matcher.py   # 네이버 지도 후보 중 1개 선정
  verifier.py         # 대표번호 가중치 다수결
  excel_io.py         # 엑셀 입출력
  pipeline.py         # 업체별 orchestrator
  sources/            # 외부 데이터 소스 어댑터
data/
  icp_keywords.yaml   # ICP 사전 (편집 가능)
tests/                # 단위 테스트
samples/              # 샘플 엑셀
app.py                # Streamlit 진입점
```

## 웹 주소로 배포 (Streamlit Community Cloud)

본인 PC가 아닌 곳에서도 접속하고 싶다면 무료 클라우드에 올릴 수 있습니다.

1. **GitHub 계정 + 빈 repo 생성**
   - https://github.com 로그인 → 우상단 `+` → New repository → 이름 정하고 **Private** 선택 → Create.
2. **이 폴더를 GitHub에 푸시**
   ```powershell
   cd "C:\Users\jhkim\Documents\Claude code"
   git init
   git add .
   git commit -m "initial"
   git branch -M main
   git remote add origin https://github.com/<당신아이디>/<repo이름>.git
   git push -u origin main
   ```
3. **Streamlit Community Cloud 등록**
   - https://share.streamlit.io 접속 → "Continue with GitHub"
   - "New app" → 방금 만든 repo 선택, branch=`main`, 메인 파일=`app.py` → Deploy.
4. **Secrets 입력** (가장 중요)
   - 배포된 앱 화면에서 우하단 `⋮` → `Settings` → `Secrets` 탭.
   - 다음 형식으로 붙여넣고 Save:
     ```toml
     NAVER_CLIENT_ID = "여기에_아이디"
     NAVER_CLIENT_SECRET = "여기에_시크릿"
     APP_PASSWORD = "원하는_비밀번호"
     ```
   - `APP_PASSWORD`를 설정하지 않으면 URL을 아는 사람은 누구나 사용할 수 있게 되니, **반드시 채워주세요**.
5. 잠시 후 `https://<이름>.streamlit.app` 같은 URL이 발급되면 끝. 브라우저 즐겨찾기에 추가해두면 됩니다.

> `.env`와 실제 `.streamlit/secrets.toml`은 `.gitignore`로 차단되어 있어 GitHub에 올라가지 않습니다.

## 알려진 제약

- 잡코리아·사람인은 비공식 스크래핑 → 사이트 구조 변경 시 셀렉터 업데이트 필요
- 동명 업체가 많고 사용자 힌트도 없을 경우 `확정필요` 라벨로 분류되어 수동 확인 필요
- 1차 버전은 사업자등록정보 API 미사용 (추후 통합 시 disambiguation 정확도 향상)
- Streamlit Community Cloud 무료 플랜은 일정 시간 사용이 없으면 슬립 상태가 됩니다. 다시 접속하면 30초~1분 내에 자동 깨어납니다.
