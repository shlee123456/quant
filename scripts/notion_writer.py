#!/usr/bin/env python3
"""
Notion Writer - 호스트에서 cron으로 실행하는 노션 작성 스크립트

컨테이너의 scheduler.py가 생성한 시장 분석 JSON을 읽어
Claude CLI로 Notion 페이지를 작성합니다.

Usage:
    # 실제 실행 (병렬 모드 - 기본값)
    python scripts/notion_writer.py

    # 레거시 모드 (단일 Claude)
    python scripts/notion_writer.py --legacy

    # Dry-run (JSON 탐색만, 노션 작성 안 함)
    python scripts/notion_writer.py --dry-run

    # Dry-run-prompts (프롬프트 파일로 저장, Claude 호출 안 함)
    python scripts/notion_writer.py --dry-run-prompts

Cron 등록 예시 (06:15 KST, 컨테이너 06:10 수집 완료 후):
    15 6 * * * cd /home/puzzle/quant && python scripts/notion_writer.py >> logs/notion_writer.log 2>&1
"""

import sys
import os
import subprocess
import argparse
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional, Dict

import pytz

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.market_analysis_prompt import build_analysis_prompt, get_notion_page_id
from trading_bot.parallel_prompt_builder import (
    WORKER_MODELS,
    precompute_session_metrics,
    build_worker_a_prompt,
    build_worker_b_prompt,
    build_worker_c_prompt,
    build_notion_writer_prompt,
    assemble_sections,
    validate_assembly,
    _load_previous_top3,
    _save_top3_marker,
)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MARKET_ANALYSIS_DIR = PROJECT_ROOT / "data" / "market_analysis"
MARKER_SUFFIX = ".notion_done"


def find_today_json() -> Path | None:
    """오늘 날짜의 시장 분석 JSON 파일을 찾습니다."""
    kst = pytz.timezone("Asia/Seoul")
    today = datetime.now(kst).strftime("%Y-%m-%d")

    if not MARKET_ANALYSIS_DIR.is_dir():
        logger.warning(f"시장 분석 디렉토리 없음: {MARKET_ANALYSIS_DIR}")
        return None

    # {YYYY-MM-DD}.json 패턴 검색 (MarketAnalyzer.save_json 형식)
    candidates = sorted(MARKET_ANALYSIS_DIR.glob(f"{today}*.json"))
    if not candidates:
        logger.info(f"오늘({today}) 분석 JSON 파일 없음")
        return None

    # 가장 최신 파일 반환
    return candidates[-1]


def is_already_done(json_path: Path) -> bool:
    """마커 파일로 이미 처리된 JSON인지 확인합니다."""
    marker = json_path.with_suffix(json_path.suffix + MARKER_SUFFIX)
    return marker.exists()


def mark_done(json_path: Path) -> None:
    """처리 완료 마커 파일을 생성합니다."""
    marker = json_path.with_suffix(json_path.suffix + MARKER_SUFFIX)
    marker.write_text(datetime.now().isoformat())
    logger.info(f"마커 생성: {marker}")


def find_session_reports_dir() -> str | None:
    """당일 세션 리포트 디렉토리를 찾습니다."""
    from datetime import timedelta

    kst = pytz.timezone("Asia/Seoul")
    now_kst = datetime.now(kst)
    # 06:15에 실행되므로, 세션 시작일은 전날
    session_date = (now_kst - timedelta(hours=7)).strftime("%Y-%m-%d")
    reports_dir = PROJECT_ROOT / "reports" / session_date

    if reports_dir.is_dir():
        logger.info(f"세션 리포트 디렉토리: {reports_dir}")
        return str(reports_dir)

    logger.info(f"세션 리포트 디렉토리 없음: {reports_dir}")
    return None


def run_claude(prompt: str) -> bool:
    """Claude CLI를 실행하여 노션 페이지를 작성합니다."""
    logger.info("Claude CLI로 노션 작성 요청 중...")

    # CLAUDECODE 환경 변수 제거 (중첩 세션 방지)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        proc = subprocess.run(
            [
                "claude", "-p",
                "--model", "claude-sonnet-4-6",
                "--allowedTools", "mcp__claude_ai_Notion__*,Read,WebSearch",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )

        if proc.returncode == 0:
            logger.info("노션 작성 완료")
            return True

        logger.error(f"Claude 실패 (returncode={proc.returncode})")
        if proc.stderr:
            logger.error(f"stderr: {proc.stderr[:500]}")
        return False

    except subprocess.TimeoutExpired:
        logger.error("Claude 타임아웃 (1800초 초과)")
        return False
    except FileNotFoundError:
        logger.error("Claude CLI를 찾을 수 없습니다. claude가 PATH에 있는지 확인하세요.")
        return False


