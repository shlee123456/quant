"""
Automated Trading Scheduler

Schedules paper trading sessions during US market hours:
- Market open: 23:30 KST - Start paper trading
- Market close: 06:00 KST - Stop trading and generate reports

Usage:
    python scheduler.py
    python scheduler.py --preset "스윙트레이딩 - RSI 보수적"
    python scheduler.py --presets "RSI 보수적" "MACD 추세" "RSI+MACD 복합"

Requirements:
    - .env file with KIS API credentials
    - APScheduler installed (pip install APScheduler)
"""

import sys
import signal
import logging
from logging.handlers import RotatingFileHandler
import argparse
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Load environment variables
load_dotenv()

# Setup logging (load config for scheduler log settings)
from trading_bot.config import Config as _SchedulerConfig
_sched_cfg = _SchedulerConfig()

Path('logs').mkdir(exist_ok=True)
_log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_file_handler = RotatingFileHandler(
    _sched_cfg.get('scheduler.log_file', 'logs/scheduler.log'),
    maxBytes=_sched_cfg.get('scheduler.log_max_bytes', 10 * 1024 * 1024),
    backupCount=_sched_cfg.get('scheduler.log_backup_count', 5),
    encoding='utf-8'
)
_file_handler.setFormatter(_log_formatter)
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_file_handler, _stream_handler]
)
logger = logging.getLogger(__name__)

# Import all scheduler components from the package.
# Re-export at module level so that existing `from scheduler import X` patterns
# in tests and examples continue to work.
from trading_bot.scheduler.scheduler_state import (  # noqa: E402
    STRATEGY_CLASS_MAP,
    ctx,
    active_traders,
    trader_threads,
    traders_lock,
    preset_configs,
    notifier,
    preset_manager,
    scheduler_health,
    anomaly_detector,
    global_db,
    global_regime_detector,
    global_llm_client,
)
from trading_bot.scheduler.session_manager import (  # noqa: E402
    start_paper_trading,
    stop_paper_trading,
    run_market_analysis,
    _start_single_session,
    _stop_single_session,
    _is_trading_day,
)
from trading_bot.scheduler.db_maintenance import db_maintenance as _db_maintenance  # noqa: E402
from trading_bot.scheduler.scheduler_core import (  # noqa: E402
    signal_handler,
    heartbeat as _heartbeat,
    watchdog as _watchdog,
    _handle_status,
    _handle_stop,
    _handle_stop_all,
    _handle_cleanup,
    _validate_environment,
)


