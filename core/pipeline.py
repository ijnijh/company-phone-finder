"""업체 1건당 entity matching → phone verification 파이프라인.

병렬 처리(ThreadPoolExecutor)와 진행률 콜백을 제공.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

from core import phone as phone_mod
from core.entity_matcher import MatchResult, ScoredCandidate, select as entity_select
from core.excel_io import ExcelInput, InputRow
from core.icp import IcpConfig, load_config
from core.sources import (
    company_homepage,
    jobkorea,
    llm_extractor,
    naver_local,
    naver_web,
    saramin,
)
from core.verifier import VerifyResult, decide

log = logging.getLogger(__name__)


@dataclass
class CompanyResult:
    row_index: int
    company_name: str
    result_row: dict             # excel_io.write_output용 dict
    candidates_dump: list[dict]  # 후보 시트용


def process_all(
    excel_input: ExcelInput,
    config: Optional[IcpConfig] = None,
    max_workers: int = 5,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> tuple[dict[int, dict], dict[int, list[dict]]]:
    """모든 업체를 처리. 결과 dict 두 개(메인 결과, 후보 덤프)를 반환."""
    cfg = config or load_config()
    results_main: dict[int, dict] = {}
    results_candidates: dict[int, list[dict]] = {}
    total = len(excel_input.rows)
    done = 0

    def _log(msg: str) -> None:
        if on_log:
            try:
                on_log(msg)
            except Exception:
                pass
        log.info(msg)

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
        future_to_row = {
            ex.submit(_process_one, row, cfg, _log): row
            for row in excel_input.rows
        }
        for fut in as_completed(future_to_row):
            row = future_to_row[fut]
            try:
                res = fut.result()
            except Exception as e:
                _log(f"[{row.company_name}] 처리 실패: {e}")
                res = _failure_result(row, f"예외: {e}")
            results_main[row.row_index] = res.result_row
            results_candidates[row.row_index] = res.candidates_dump
            done += 1
            if on_progress:
                try:
                    on_progress(done, total, row.company_name)
                except Exception:
                    pass

    return results_main, results_candidates


def _process_one(row: InputRow, config: IcpConfig, log_fn: Callable[[str], None]) -> CompanyResult:
    company = row.company_name
    log_fn(f"[{company}] 시작")

    # 단계 1: Entity matching (네이버 지도)
    try:
        items = naver_local.search(company, display=5)
    except Exception as e:
        log_fn(f"[{company}] 네이버 지도 API 오류: {e}")
        return _failure_result(row, f"네이버 지도 API 오류: {e}")

    hints = {"region": row.region_hint, "category": row.category_hint}
    match: MatchResult = entity_select(company, items, hints, config)

    candidates_dump = _build_candidates_dump(match)

    if match.status == "업체매칭실패" or not match.chosen:
        return CompanyResult(
            row_index=row.row_index,
            company_name=company,
            result_row={
                "매칭상태": match.status,
                "매칭된업체명": "",
                "ICP점수": "",
                "대표번호": "",
                "신뢰도": "찾지못함",
                "출처": "",
                "주소_시도": "",
                "주소_시군구": "",
                "주소_동": "",
                "주소_전체": "",
                "후보번호": "",
                "비고": match.note,
            },
            candidates_dump=candidates_dump,
        )

    chosen: ScoredCandidate = match.chosen
    log_fn(f"[{company}] 매칭: {chosen.item.title} ({chosen.address.full or chosen.item.address}) score={chosen.score:.1f}")

    # 단계 2: Phone verification
    by_source: dict[str, list[str]] = {}

    # 2-1) 네이버 지도가 준 telephone
    if chosen.item.telephone:
        normalized = phone_mod.normalize(chosen.item.telephone)
        if normalized and phone_mod.is_corporate(normalized):
            by_source["naver_local"] = [normalized]

    # 2-2) 홈페이지 — 두 URL 후보 모두에서 추출 시도해 결과 합침
    #   ① 네이버 지도의 link 필드 (단, place.naver.com 같은 제외 도메인은 거부)
    #   ② naver_web.find_homepage가 웹검색으로 찾은 URL
    #   두 후보가 다른 URL이면 양쪽 다 fetch — 어느 한쪽이 실패해도 다른 쪽이
    #   백업이 되도록.
    homepage_urls: list[str] = []
    link = (chosen.item.link or "").strip()
    if link and not naver_web.is_excluded_homepage_domain(link):
        homepage_urls.append(link)
    try:
        searched = naver_web.find_homepage(company)
        if searched and searched not in homepage_urls:
            homepage_urls.append(searched)
    except Exception as e:
        log_fn(f"[{company}] find_homepage 오류: {e}")

    all_home_phones: list[str] = []
    for hu in homepage_urls:
        try:
            phones = company_homepage.fetch_phones(hu, company_name=company)
            if phones:
                log_fn(f"[{company}] 홈페이지({hu}) 후보 {len(phones)}건")
                for p in phones:
                    if p not in all_home_phones:
                        all_home_phones.append(p)
        except Exception as e:
            log_fn(f"[{company}] 홈페이지 추출 오류({hu}): {e}")

    if all_home_phones:
        by_source["homepage"] = all_home_phones[:3]

    # 2-3) LLM 추출 — Claude AI가 홈페이지 텍스트를 직접 분석해 본사 대표번호 추출
    #      (정규식 룰의 사각지대 — 라벨 변형·그룹 콜센터·잘못된 페이지 매칭 등 해결)
    if llm_extractor.is_available() and homepage_urls:
        try:
            llm_text_chunks: list[str] = []
            for hu in homepage_urls[:2]:  # 최대 2개 URL 텍스트 결합
                text_blob = company_homepage.fetch_text(hu, company_name=company)
                if text_blob:
                    llm_text_chunks.append(text_blob)
            if llm_text_chunks:
                combined_text = "\n\n".join(llm_text_chunks)
                llm_phone = llm_extractor.extract_phone_with_llm(company, combined_text)
                if llm_phone:
                    by_source["llm"] = [llm_phone]
                    log_fn(f"[{company}] LLM 추출 성공: {llm_phone}")
        except Exception as e:
            log_fn(f"[{company}] LLM 추출 오류: {e}")

    # 2-4) 잡코리아·사람인 — ICP 양성 신호가 있을 때만 (음식점·미용실 노이즈 차단)
    has_positive_icp = chosen.detail.get("icp_pos_keywords", 0) >= 1
    if has_positive_icp:
        try:
            phones = jobkorea.fetch_phones(company)
            if phones:
                by_source["jobkorea"] = phones
        except Exception as e:
            log_fn(f"[{company}] 잡코리아 오류: {e}")
        try:
            phones = saramin.fetch_phones(company)
            if phones:
                by_source["saramin"] = phones
        except Exception as e:
            log_fn(f"[{company}] 사람인 오류: {e}")

    verify: VerifyResult = decide(by_source)

    # 격상 룰: 매칭이 확실하고(매칭확정) ICP 양성 신호가 충분하며
    # 권위 소스(LLM, 네이버 지도, 또는 공식 홈페이지)가 번호를 단독 반환한 경우,
    # 교차검증된 것에 준하는 신뢰로 격상한다.
    promoted = False
    if (
        match.status == "매칭확정"
        and chosen.detail.get("icp_pos_keywords", 0) >= 1
        and verify.confidence in ("AI확인", "지도확인", "홈페이지확인")
    ):
        verify.confidence = "검증됨"
        promoted = True

    addr = chosen.address
    candidate_str = "; ".join(p for p, _, _ in verify.candidates[:3])
    sources_str = "+".join(_source_label(s) for s in verify.sources)

    # 진단(diagnostics): 어디서 어떻게 뽑혔는지 추적 가능하도록 비고에 합쳐 기록
    diag_parts = []
    if by_source.get("llm"):
        diag_parts.append(f"AI={by_source['llm'][0]}")
    elif llm_extractor.is_available() and homepage_urls:
        diag_parts.append("AI=∅")
    if by_source.get("naver_local"):
        diag_parts.append(f"지도={by_source['naver_local'][0]}")
    else:
        diag_parts.append("지도=∅")
    if by_source.get("homepage"):
        diag_parts.append(f"홈페이지={by_source['homepage'][0]}")
    else:
        # 빈 결과일 때 URL 후보 자체가 있었는지 표시
        if homepage_urls:
            urls_short = ", ".join(_short_url(u) for u in homepage_urls[:2])
            diag_parts.append(f"홈페이지=∅(시도:{urls_short})")
        else:
            diag_parts.append("홈페이지=∅(URL미발견)")
    if by_source.get("jobkorea"):
        diag_parts.append(f"잡코리아={by_source['jobkorea'][0]}")
    if by_source.get("saramin"):
        diag_parts.append(f"사람인={by_source['saramin'][0]}")

    notes = []
    if match.note:
        notes.append(match.note)
    if not verify.best_phone:
        notes.append("전화번호 후보 없음")
    if promoted:
        notes.append("단일 권위소스 자동 격상")
    notes.append("진단: " + " / ".join(diag_parts))
    note = " | ".join(notes)

    return CompanyResult(
        row_index=row.row_index,
        company_name=company,
        result_row={
            "매칭상태": match.status,
            "매칭된업체명": chosen.item.title,
            "ICP점수": round(chosen.score, 1),
            "대표번호": verify.best_phone,
            "신뢰도": verify.confidence,
            "출처": sources_str,
            "주소_시도": addr.sido,
            "주소_시군구": addr.sigungu,
            "주소_동": addr.dong,
            "주소_전체": addr.full,
            "후보번호": candidate_str,
            "비고": note,
        },
        candidates_dump=candidates_dump if match.status != "매칭확정" else [],
    )


def _build_candidates_dump(match: MatchResult) -> list[dict]:
    """확정필요·매칭약함·실패 케이스를 위해 상위 3개 후보를 dump."""
    dump: list[dict] = []
    for i, cand in enumerate(match.alternates[:3], start=1):
        dump.append({
            "rank": i,
            "title": cand.item.title,
            "category": cand.item.category,
            "address": cand.address.full or cand.item.address,
            "phone": cand.item.telephone,
            "icp_score": round(cand.score, 1),
        })
    return dump


def _failure_result(row: InputRow, note: str) -> CompanyResult:
    return CompanyResult(
        row_index=row.row_index,
        company_name=row.company_name,
        result_row={
            "매칭상태": "업체매칭실패",
            "매칭된업체명": "",
            "ICP점수": "",
            "대표번호": "",
            "신뢰도": "찾지못함",
            "출처": "",
            "주소_시도": "",
            "주소_시군구": "",
            "주소_동": "",
            "주소_전체": "",
            "후보번호": "",
            "비고": note,
        },
        candidates_dump=[],
    )


def _source_label(source: str) -> str:
    return {
        "llm": "AI",
        "naver_local": "지도",
        "homepage": "홈페이지",
        "jobkorea": "잡코리아",
        "saramin": "사람인",
    }.get(source, source)


def _short_url(url: str) -> str:
    """진단 표시용 — 도메인만."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or url[:30]
    except Exception:
        return url[:30]
