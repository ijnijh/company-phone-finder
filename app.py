"""Streamlit UI - 업체 대표번호 자동 검색."""
from __future__ import annotations

import os
import time
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core.excel_io import build_sample_workbook, parse_input, write_output
from core.icp import load_config
from core.pipeline import process_all

load_dotenv()


# Streamlit Cloud의 st.secrets 값을 process 환경변수로 동기화.
# core/sources/* 들이 os.environ을 직접 읽기 때문에 이 한 줄로 통일된다.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and not os.environ.get(_k):
            os.environ[_k] = _v
except Exception:
    pass


st.set_page_config(page_title="업체 대표번호 자동 검색", page_icon="📞", layout="wide")


# ---------------- 비밀번호 게이트 ----------------
# APP_PASSWORD 환경변수(또는 secrets)가 설정돼 있으면 잠금. 비어있으면 누구나 사용.
# 로컬에서 .env에 안 적어두면 게이트 없이 동작 → 본인 PC에서 편하게.
_APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
if _APP_PASSWORD:
    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False
    if not st.session_state.auth_ok:
        st.title("🔒 접속 비밀번호")
        pw = st.text_input("비밀번호를 입력하세요", type="password")
        if pw:
            if pw == _APP_PASSWORD:
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")
        st.stop()

# ---------------- 사이드바 ----------------
st.sidebar.header("⚙️ 설정")

naver_id = os.environ.get("NAVER_CLIENT_ID", "")
naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
if naver_id and naver_secret:
    st.sidebar.success("네이버 API 키 OK")
else:
    st.sidebar.error("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")
    st.sidebar.markdown(
        """
1. https://developers.naver.com 에서 애플리케이션 등록
2. **검색** API 사용 권한 추가
3. 프로젝트 폴더의 `.env` 파일에:
   ```
   NAVER_CLIENT_ID=...
   NAVER_CLIENT_SECRET=...
   ```
4. Streamlit 재시작
        """
    )

max_workers = st.sidebar.slider("동시 처리 업체 수", 1, 10, 5, help="너무 높이면 외부 사이트가 차단할 수 있습니다.")

with st.sidebar.expander("ICP 사전(.yaml) 미리보기"):
    try:
        cfg = load_config()
        st.write(f"양성 카테고리 {sum(len(v) for v in cfg.positive.values())}개")
        st.write(f"음성 카테고리 {sum(len(v) for v in cfg.negative.values())}개")
        st.json({"weights": cfg.weights, "thresholds": cfg.thresholds})
    except Exception as e:
        st.error(f"ICP 사전 로드 실패: {e}")

