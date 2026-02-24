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

        logger.info(
            f"[{worker_name}] 완료 (출력 길이: {len(markdown_output)}자, "
            f"비용: ${cost_usd:.4f})" if cost_usd else
            f"[{worker_name}] 완료 (출력 길이: {len(markdown_output)}자)"
        )
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

    market_data = {k: v for k, v in data.items() if k not in ("news", "fear_greed_index")}
    news_data = data.get("news", {})
    fear_greed_data = data.get("fear_greed_index", {})

    # 2. 세션 메트릭 사전 계산
    session_metrics = None
    if session_reports_dir and os.path.isdir(session_reports_dir):
        logger.info(f"세션 메트릭 사전 계산: {session_reports_dir}")
        session_metrics = precompute_session_metrics(session_reports_dir)

    today = datetime.now().strftime("%Y-%m-%d")
    has_sessions = session_metrics is not None and session_metrics.get("has_sessions", False)

    # 3. 워커 프롬프트 빌드
    prompt_a = build_worker_a_prompt(market_data, today)
    prompt_b = build_worker_b_prompt(market_data, news_data, fear_greed_data, today)
    prompt_c = build_worker_c_prompt(
        market_data, session_metrics or {}, today, has_sessions
    )

    logger.info(
        f"프롬프트 생성 완료 - A: {len(prompt_a)}자, B: {len(prompt_b)}자, C: {len(prompt_c)}자"
    )

    # 4. 워커 설정 (이름은 WORKER_MODELS 키와 일치)
    worker_configs = {
        "Worker-A": {"prompt": prompt_a, "tools": "WebSearch", "timeout": 600, "max_budget": 0.50},
        "Worker-B": {"prompt": prompt_b, "tools": "WebSearch,Read", "timeout": 600, "max_budget": 0.50},
        "Worker-C": {"prompt": prompt_c, "tools": "", "timeout": 300, "max_budget": 0.30},
    }

    # 스태거 지연 (초)
    stagger_delays = {"Worker-A": 0, "Worker-B": 2, "Worker-C": 4}

    # 5. 병렬 실행
    results: Dict[str, Tuple[bool, str, Optional[float]]] = {}

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

    # 7. 전체 실패 → 레거시 폴백
    if success_count == 0:
        logger.error("모든 워커 실패")
        return _run_legacy_fallback(json_path, session_reports_dir)

    # 8. 부분 실패 시 플레이스홀더 삽입
    for key in ["Worker-A", "Worker-B", "Worker-C"]:
        if key not in worker_outputs:
            worker_outputs[key] = (
                '::: callout {icon="⚠️" color="red_bg"}\n'
                "\t이 섹션은 생성에 실패했습니다.\n:::"
            )

    # 9. 섹션 조합
    assembled = assemble_sections(
        worker_a_output=worker_outputs["Worker-A"],
        worker_b_output=worker_outputs["Worker-B"],
        worker_c_output=worker_outputs["Worker-C"],
        today=today,
    )

    # 10. 유효성 검증
    if has_sessions:
        expected = ["# 1.", "# 2.", "# 3.", "# 4.", "# 5.",
                     "# 6.", "# 7.", "# 8.", "# 9.", "# 10."]
    else:
        expected = ["# 1.", "# 2.", "# 3.", "# 4.", "# 5.",
                     "# 6.", "# 7.", "# 8."]

    if success_count == 3 and not validate_assembly(assembled, expected):
        logger.error("조합 결과 유효성 검증 실패 → 레거시 폴백")
        return _run_legacy_fallback(json_path, session_reports_dir)
    elif success_count < 3:
        logger.warning("일부 워커 실패 - 유효성 검증 건너뜀")

    logger.info(f"섹션 조합 완료 (총 길이: {len(assembled)}자)")

    # 11. Notion Writer Claude 실행
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

    # 12. 비용 요약 로깅
    total_cost = sum(costs.values())
    logger.info(
        f"총 비용: ${total_cost:.4f} "
        f"(A=${costs.get('Worker-A', 0):.4f}, "
        f"B=${costs.get('Worker-B', 0):.4f}, "
        f"C=${costs.get('Worker-C', 0):.4f}, "
        f"Writer=${costs.get('Notion-Writer', 0):.4f})"
    )

    if not notion_ok:
        logger.error("Notion Writer 실패 - 마커 생성하지 않음 (다음 실행 시 재시도)")
        return False

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
        logger.info("처리할 JSON 파일이 없습니다. 종료.")
        return

    logger.info(f"대상 JSON: {json_path}")

    # 이미 처리된 파일인지 확인
    if is_already_done(json_path):
        logger.info(f"이미 처리 완료된 파일입니다: {json_path}")
        return

    if args.dry_run:
        logger.info("[DRY-RUN] 노션 작성을 건너뜁니다.")
        return

    # 세션 리포트 디렉토리 찾기
    session_reports_dir = find_session_reports_dir()

    # --dry-run-prompts: 프롬프트만 파일로 저장
    if args.dry_run_prompts:
        logger.info("[DRY-RUN-PROMPTS] 프롬프트를 파일로 저장합니다.")

        with open(str(json_path), "r", encoding="utf-8") as f:
            data = json.load(f)

        market_data = {k: v for k, v in data.items() if k not in ("news", "fear_greed_index")}
        news_data = data.get("news", {})
        fear_greed_data = data.get("fear_greed_index", {})

        session_metrics = None
        if session_reports_dir and os.path.isdir(session_reports_dir):
            session_metrics = precompute_session_metrics(session_reports_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        has_sessions = session_metrics is not None and session_metrics.get("has_sessions", False)

        prompts_dir = PROJECT_ROOT / "data" / "debug_prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        prompt_a = build_worker_a_prompt(market_data, today)
        prompt_b = build_worker_b_prompt(market_data, news_data, fear_greed_data, today)
        prompt_c = build_worker_c_prompt(
            market_data, session_metrics or {}, today, has_sessions
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