# ---------------------------------------------------------------------------
# 병렬 실행 함수들
# ---------------------------------------------------------------------------

def run_claude_worker(
    worker_name: str,
    prompt: str,
    tools: str,
    timeout: int = 600,
    max_budget: float = 0.50,
) -> Tuple[bool, str, Optional[float]]:
    """
    단일 Claude CLI 워커를 서브프로세스로 실행합니다.

    Args:
        worker_name: 워커 식별 이름 (예: "worker_a", "worker_b", "worker_c", "notion_writer")
        prompt: Claude에 전달할 프롬프트
        tools: 허용할 도구 (콤마 구분 문자열). 빈 문자열이면 도구 없음.
        timeout: 서브프로세스 타임아웃 (초)
        max_budget: 최대 비용 한도 (USD)

    Returns:
        (success, markdown_output, cost_usd) 튜플
    """
    logger.info(f"[{worker_name}] Claude 워커 시작 (timeout={timeout}s, budget=${max_budget:.2f})")

    # CLAUDECODE 환경 변수 제거 (중첩 세션 방지)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    # 모델 선택
    model = WORKER_MODELS.get(worker_name, "claude-sonnet-4-6")

    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
        "--max-budget-usd", str(max_budget),
    ]

    if tools:
        cmd.extend(["--allowedTools", tools])

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        if proc.returncode != 0:
            logger.error(f"[{worker_name}] Claude 실패 (returncode={proc.returncode})")
            if proc.stderr:
                logger.error(f"[{worker_name}] stderr: {proc.stderr[:500]}")
            return (False, "", None)

        # JSON 출력 파싱
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.error(f"[{worker_name}] JSON 파싱 실패. stdout 길이: {len(proc.stdout)}")
            if proc.stdout:
                logger.error(f"[{worker_name}] stdout (앞 300자): {proc.stdout[:300]}")
            return (False, "", None)

        # 에러 체크
        if result.get("is_error", False):
            logger.error(f"[{worker_name}] Claude가 에러를 반환: {str(result.get('result', ''))[:300]}")
            return (False, "", None)

        markdown_output = result.get("result", "")
        cost_usd = result.get("total_cost_usd")
        session_id = result.get("session_id", "N/A")

        logger.info(
            f"[{worker_name}] 완료 (출력 길이: {len(markdown_output)}자, "
            f"비용: ${cost_usd:.4f}, session: {session_id})" if cost_usd else
            f"[{worker_name}] 완료 (출력 길이: {len(markdown_output)}자)"
        )

        # 출력이 비어있으면 예산 소진으로 인한 실패로 간주
        if not markdown_output.strip():
            logger.warning(
                f"[{worker_name}] 출력이 비어있음 (예산 소진 가능성). "
                f"비용: ${cost_usd:.4f}" if cost_usd else
                f"[{worker_name}] 출력이 비어있음"
            )
            return (False, "", cost_usd)

        return (True, markdown_output, cost_usd)

    except subprocess.TimeoutExpired:
        logger.error(f"[{worker_name}] 타임아웃 ({timeout}초 초과)")
        return (False, "", None)
    except FileNotFoundError:
        logger.error(f"[{worker_name}] Claude CLI를 찾을 수 없습니다.")
        return (False, "", None)


def _run_with_delay(fn, delay: float, *args, **kwargs):
    """지연 후 함수를 실행하는 헬퍼 (ThreadPoolExecutor 스태거용)."""
    if delay > 0:
        time.sleep(delay)
    return fn(*args, **kwargs)


