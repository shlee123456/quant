#!/usr/bin/env python3
"""
KR Notion Writer - 한국 시장 분석 노션 작성 스크립트

한국 시장 분석 JSON (*_kr.json)을 읽어
Claude CLI로 Notion 페이지를 작성합니다.

Usage:
    python scripts/kr_notion_writer.py
    python scripts/kr_notion_writer.py --dry-run
    python scripts/kr_notion_writer.py --dry-run-prompts
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
from typing import Tuple, Optional, Dict, List

import pytz

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from trading_bot.kr_parallel_prompt_builder import (
    KR_WORKER_MODELS,
    build_kr_worker_a_prompt,
    build_kr_worker_b_prompt,
    build_kr_worker_c_prompt,
    build_kr_notion_writer_prompt,
    assemble_kr_sections,
    validate_kr_assembly,
    _get_kr_notion_page_id,
)
from trading_bot.kr_market_analyzer import KRMarketAnalyzer
from trading_bot.notion_api_writer import NotionPageWriter

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MARKET_ANALYSIS_DIR = PROJECT_ROOT / "data" / "market_analysis"
MARKER_SUFFIX = ".notion_done"


def find_today_kr_json() -> Optional[Path]:
    """오늘 날짜의 한국 시장 분석 JSON 파일을 찾습니다."""
    kst = pytz.timezone("Asia/Seoul")
    today = datetime.now(kst).strftime("%Y-%m-%d")

    if not MARKET_ANALYSIS_DIR.is_dir():
        logger.warning(f"시장 분석 디렉토리 없음: {MARKET_ANALYSIS_DIR}")
        return None

    # {YYYY-MM-DD}_kr.json 패턴
    candidates = sorted(MARKET_ANALYSIS_DIR.glob(f"{today}*_kr.json"))
    if not candidates:
        logger.info(f"오늘({today}) 한국 분석 JSON 파일 없음")
        return None

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
        worker_name: 워커 식별 이름
        prompt: Claude에 전달할 프롬프트
        tools: 허용할 도구
        timeout: 서브프로세스 타임아웃 (초)
        max_budget: 최대 비용 한도 (USD)

    Returns:
        (success, markdown_output, cost_usd) 튜플
    """
    logger.info(f"[{worker_name}] Claude 워커 시작 (timeout={timeout}s, budget=${max_budget:.2f})")

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    model = KR_WORKER_MODELS.get(worker_name, "claude-sonnet-4-6")

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

        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.error(f"[{worker_name}] JSON 파싱 실패. stdout 길이: {len(proc.stdout)}")
            return (False, "", None)

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

        if not markdown_output.strip():
            logger.warning(f"[{worker_name}] 출력이 비어있음")
            return (False, "", cost_usd)

        return (True, markdown_output, cost_usd)

    except subprocess.TimeoutExpired:
        logger.error(f"[{worker_name}] 타임아웃 ({timeout}초 초과)")
        return (False, "", None)
    except FileNotFoundError:
        logger.error(f"[{worker_name}] Claude CLI를 찾을 수 없습니다.")
        return (False, "", None)


def _run_with_delay(fn, delay: float, *args, **kwargs):
    """지연 후 함수를 실행하는 헬퍼."""
    if delay > 0:
        time.sleep(delay)
    return fn(*args, **kwargs)


def _notify_worker_failure(worker_name: str, detail: str) -> None:
    """워커 실패 시 Slack 알림을 전송합니다."""
    try:
        from trading_bot.notifications import NotificationService
        notifier = NotificationService()
        notifier.notify_error(
            f"KR Notion Writer {worker_name} 실패",
            context=detail,
        )
    except Exception as e:
        logger.warning(f"Slack 알림 전송 실패 (무시): {e}")