st.sidebar.download_button(
    "샘플 엑셀 다운로드",
    data=build_sample_workbook(),
    file_name="sample_companies.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# ---------------- 본문 ----------------
st.title("📞 업체 대표번호 자동 검색 (음주측정기 ICP 인지형)")
st.caption(
    "엑셀(A열=업체명)을 업로드하면 네이버 지도·기업 홈페이지·잡코리아·사람인을 교차분석해 "
    "**음주측정기 잠재 구매처에 부합하는 본사**의 대표번호와 주소(동 단위)를 자동으로 채워드립니다."
)

uploaded = st.file_uploader("엑셀 파일 업로드 (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("좌측 사이드바에서 샘플 엑셀을 받아 형식을 확인하실 수 있습니다.")
    st.stop()

try:
    file_bytes = uploaded.getvalue()
    parsed = parse_input(file_bytes)
except Exception as e:
    st.error(f"엑셀을 읽을 수 없습니다: {e}")
    st.stop()

st.success(f"업체 {len(parsed.rows)}건 인식 완료")

col_a, col_b, col_c = st.columns(3)
col_a.metric("처리 대상", f"{len(parsed.rows)} 건")
col_b.metric("지역 힌트 컬럼", "있음" if parsed.region_hint_col else "없음")
col_c.metric("업종 힌트 컬럼", "있음" if parsed.category_hint_col else "없음")

with st.expander("입력 미리보기 (상위 10건)"):
    preview = pd.DataFrame(
        [
            {
                "행": r.row_index,
                "업체명": r.company_name,
                "지역힌트": r.region_hint,
                "업종힌트": r.category_hint,
            }
            for r in parsed.rows[:10]
        ]
    )
    st.dataframe(preview, use_container_width=True, hide_index=True)

can_run = bool(naver_id and naver_secret) and len(parsed.rows) > 0

if not can_run:
    st.warning("네이버 API 키가 설정되지 않아 시작할 수 없습니다.")
    st.stop()

def _summarize(results: dict[int, dict]) -> dict[str, int]:
    counts = {"매칭확정": 0, "확정필요": 0, "매칭약함": 0, "업체매칭실패": 0}
    for r in results.values():
        s = r.get("매칭상태", "")
        if s in counts:
            counts[s] += 1
    return counts


def _confidence_summary(results: dict[int, dict]) -> dict[str, int]:
    counts = {"검증됨": 0, "지도확인": 0, "홈페이지확인": 0, "잡포털확인": 0, "찾지못함": 0}
    for r in results.values():
        c = r.get("신뢰도", "")
        if c in counts:
            counts[c] += 1
    return counts


if st.button("🔎 검색 시작", type="primary"):
    progress = st.progress(0.0, text="시작 중...")
    log_placeholder = st.empty()
    log_lines: list[str] = []
    started = time.time()

    def _on_progress(done: int, total: int, name: str) -> None:
        ratio = done / total if total else 1.0
        progress.progress(min(ratio, 1.0), text=f"{done}/{total} 완료 — 직전: {name}")

    def _on_log(msg: str) -> None:
        log_lines.append(msg)
        log_placeholder.code("\n".join(log_lines[-12:]), language="text")

    with st.spinner("교차분석 진행 중..."):
        results_main, results_cand = process_all(
            parsed,
            max_workers=max_workers,
            on_progress=_on_progress,
            on_log=_on_log,
        )
        output_bytes = write_output(parsed, results_main, results_cand)

    elapsed = time.time() - started
    st.success(f"완료! 소요시간 {elapsed:.1f}초")

    # 매칭상태 요약
    summary = _summarize(results_main)
    st.markdown("**매칭상태 요약**")
    cols = st.columns(4)
    cols[0].metric("매칭확정", summary["매칭확정"])
    cols[1].metric("확정필요", summary["확정필요"])
    cols[2].metric("매칭약함", summary["매칭약함"])
    cols[3].metric("매칭실패", summary["업체매칭실패"])

    # 신뢰도(전화번호 교차검증) 분포
    conf = _confidence_summary(results_main)
    st.markdown("**전화번호 신뢰도 분포**")
    ccols = st.columns(5)
    ccols[0].metric("검증됨", conf["검증됨"], help="2개 이상 소스 일치 또는 매칭확정+ICP양성+권위소스 격상")
    ccols[1].metric("지도확인", conf["지도확인"], help="네이버 지도 단독")
    ccols[2].metric("홈페이지확인", conf["홈페이지확인"], help="공식 홈페이지 단독")
    ccols[3].metric("잡포털확인", conf["잡포털확인"], help="잡코리아·사람인 단독")
    ccols[4].metric("찾지못함", conf["찾지못함"])

    # 결과 미리보기
    rows = []
    for r in parsed.rows:
        info = results_main.get(r.row_index, {})
        rows.append({
            "업체명": r.company_name,
            "매칭상태": info.get("매칭상태", ""),
            "매칭된업체명": info.get("매칭된업체명", ""),
            "대표번호": info.get("대표번호", ""),
            "신뢰도": info.get("신뢰도", ""),
            "출처": info.get("출처", ""),
            "주소_시도": info.get("주소_시도", ""),
            "주소_시군구": info.get("주소_시군구", ""),
            "주소_동": info.get("주소_동", ""),
            "ICP점수": info.get("ICP점수", ""),
            "후보번호": info.get("후보번호", ""),
            "비고": info.get("비고", ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    fname_stem = (uploaded.name.rsplit(".", 1)[0] if uploaded.name else "result")
    out_name = f"{fname_stem}_phones_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    st.download_button(
        "📥 결과 엑셀 다운로드",
        data=output_bytes,
        file_name=out_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