def _run_legacy_fallback(json_path: str, session_reports_dir: Optional[str]) -> bool:
    """레거시 단일 Claude 모드로 폴백합니다."""
    logger.warning("병렬 모드 실패 → 레거시 단일 Claude 모드로 폴백")
    prompt = build_analysis_prompt(json_path, session_reports_dir=session_reports_dir)
    logger.info(f"레거시 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return run_claude(prompt)


def _notify_worker_failure(worker_name: str, detail: str) -> None:
    """워커 실패 시 Slack 알림을 전송합니다."""
    try:
        from trading_bot.notifications import NotificationService
        notifier = NotificationService()
        notifier.notify_error(
            f"Notion Writer {worker_name} 실패",
            context=detail,
        )
    except Exception as e:
        logger.warning(f"Slack 알림 전송 실패 (무시): {e}")


def run_parallel_notion_writer(json_path: str, session_reports_dir: Optional[str]) -> bool:
    """
    병렬 Claude CLI 실행으로 Notion 페이지를 작성합니다.

    3개의 워커가 병렬로 섹션을 생성하고, 결과를 조합하여
    Notion Writer Claude가 최종 페이지를 작성합니다.

    Args:
        json_path: 시장 분석 JSON 파일 경로
        session_reports_dir: 세션 리포트 디렉토리 경로 (선택)

    Returns:
        성공 여부
    """
    logger.info("=" * 40)
    logger.info("병렬 모드 시작")
    logger.info("=" * 40)

    # 1. JSON 데이터 로드
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    market_data = {k: v for k, v in data.items() if k not in ("news", "fear_greed_index", "macro", "events", "fundamentals")}
    news_data = data.get("news", {})
    fear_greed_data = data.get("fear_greed_index", {})
    macro_data = data.get("macro")
    events_data = data.get("events")
    fundamentals_data = data.get("fundamentals")

    # 2. 세션 메트릭 사전 계산
    session_metrics = None
    if session_reports_dir and os.path.isdir(session_reports_dir):
        logger.info(f"세션 메트릭 사전 계산: {session_reports_dir}")
        session_metrics = precompute_session_metrics(session_reports_dir)

    today = datetime.now().strftime("%Y-%m-%d")
    has_sessions = session_metrics is not None and session_metrics.get("has_sessions", False)

    # 2.5. 전일 대비 변화 계산
    daily_changes = None
    try:
        from trading_bot.market_analyzer import MarketAnalyzer
        previous_data = MarketAnalyzer._load_previous_day_json(today, str(Path(json_path).parent))
        if previous_data:
            daily_changes = MarketAnalyzer._calculate_daily_changes(data, previous_data)
            logger.info(f"전일 변화 계산 완료 (이전 날짜: {daily_changes.get('previous_date', 'N/A')})")
    except Exception as e:
        logger.warning(f"전일 변화 계산 실패 (무시): {e}")

    # 2.7. 이전 TOP 3 로드 (중복 방지)
    previous_top3 = _load_previous_top3(str(Path(json_path).parent), today)
    if previous_top3:
        logger.info(f"이전 TOP 3: {previous_top3}")

    # 3. 워커 프롬프트 빌드
    intelligence_data = data.get("intelligence")

    prompt_a = build_worker_a_prompt(
        market_data, today, macro_data=macro_data,
        intelligence_data=intelligence_data,
        events_data=events_data,
        fundamentals_data=fundamentals_data,
        fear_greed_data=fear_greed_data,
        daily_changes=daily_changes,
    )
    prompt_c = build_worker_c_prompt(
        market_data, session_metrics or {}, today, has_sessions,
        intelligence_data=intelligence_data,
        daily_changes=daily_changes,
    )

    reflection_enabled = os.getenv('REFLECTION_ENABLED', 'true').lower() == 'true'
    top3_symbols_code = []  # Will be set by build_worker_b_prompt

    # 4. 워커 설정
    worker_a_cfg = {"prompt": prompt_a, "tools": "WebSearch", "timeout": 600, "max_budget": 2.00}
    worker_b_cfg = {"tools": "WebSearch,Read", "timeout": 600, "max_budget": 3.00}
    worker_c_cfg = {"prompt": prompt_c, "tools": "", "timeout": 300, "max_budget": 0.30}

    # 5. 실행 (Reflection 모드: A+C 병렬 → B 직렬, 기존: A+B+C 병렬)
    results: Dict[str, Tuple[bool, str, Optional[float]]] = {}

    if reflection_enabled:
        logger.info("Reflection 모드: Worker-A + Worker-C 병렬 → Worker-B 직렬")

        # Phase 1: A + C 병렬
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(run_claude_worker, "Worker-A", worker_a_cfg["prompt"], worker_a_cfg["tools"], worker_a_cfg["timeout"], worker_a_cfg["max_budget"])
            future_c = executor.submit(run_claude_worker, "Worker-C", worker_c_cfg["prompt"], worker_c_cfg["tools"], worker_c_cfg["timeout"], worker_c_cfg["max_budget"])

            try:
                results["Worker-A"] = future_a.result()
            except Exception as e:
                logger.error(f"[Worker-A] 예외 발생: {e}")
                results["Worker-A"] = (False, "", None)

            try:
                results["Worker-C"] = future_c.result()
            except Exception as e:
                logger.error(f"[Worker-C] 예외 발생: {e}")
                results["Worker-C"] = (False, "", None)

        # Phase 2: B with A's context (직렬)
        worker_a_output = results["Worker-A"][1] if results["Worker-A"][0] else ""
        worker_a_context = worker_a_output[:3000] if worker_a_output else None

        prompt_b, top3_symbols_code = build_worker_b_prompt(
            market_data, news_data, fear_greed_data, today,
            intelligence_data=intelligence_data,
            worker_a_context=worker_a_context,
            daily_changes=daily_changes,
            previous_top3=previous_top3,
        )
        logger.info(f"프롬프트 생성 완료 - A: {len(prompt_a)}자, B: {len(prompt_b)}자, C: {len(prompt_c)}자")

        try:
            results["Worker-B"] = run_claude_worker("Worker-B", prompt_b, worker_b_cfg["tools"], worker_b_cfg["timeout"], worker_b_cfg["max_budget"])
        except Exception as e:
            logger.error(f"[Worker-B] 예외 발생: {e}")
            results["Worker-B"] = (False, "", None)
    else:
        # 기존 3개 병렬 실행
        prompt_b, top3_symbols_code = build_worker_b_prompt(
            market_data, news_data, fear_greed_data, today,
            intelligence_data=intelligence_data,
            daily_changes=daily_changes,
            previous_top3=previous_top3,
        )
        logger.info(f"프롬프트 생성 완료 - A: {len(prompt_a)}자, B: {len(prompt_b)}자, C: {len(prompt_c)}자")

        worker_configs = {
            "Worker-A": worker_a_cfg,
            "Worker-B": {**worker_b_cfg, "prompt": prompt_b},
            "Worker-C": worker_c_cfg,
        }
        stagger_delays = {"Worker-A": 0, "Worker-B": 2, "Worker-C": 4}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            for name, cfg in worker_configs.items():
                delay = stagger_delays[name]
                future = executor.submit(
                    _run_with_delay,
                    run_claude_worker,
                    delay,
                    name,
                    cfg["prompt"],
                    cfg["tools"],
                    cfg["timeout"],
                    cfg["max_budget"],
                )
                futures[future] = name

            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    logger.error(f"[{name}] 예외 발생: {e}")
                    results[name] = (False, "", None)

    # 6. 결과 수집 및 비용 로깅
    costs: Dict[str, float] = {}
    worker_outputs: Dict[str, str] = {}
    success_count = 0

    for name in ["Worker-A", "Worker-B", "Worker-C"]:
        ok, output, cost = results.get(name, (False, "", None))
        costs[name] = cost or 0.0
        if ok and output:
            worker_outputs[name] = output
            success_count += 1
            logger.info(f"[{name}] 성공")
        else:
            logger.warning(f"[{name}] 실패")

    logger.info(f"워커 결과: {success_count}/3 성공")

    # 7. 워커별 설정 (재시도에 사용, prompt_b는 이 시점에서 항상 정의됨)
    all_worker_cfgs = {
        "Worker-A": {**worker_a_cfg, "prompt": prompt_a},
        "Worker-B": {**worker_b_cfg, "prompt": prompt_b},
        "Worker-C": {**worker_c_cfg, "prompt": prompt_c},
    }

    # 8. 핵심 워커 실패 → 재시도 → 레거시 폴백
    # Worker A (시장요약), B (Top3/F&G/뉴스)가 없으면 리포트 가치 없음
    if success_count == 0:
        logger.error("모든 워커 실패")
        _notify_worker_failure("전체 워커", "모든 워커(A/B/C)가 실패하여 레거시 폴백으로 전환합니다.")
        return _run_legacy_fallback(json_path, session_reports_dir)

    failed_core = [k for k in ["Worker-A", "Worker-B"] if k not in worker_outputs]
    if failed_core:
        logger.warning(f"핵심 워커 실패 {failed_core} → 재시도 (예산 2배 상향)")
        for name in failed_core:
            cfg = all_worker_cfgs[name]
            retry_budget = cfg["max_budget"] * 2.0  # 예산 100% 상향
            logger.info(f"[{name}] 재시도 (budget=${retry_budget:.2f})")
            ok, output, cost = run_claude_worker(
                name, cfg["prompt"], cfg["tools"], cfg["timeout"], retry_budget
            )
            costs[name] = costs.get(name, 0) + (cost or 0.0)
            if ok and output:
                worker_outputs[name] = output
                success_count += 1
                logger.info(f"[{name}] 재시도 성공")
            else:
                logger.warning(f"[{name}] 재시도 실패")

        # 재시도 후에도 핵심 워커가 빠져 있으면 레거시 폴백
        still_failed = [k for k in ["Worker-A", "Worker-B"] if k not in worker_outputs]
        if still_failed:
            logger.warning(f"핵심 워커 재시도 실패 {still_failed} → 레거시 폴백")
            return _run_legacy_fallback(json_path, session_reports_dir)

    # 9. Worker-C 실패 시 재시도 → 레거시 폴백
    if "Worker-C" not in worker_outputs:
        logger.warning("[Worker-C] 실패 → 재시도 (타임아웃 2배, 예산 2배 상향)")
        _notify_worker_failure("Worker-C", "Worker-C 실패 - 재시도 중 (timeout=600s, budget=$0.60)")
        cfg_c = all_worker_cfgs["Worker-C"]
        retry_timeout = cfg_c["timeout"] * 2  # 300s → 600s
        retry_budget = cfg_c["max_budget"] * 2.0  # $0.30 → $0.60
        logger.info(f"[Worker-C] 재시도 (timeout={retry_timeout}s, budget=${retry_budget:.2f})")
        ok, output, cost = run_claude_worker(
            "Worker-C", cfg_c["prompt"], cfg_c["tools"], retry_timeout, retry_budget
        )
        costs["Worker-C"] = costs.get("Worker-C", 0) + (cost or 0.0)
        if ok and output:
            worker_outputs["Worker-C"] = output
            success_count += 1
            logger.info("[Worker-C] 재시도 성공")
        else:
            logger.warning("[Worker-C] 재시도 실패 → 레거시 폴백")
            _notify_worker_failure("Worker-C", "Worker-C 재시도도 실패하여 레거시 폴백으로 전환합니다.")
            return _run_legacy_fallback(json_path, session_reports_dir)

    # 10. 섹션 조합
    assembled = assemble_sections(
        worker_a_output=worker_outputs["Worker-A"],
        worker_b_output=worker_outputs["Worker-B"],
        worker_c_output=worker_outputs["Worker-C"],
        today=today,
    )

    # 11. 유효성 검증 (모든 워커 성공 시에만 도달)
    if has_sessions:
        expected = ["# 1.", "# 2.", "# 3.", "# 4.", "# 5.",
                     "# 6.", "# 7.", "# 8.", "# 9.", "# 10."]
    else:
        expected = ["# 1.", "# 2.", "# 3.", "# 4.", "# 5.",
                     "# 6.", "# 7.", "# 8."]

    if macro_data:
        expected = ["# 0."] + expected

    if not validate_assembly(assembled, expected):
        logger.error("조합 결과 유효성 검증 실패 → 레거시 폴백")
        return _run_legacy_fallback(json_path, session_reports_dir)

    logger.info(f"섹션 조합 완료 (총 길이: {len(assembled)}자)")

    # 12. Notion Writer Claude 실행
    parent_page_id = get_notion_page_id()
    notion_prompt = build_notion_writer_prompt(assembled, today, parent_page_id)

    logger.info(f"Notion Writer 프롬프트 생성 완료 (길이: {len(notion_prompt)}자)")

    notion_ok, notion_output, notion_cost = run_claude_worker(
        worker_name="Notion-Writer",
        prompt=notion_prompt,
        tools="mcp__claude_ai_Notion__*",
        timeout=300,
        max_budget=0.30,
    )

    costs["Notion-Writer"] = notion_cost or 0.0

    # 12.5. Notion Writer 실패 시 1회 재시도 (budget 2배)
    if not notion_ok:
        logger.warning("[Notion-Writer] 실패 → 재시도 (budget 2배, timeout 2배)")
        _notify_worker_failure("Notion-Writer", "Notion Writer 실패 - 재시도 중 (budget=$0.60, timeout=600s)")
        retry_ok, retry_output, retry_cost = run_claude_worker(
            worker_name="Notion-Writer",
            prompt=notion_prompt,
            tools="mcp__claude_ai_Notion__*",
            timeout=600,
            max_budget=0.60,
        )
        costs["Notion-Writer"] = costs.get("Notion-Writer", 0) + (retry_cost or 0.0)
        if retry_ok:
            notion_ok = True
            notion_output = retry_output
            logger.info("[Notion-Writer] 재시도 성공")
        else:
            logger.error("[Notion-Writer] 재시도 실패 → 레거시 폴백")
            _notify_worker_failure("Notion-Writer", "Notion Writer 재시도도 실패하여 레거시 폴백으로 전환합니다.")
            return _run_legacy_fallback(json_path, session_reports_dir)

    # 13. 비용 요약 로깅
    total_cost = sum(costs.values())
    logger.info(
        f"총 비용: ${total_cost:.4f} "
        f"(A=${costs.get('Worker-A', 0):.4f}, "
        f"B=${costs.get('Worker-B', 0):.4f}, "
        f"C=${costs.get('Worker-C', 0):.4f}, "
        f"Writer=${costs.get('Notion-Writer', 0):.4f})"
    )

    # 14. Notion 페이지 생성 검증 (출력에 URL이 포함되어야 함)
    import re
    notion_url_match = re.search(r'NOTION_PAGE_URL:\s*(https?://\S+)', notion_output)
    if not notion_url_match:
        # URL 마커가 없으면 notion.so URL이라도 있는지 확인
        notion_url_fallback = re.search(r'https://(?:www\.)?notion\.(?:so|site)/\S+', notion_output)
        if not notion_url_fallback:
            logger.error(
                "Notion Writer가 성공을 반환했지만 페이지 URL이 출력에 없습니다. "
                "실제 페이지 생성에 실패했을 가능성이 높습니다."
            )
            logger.error(f"Notion Writer 출력 (앞 500자): {notion_output[:500]}")
            _notify_worker_failure("Notion-Writer", "페이지 URL 미확인 - 실제 생성 실패 가능성")
            return False
        else:
            logger.info(f"Notion 페이지 URL (fallback): {notion_url_fallback.group()}")
    else:
        logger.info(f"Notion 페이지 URL: {notion_url_match.group(1)}")

    # 15. TOP 3 마커 저장 (다음날 중복 방지용 — 코드 기반)
    try:
        if top3_symbols_code:
            _save_top3_marker(json_path, top3_symbols_code)
            logger.info(f"TOP 3 마커 저장 (코드 기반): {top3_symbols_code}")
        else:
            logger.warning("코드 기반 TOP 3가 비어있습니다.")
    except Exception as e:
        logger.warning(f"TOP 3 마커 저장 실패 (무시): {e}")

    logger.info("병렬 Notion 작성 성공!")
    return True


def main():
    parser = argparse.ArgumentParser(description="시장 분석 JSON → Notion 페이지 작성")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="JSON 탐색만 수행하고 노션 작성은 하지 않음",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="레거시 단일 Claude 모드로 실행",
    )
    parser.add_argument(
        "--dry-run-prompts",
        action="store_true",
        help="프롬프트를 파일로 저장하고 Claude 호출은 하지 않음",
    )
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Notion Writer 시작")
    logger.info("=" * 50)

    # 오늘 JSON 파일 찾기
    json_path = find_today_json()
    if json_path is None:
        logger.warning("처리할 JSON 파일이 없습니다. 종료.")
        sys.exit(2)  # 구분된 exit code: no-op

    logger.info(f"대상 JSON: {json_path}")

    if args.dry_run:
        logger.info("[DRY-RUN] 노션 작성을 건너뜁니다.")
        return

    # 이미 처리된 파일인지 확인 (dry-run 모드에서는 스킵)
    if not args.dry_run_prompts and is_already_done(json_path):
        logger.warning(f"이미 처리 완료된 파일입니다: {json_path}")
        sys.exit(2)  # 구분된 exit code: no-op (이미 완료)

    # 세션 리포트 디렉토리 찾기
    session_reports_dir = find_session_reports_dir()

    # --dry-run-prompts: 프롬프트만 파일로 저장
    if args.dry_run_prompts:
        logger.info("[DRY-RUN-PROMPTS] 프롬프트를 파일로 저장합니다.")

        with open(str(json_path), "r", encoding="utf-8") as f:
            data = json.load(f)

        market_data = {k: v for k, v in data.items() if k not in ("news", "fear_greed_index", "macro", "events", "fundamentals")}
        news_data = data.get("news", {})
        fear_greed_data = data.get("fear_greed_index", {})

        session_metrics = None
        if session_reports_dir and os.path.isdir(session_reports_dir):
            session_metrics = precompute_session_metrics(session_reports_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        has_sessions = session_metrics is not None and session_metrics.get("has_sessions", False)

        prompts_dir = PROJECT_ROOT / "data" / "debug_prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        macro_data_dry = data.get("macro")
        events_data_dry = data.get("events")
        fundamentals_data_dry = data.get("fundamentals")
        intelligence_data_dry = data.get("intelligence")

        # 전일 대비 변화 계산
        daily_changes_dry = None
        try:
            from trading_bot.market_analyzer import MarketAnalyzer
            previous_data_dry = MarketAnalyzer._load_previous_day_json(today, str(Path(str(json_path)).parent))
            if previous_data_dry:
                daily_changes_dry = MarketAnalyzer._calculate_daily_changes(data, previous_data_dry)
        except Exception as e:
            logger.warning(f"전일 변화 계산 실패 (무시): {e}")

        prompt_a = build_worker_a_prompt(
            market_data, today, macro_data=macro_data_dry,
            intelligence_data=intelligence_data_dry,
            events_data=events_data_dry, fundamentals_data=fundamentals_data_dry,
            fear_greed_data=fear_greed_data,
            daily_changes=daily_changes_dry,
        )
        previous_top3_dry = _load_previous_top3(str(Path(str(json_path)).parent), today)
        prompt_b, _ = build_worker_b_prompt(
            market_data, news_data, fear_greed_data, today,
            intelligence_data=intelligence_data_dry,
            daily_changes=daily_changes_dry,
            previous_top3=previous_top3_dry,
        )
        prompt_c = build_worker_c_prompt(
            market_data, session_metrics or {}, today, has_sessions,
            intelligence_data=intelligence_data_dry,
            daily_changes=daily_changes_dry,
        )

        for name, prompt in [("worker_a", prompt_a), ("worker_b", prompt_b), ("worker_c", prompt_c)]:
            out_path = prompts_dir / f"{name}_prompt.md"
            out_path.write_text(prompt, encoding="utf-8")
            logger.info(f"  {name}: {out_path} ({len(prompt)}자)")

        # 레거시 프롬프트도 저장
        legacy_prompt = build_analysis_prompt(str(json_path), session_reports_dir=session_reports_dir)
        legacy_path = prompts_dir / "legacy_prompt.md"
        legacy_path.write_text(legacy_prompt, encoding="utf-8")
        logger.info(f"  legacy: {legacy_path} ({len(legacy_prompt)}자)")

        logger.info("[DRY-RUN-PROMPTS] 완료. Claude 호출을 건너뜁니다.")
        return

    # --legacy: 기존 단일 Claude 모드
    if args.legacy:
        logger.info("레거시 모드로 실행")
        prompt = build_analysis_prompt(str(json_path), session_reports_dir=session_reports_dir)
        logger.info(f"프롬프트 생성 완료 (길이: {len(prompt)}자)")

        success = run_claude(prompt)
        if success:
            mark_done(json_path)
            logger.info("노션 작성 성공!")
        else:
            logger.error("노션 작성 실패. 다음 실행 시 재시도됩니다.")
            sys.exit(1)
        return

    # 기본: 병렬 모드
    success = run_parallel_notion_writer(str(json_path), session_reports_dir)
    if success:
        mark_done(json_path)
        logger.info("노션 작성 성공!")
    else:
        logger.error("노션 작성 실패. 다음 실행 시 재시도됩니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