def run_parallel_kr_notion_writer(json_path: str) -> bool:
    """
    병렬 Claude CLI 실행으로 한국 시장 Notion 페이지를 작성합니다.

    Args:
        json_path: 한국 시장 분석 JSON 파일 경로

    Returns:
        성공 여부
    """
    logger.info("=" * 40)
    logger.info("한국 시장 병렬 모드 시작")
    logger.info("=" * 40)

    # 1. JSON 데이터 로드
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    market_data = {k: v for k, v in data.items() if k not in ("news", "macro", "events", "intelligence")}
    news_data = data.get("news", {})
    macro_data = data.get("macro")
    events_data = data.get("events")
    intelligence_data = data.get("intelligence")

    today = datetime.now().strftime("%Y-%m-%d")

    # 2. 전일 대비 변화 계산
    daily_changes: Optional[Dict] = None
    try:
        previous_data = KRMarketAnalyzer._load_previous_day_json(
            today, str(Path(json_path).parent)
        )
        if previous_data:
            daily_changes = KRMarketAnalyzer._calculate_daily_changes(data, previous_data)
            logger.info(f"전일 변화 계산 완료 (이전 날짜: {daily_changes.get('previous_date', 'N/A')})")
    except Exception as e:
        logger.warning(f"전일 변화 계산 실패 (무시): {e}")

    # 3. 워커 프롬프트 빌드
    prompt_a = build_kr_worker_a_prompt(
        market_data, today,
        macro_data=macro_data,
        intelligence_data=intelligence_data,
        events_data=events_data,
        daily_changes=daily_changes,
    )
    prompt_c = build_kr_worker_c_prompt(
        market_data, today,
        intelligence_data=intelligence_data,
        daily_changes=daily_changes,
    )

    # 4. A + C 병렬 실행
    results: Dict[str, Tuple[bool, str, Optional[float]]] = {}

    logger.info("Phase 1: Worker-A + Worker-C 병렬 실행")
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(
            run_claude_worker, "Worker-A", prompt_a, "WebSearch", 600, 2.00
        )
        future_c = executor.submit(
            run_claude_worker, "Worker-C", prompt_c, "", 300, 0.30
        )

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

    # 5. B with A's context (직렬)
    worker_a_output = results["Worker-A"][1] if results["Worker-A"][0] else ""
    worker_a_context = worker_a_output[:3000] if worker_a_output else None

    prompt_b, top3_symbols = build_kr_worker_b_prompt(
        market_data, news_data, today,
        intelligence_data=intelligence_data,
        worker_a_context=worker_a_context,
        daily_changes=daily_changes,
    )
    logger.info(
        f"프롬프트 생성 완료 - A: {len(prompt_a)}자, B: {len(prompt_b)}자, C: {len(prompt_c)}자"
    )

    try:
        results["Worker-B"] = run_claude_worker(
            "Worker-B", prompt_b, "WebSearch,Read", 600, 3.00
        )
    except Exception as e:
        logger.error(f"[Worker-B] 예외 발생: {e}")
        results["Worker-B"] = (False, "", None)

    # 6. 결과 수집
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

    # 7. 핵심 워커 실패 시 재시도
    if success_count == 0:
        logger.error("모든 워커 실패")
        _notify_worker_failure("전체 워커", "모든 워커(A/B/C)가 실패했습니다.")
        return False

    all_worker_cfgs = {
        "Worker-A": {"prompt": prompt_a, "tools": "WebSearch", "timeout": 600, "max_budget": 2.00},
        "Worker-B": {"prompt": prompt_b, "tools": "WebSearch,Read", "timeout": 600, "max_budget": 3.00},
        "Worker-C": {"prompt": prompt_c, "tools": "", "timeout": 300, "max_budget": 0.30},
    }

    failed_core = [k for k in ["Worker-A", "Worker-B"] if k not in worker_outputs]
    if failed_core:
        logger.warning(f"핵심 워커 실패 {failed_core} -> 재시도 (예산 2배)")
        for name in failed_core:
            cfg = all_worker_cfgs[name]
            retry_budget = cfg["max_budget"] * 2.0
            ok, output, cost = run_claude_worker(
                name, cfg["prompt"], cfg["tools"], cfg["timeout"], retry_budget
            )
            costs[name] = costs.get(name, 0) + (cost or 0.0)
            if ok and output:
                worker_outputs[name] = output
                success_count += 1

        still_failed = [k for k in ["Worker-A", "Worker-B"] if k not in worker_outputs]
        if still_failed:
            logger.error(f"핵심 워커 재시도 실패 {still_failed}")
            return False

    if "Worker-C" not in worker_outputs:
        logger.warning("[Worker-C] 실패 -> 재시도")
        cfg_c = all_worker_cfgs["Worker-C"]
        ok, output, cost = run_claude_worker(
            "Worker-C", cfg_c["prompt"], cfg_c["tools"], 600, 0.60
        )
        costs["Worker-C"] = costs.get("Worker-C", 0) + (cost or 0.0)
        if ok and output:
            worker_outputs["Worker-C"] = output
        else:
            logger.error("[Worker-C] 재시도 실패")
            return False

    # 8. 섹션 조합
    assembled = assemble_kr_sections(
        worker_a_output=worker_outputs["Worker-A"],
        worker_b_output=worker_outputs["Worker-B"],
        worker_c_output=worker_outputs["Worker-C"],
        today=today,
    )

    # 9. 유효성 검증
    expected: List[str] = ["# 1.", "# 2.", "# 3.", "# 4.", "# 5.", "# 6.", "# 7.", "# 8."]
    if macro_data:
        expected = ["# 0."] + expected

    if not validate_kr_assembly(assembled, expected):
        logger.error("조합 결과 유효성 검증 실패")
        return False

    logger.info(f"섹션 조합 완료 (총 길이: {len(assembled)}자)")

    # 10. Notion API로 직접 페이지 생성 (Claude CLI MCP 의존성 제거)
    logger.info("[Notion-API] Python notion-client로 페이지 생성 시작")
    parent_page_id = _get_kr_notion_page_id()

    from datetime import datetime as dt
    month_name = dt.strptime(today, "%Y-%m-%d").strftime("%y-%m월")

    try:
        writer = NotionPageWriter(parent_page_id=parent_page_id)
        page_url = writer.create_report(
            title=f"📊 한국 시장 분석 | {today}",
            content=assembled,
            month_name=month_name,
        )
    except Exception as e:
        logger.error(f"[Notion-API] 페이지 생성 실패: {e}")
        return False

    if not page_url:
        logger.error("[Notion-API] 페이지 URL 없음 — 생성 실패")
        return False

    logger.info(f"[Notion-API] 페이지 생성 완료: {page_url}")

    # 11. 비용 요약
    total_cost = sum(costs.values())
    logger.info(
        f"총 비용: ${total_cost:.4f} "
        f"(A=${costs.get('Worker-A', 0):.4f}, "
        f"B=${costs.get('Worker-B', 0):.4f}, "
        f"C=${costs.get('Worker-C', 0):.4f}, "
        f"Notion-API=$0.0000)"
    )

    logger.info("한국 시장 병렬 Notion 작성 성공!")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="한국 시장 분석 JSON -> Notion 페이지 작성")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="JSON 탐색만 수행하고 노션 작성은 하지 않음",
    )
    parser.add_argument(
        "--dry-run-prompts",
        action="store_true",
        help="프롬프트를 파일로 저장하고 Claude 호출은 하지 않음",
    )
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("KR Notion Writer 시작")
    logger.info("=" * 50)

    # 오늘 JSON 파일 찾기
    json_path = find_today_kr_json()
    if json_path is None:
        logger.warning("처리할 한국 분석 JSON 파일이 없습니다. 종료.")
        sys.exit(2)

    logger.info(f"대상 JSON: {json_path}")

    if args.dry_run:
        logger.info("[DRY-RUN] 노션 작성을 건너뜁니다.")
        return

    if not args.dry_run_prompts and is_already_done(json_path):
        logger.warning(f"이미 처리 완료된 파일입니다: {json_path}")
        sys.exit(2)

    # --dry-run-prompts: 프롬프트만 파일로 저장
    if args.dry_run_prompts:
        logger.info("[DRY-RUN-PROMPTS] 프롬프트를 파일로 저장합니다.")

        with open(str(json_path), "r", encoding="utf-8") as f:
            data = json.load(f)

        market_data = {k: v for k, v in data.items() if k not in ("news", "macro", "events", "intelligence")}
        news_data = data.get("news", {})
        macro_data = data.get("macro")
        events_data = data.get("events")
        intelligence_data = data.get("intelligence")
        today = datetime.now().strftime("%Y-%m-%d")

        prompts_dir = PROJECT_ROOT / "data" / "debug_prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        prompt_a = build_kr_worker_a_prompt(
            market_data, today,
            macro_data=macro_data,
            intelligence_data=intelligence_data,
            events_data=events_data,
        )
        prompt_b, _ = build_kr_worker_b_prompt(
            market_data, news_data, today,
            intelligence_data=intelligence_data,
        )
        prompt_c = build_kr_worker_c_prompt(
            market_data, today,
            intelligence_data=intelligence_data,
        )

        for name, prompt in [("kr_worker_a", prompt_a), ("kr_worker_b", prompt_b), ("kr_worker_c", prompt_c)]:
            out_path = prompts_dir / f"{name}_prompt.md"
            out_path.write_text(prompt, encoding="utf-8")
            logger.info(f"  {name}: {out_path} ({len(prompt)}자)")

        logger.info("[DRY-RUN-PROMPTS] 완료.")
        return

    # 기본: 병렬 모드
    success = run_parallel_kr_notion_writer(str(json_path))
    if success:
        mark_done(json_path)
        logger.info("한국 시장 노션 작성 성공!")
    else:
        logger.error("한국 시장 노션 작성 실패. 다음 실행 시 재시도됩니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