def main():
    """
    메인 스케줄러 진입점
    """
    import trading_bot.scheduler.scheduler_state as state

    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.executors.pool import ThreadPoolExecutor

    # CLI 인자 파싱
    parser = argparse.ArgumentParser(description='자동매매 트레이딩 스케줄러')
    parser.add_argument('--preset', type=str, default=None,
                        help='사용할 프리셋 이름 (예: "스윙트레이딩 - RSI 보수적")')
    parser.add_argument('--presets', type=str, nargs='+', default=None,
                        help='동시 실행할 프리셋 이름 목록 (예: "RSI 보수적" "MACD 추세")')
    parser.add_argument('--list-presets', action='store_true',
                        help='저장된 프리셋 목록 표시')
    # 관리 CLI 옵션
    parser.add_argument('--status', action='store_true',
                        help='스케줄러 상태 및 활성 세션 조회')
    parser.add_argument('--stop', type=str, default=None,
                        help='특정 세션 중지 명령 전송 (라벨)')
    parser.add_argument('--stop-all', action='store_true',
                        help='전체 세션 중지 명령 전송')
    parser.add_argument('--cleanup', action='store_true',
                        help='좀비 세션 즉시 정리')
    parser.add_argument('--max-sessions', type=int, default=0,
                        help='최대 동시 세션 수 (0=무제한)')
    args = parser.parse_args()

    # === 관리 CLI 모드 (즉시 실행 후 종료) ===
    if args.status:
        _handle_status()
        return

    if args.stop:
        _handle_stop(args.stop)
        return

    if args.stop_all:
        _handle_stop_all()
        return

    if args.cleanup:
        _handle_cleanup()
        return

    # 프리셋 목록 표시
    if args.list_presets:
        presets = preset_manager.list_presets()
        if presets:
            print("저장된 프리셋 목록:")
            for p in presets:
                print(f"  - {p['name']} ({p['strategy']})")
        else:
            print("저장된 프리셋이 없습니다.")
        return

    # --preset과 --presets 동시 사용 방지
    if args.preset and args.presets:
        logger.error("✗ --preset과 --presets는 동시에 사용할 수 없습니다")
        return

    # 최대 세션 수 설정
    state.ctx.max_sessions = args.max_sessions

    # 프리셋 이름 목록 통합 (--preset -> 1개짜리 리스트로 변환)
    preset_names: List[str] = []
    if args.presets:
        preset_names = args.presets
    elif args.preset:
        preset_names = [args.preset]
    else:
        # 프리셋 미지정 시 저장된 전체 프리셋 자동 로드
        all_presets = preset_manager.list_presets()
        if all_presets:
            preset_names = [p['name'] for p in all_presets]
            logger.info(f"프리셋 미지정 → 저장된 전체 {len(preset_names)}개 프리셋 자동 로드")

    # 프리셋 로드 및 검증
    if preset_names:
        # 먼저 모든 프리셋 존재 여부 검증
        missing = []
        for name in preset_names:
            loaded = preset_manager.load_preset(name)
            if not loaded:
                missing.append(name)

        if missing:
            logger.error(f"✗ 다음 프리셋을 찾을 수 없습니다: {', '.join(missing)}")
            logger.info("사용 가능한 프리셋: --list-presets 옵션으로 확인하세요")
            return

        # 검증 통과 후 로드
        for name in preset_names:
            loaded = preset_manager.load_preset(name)
            loaded['_preset_name'] = name
            state.preset_configs.append(loaded)
            logger.info(f"✓ 프리셋 '{name}' 로드 완료")
            logger.info(f"  전략: {loaded['strategy']}")
            logger.info(f"  종목: {', '.join(loaded.get('symbols', []))}")
            logger.info(f"  파라미터: {loaded.get('strategy_params', {})}")

    # logs 디렉토리가 없으면 생성
    Path('logs').mkdir(exist_ok=True)

    # === 환경 변수 검증 ===
    _validate_environment()

    # === Phase 1: 시작 시 좀비 세션 복구 ===
    state.scheduler_health.update('starting')
    recovered_count = state.global_db.recover_zombie_sessions()
    if recovered_count > 0:
        logger.info(f"✓ 좀비 세션 {recovered_count}개 복구 완료")
        state.notifier.send_slack(
            f"*스케줄러 시작 - 좀비 세션 복구*\n\n"
            f"복구된 세션: {recovered_count}개",
            color='warning'
        )

    # 우아한 종료를 위한 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 스케줄러 생성 (ThreadPoolExecutor로 블로킹 방지)
    executors = {
        'default': ThreadPoolExecutor(max_workers=4)
    }
    scheduler = BlockingScheduler(timezone='Asia/Seoul', executors=executors)

    logger.info("=" * 60)
    logger.info("자동매매 트레이딩 스케줄러")
    logger.info("=" * 60)
    if state.preset_configs:
        logger.info(f"프리셋 ({len(state.preset_configs)}개):")
        for cfg in state.preset_configs:
            logger.info(f"  - {cfg['_preset_name']} ({cfg['strategy']})")
    else:
        logger.info("프리셋: 없음 (기본 설정 1개 세션)")
    if state.ctx.max_sessions > 0:
        logger.info(f"최대 세션 수: {state.ctx.max_sessions}")
    logger.info("시간대: Asia/Seoul")
    logger.info("스케줄:")
    logger.info("  23:30 KST - 페이퍼 트레이딩 시작")
    logger.info("  06:00 KST - 트레이딩 중지 및 리포트")
    logger.info("  06:10 KST - 시장 분석 + 노션 작성")
    logger.info("  매 60초 - 하트비트 + 제어 명령 폴링")
    logger.info("  매 2분 - 워치독 (스레드 감시)")
    logger.info("  매일 06:05 - DB 유지보수 (다운샘플링+정리)")
    logger.info("=" * 60)

    # 스케줄 작업 추가

    # 장 시작: 트레이딩 시작 (23:30 KST) - 공휴일/주말 건너뜀
    def _scheduled_start():
        if not _is_trading_day():
            return
        start_paper_trading()

    scheduler.add_job(
        _scheduled_start,
        CronTrigger(hour=23, minute=30),
        id='start_trading',
        name='페이퍼 트레이딩 시작',
        misfire_grace_time=300
    )

    # 장 마감: 트레이딩 중지 (06:00 KST)
    scheduler.add_job(
        stop_paper_trading,
        CronTrigger(hour=6, minute=0),
        id='stop_trading',
        name='페이퍼 트레이딩 중지',
        misfire_grace_time=300
    )

    # 장 마감 후: 시장 분석 + 노션 작성 (06:10 KST)
    scheduler.add_job(
        run_market_analysis,
        CronTrigger(hour=6, minute=10),
        id='market_analysis',
        name='시장 분석 + 노션 작성',
        misfire_grace_time=600
    )

    # 하트비트 (60초 간격)
    scheduler.add_job(
        _heartbeat,
        IntervalTrigger(seconds=60),
        id='heartbeat',
        name='하트비트',
        misfire_grace_time=30,
        coalesce=True
    )

    # 워치독 (2분 간격)
    scheduler.add_job(
        _watchdog,
        IntervalTrigger(seconds=120),
        id='watchdog',
        name='워치독',
        misfire_grace_time=60,
        coalesce=True
    )

    # 일간 DB 유지보수 (매일 06:05 KST, 장 마감 직후)
    scheduler.add_job(
        _db_maintenance,
        CronTrigger(hour=6, minute=5),
        id='db_maintenance',
        name='DB 유지보수',
        misfire_grace_time=3600
    )

    # 시작 완료 -> idle 상태 + Slack 알림
    state.scheduler_health.update('idle', {
        'preset_count': len(state.preset_configs),
        'recovered_sessions': recovered_count,
    })

    state.notifier.send_slack(
        f"*스케줄러 시작 완료*\n\n"
        f"PID: {os.getpid()}\n"
        f"프리셋: {len(state.preset_configs)}개\n"
        f"복구 세션: {recovered_count}개\n"
        f"최대 세션: {'무제한' if state.ctx.max_sessions == 0 else state.ctx.max_sessions}",
        color='good'
    )

    logger.info("\n✓ 스케줄러 시작 성공")
    logger.info("중지하려면 Ctrl+C를 누르세요\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        signal_handler(None, None)


if __name__ == '__main__':
    main()
