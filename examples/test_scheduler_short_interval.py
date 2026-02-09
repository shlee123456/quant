"""
Scheduler Test - Short Interval

실제 스케줄(7시간) 대신 짧은 간격(3분)으로 전체 프로세스 테스트:
- 즉시: 전략 최적화
- 30초 후: Paper Trading 시작
- 2분 후: Paper Trading 종료 + 리포트 생성

Usage:
    python examples/test_scheduler_short_interval.py
"""

import sys
import signal
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy
from trading_bot.database import TradingDatabase
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.notifications import NotificationService
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.reports import ReportGenerator
from dashboard.kis_broker import get_kis_broker

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/test_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global trader instance
current_trader: Optional[PaperTrader] = None

# Global notification service
notifier = NotificationService()

# Global preset manager
preset_manager = StrategyPresetManager()

# Optimized parameters
optimized_params = None


def optimize_strategy():
    """
    TEST 1: 전략 최적화 (즉시 실행)
    """
    global optimized_params

    logger.info("=" * 60)
    logger.info("🔍 TEST 1: 전략 최적화 시작")
    logger.info("=" * 60)

    try:
        # 최적화용 샘플 데이터 생성
        data_gen = SimulationDataGenerator(seed=42)
        df = data_gen.generate_trend_data(periods=500, trend='bullish')

        # RSI 전략 파라미터 그리드 (테스트용 축소)
        param_grid = {
            'period': [10, 14],
            'overbought': [70, 75],
            'oversold': [25, 30]
        }

        # 최적화 실행
        optimizer = StrategyOptimizer(initial_capital=10000.0)
        logger.info("그리드 서치 최적화 실행 중...")
        results_df = optimizer.optimize(RSIStrategy, df, param_grid)

        # 샤프 비율 기준 최적 결과 찾기
        best_idx = results_df['sharpe_ratio'].idxmax()
        best_result = results_df.loc[best_idx].to_dict()

        logger.info(f"✓ 최적화 완료!")
        logger.info(f"  최적 파라미터: {best_result['params']}")
        logger.info(f"  샤프 비율: {best_result['sharpe_ratio']:.2f}")
        logger.info(f"  총 수익률: {best_result['total_return']:.2f}%")

        # 알림 전송
        notifier.send_slack(
            f"🔍 *[테스트] 전략 최적화 완료*\n\n"
            f"최적 파라미터: {best_result['params']}\n"
            f"샤프 비율: {best_result['sharpe_ratio']:.2f}\n"
            f"총 수익률: {best_result['total_return']:.2f}%",
            color='good'
        )

        # 최적 파라미터 저장
        optimized_params = best_result['params']

        # 프리셋으로 저장
        preset_name = f"테스트_자동최적화_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        preset_manager.save_preset(
            name=preset_name,
            description=f"테스트 최적화 결과 (Sharpe: {best_result['sharpe_ratio']:.2f})",
            strategy="RSI Strategy",
            strategy_params=best_result['params'],
            symbols=['AAPL', 'MSFT'],
            initial_capital=10000.0,
            position_size=0.3,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            enable_stop_loss=True,
            enable_take_profit=True
        )

        logger.info(f"✓ 최적 파라미터 프리셋 저장: {preset_name}")
        logger.info("✅ TEST 1 완료\n")

    except Exception as e:
        logger.error(f"✗ 최적화 실패: {e}", exc_info=True)
        notifier.notify_error(f"[테스트] 전략 최적화 실패: {e}", context="TEST 1")


def start_paper_trading():
    """
    TEST 2: Paper Trading 시작 (30초 후 실행)

    주의: 실제 KIS API 호출을 수행하므로 rate limit에 주의
    """
    global current_trader

    logger.info("=" * 60)
    logger.info("📈 TEST 2: Paper Trading 시작")
    logger.info("=" * 60)

    try:
        # 브로커 초기화
        broker = get_kis_broker()
        if not broker:
            logger.error("✗ KIS 브로커 초기화 실패")
            return

        # 데이터베이스 초기화
        db = TradingDatabase()

        # 전략 생성 (최적화된 파라미터 사용)
        if optimized_params:
            logger.info(f"최적화된 파라미터 사용: {optimized_params}")
            strategy = RSIStrategy(**optimized_params)
        else:
            logger.info("기본 파라미터 사용 (최적화 안 됨)")
            strategy = RSIStrategy(period=14, overbought=70, oversold=30)

        logger.info(f"전략: {strategy.name}")

        # 거래할 종목 (테스트용 2종목만)
        symbols = ['AAPL', 'MSFT']
        logger.info(f"종목: {', '.join(symbols)}")

        # 페이퍼 트레이더 생성
        current_trader = PaperTrader(
            strategy=strategy,
            symbols=symbols,
            broker=broker,
            initial_capital=10000.0,
            position_size=0.3,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            enable_stop_loss=True,
            enable_take_profit=True,
            db=db
        )

        # Attach notifier
        current_trader.notifier = notifier

        logger.info("✓ 페이퍼 트레이더 초기화 완료")
        logger.info(f"  초기 자본: ${current_trader.initial_capital:,.2f}")
        logger.info(f"  포지션 크기: {current_trader.position_size:.0%}")

        # 세션 시작 알림
        notifier.notify_session_start({
            'strategy_name': strategy.name,
            'symbols': symbols,
            'initial_capital': current_trader.initial_capital
        })

        # 세션 시작
        current_trader.start()
        logger.info("✓ 세션 시작됨")

        # 테스트용: 3번만 iteration 실행 (60초 간격)
        logger.info("📊 실시간 트레이딩 시작 (3회 iteration, 60초 간격)")

        for i in range(3):
            logger.info(f"\n--- Iteration {i+1}/3 ---")
            current_trader._realtime_iteration(timeframe='1d')

            if i < 2:  # 마지막 iteration 후에는 sleep 안 함
                import time
                logger.info("60초 대기 중...")
                time.sleep(60)

        logger.info("✅ TEST 2 완료 (3회 iteration 완료)\n")

    except Exception as e:
        logger.error(f"✗ Paper Trading 실패: {e}", exc_info=True)
        notifier.notify_error(f"[테스트] Paper Trading 실패: {e}", context="TEST 2")
        current_trader = None


def stop_paper_trading():
    """
    TEST 3: Paper Trading 종료 및 리포트 생성 (2분 후 실행)
    """
    global current_trader

    logger.info("=" * 60)
    logger.info("📊 TEST 3: Paper Trading 종료 및 리포트 생성")
    logger.info("=" * 60)

    if current_trader is None:
        logger.warning("⚠ 중지할 활성 트레이딩 세션 없음")
        return

    try:
        # 트레이더 중지
        current_trader.stop()

        # 세션 요약 조회
        if current_trader.session_id and current_trader.db:
            summary = current_trader.db.get_session_summary(current_trader.session_id)

            if summary:
                logger.info("✓ 세션 중지 성공")
                logger.info(f"  세션 ID: {current_trader.session_id}")
                logger.info(f"  최종 자본: ${summary.get('final_capital', 0):,.2f}")

                # Handle None values for metrics
                total_return = summary.get('total_return') or 0.0
                sharpe_ratio = summary.get('sharpe_ratio') or 0.0
                max_drawdown = summary.get('max_drawdown') or 0.0
                win_rate = summary.get('win_rate') or 0.0

                logger.info(f"  총 수익률: {total_return:.2f}%")
                logger.info(f"  샤프 비율: {sharpe_ratio:.2f}")
                logger.info(f"  최대 낙폭: {max_drawdown:.2f}%")
                logger.info(f"  승률: {win_rate:.2f}%")

                # 거래 횟수 조회
                trades = current_trader.db.get_session_trades(current_trader.session_id)
                logger.info(f"  총 거래: {len(trades)}회")

                # 세션 종료 알림 전송
                notifier.notify_session_end({
                    'strategy_name': summary.get('strategy_name', 'Unknown'),
                    'total_return': total_return,
                    'sharpe_ratio': sharpe_ratio,
                    'max_drawdown': max_drawdown,
                    'win_rate': win_rate,
                    'num_trades': len(trades)
                })

                # CSV 리포트 생성
                try:
                    report_gen = ReportGenerator(current_trader.db)
                    report_files = report_gen.generate_session_report(
                        current_trader.session_id,
                        output_dir='reports/test/',
                        formats=['csv', 'json']
                    )

                    logger.info("✓ 리포트 생성 완료:")
                    for format_name, file_path in report_files.items():
                        logger.info(f"  {format_name.upper()}: {file_path}")

                    # 리포트 파일 경로를 Slack으로 전송
                    report_msg = "📄 *[테스트] 리포트 생성 완료*\n\n"
                    for format_name, file_path in report_files.items():
                        report_msg += f"{format_name.upper()}: {file_path}\n"

                    notifier.send_slack(report_msg, color='good')

                except Exception as e:
                    logger.error(f"✗ 리포트 생성 실패: {e}", exc_info=True)

        logger.info("✅ TEST 3 완료\n")
        current_trader = None

    except Exception as e:
        logger.error(f"✗ 트레이딩 세션 중지 실패: {e}", exc_info=True)
        notifier.notify_error(f"[테스트] 트레이딩 세션 중지 실패: {e}", context="TEST 3")


def signal_handler(signum, frame):
    """종료 신호 처리"""
    logger.info("\n\n⚠ 종료 신호 수신")
    if current_trader:
        logger.info("활성 트레이딩 세션 중지 중...")
        stop_paper_trading()
    logger.info("테스트 스케줄러 중지됨")
    sys.exit(0)


def main():
    """
    테스트 스케줄러 진입점

    스케줄:
    - 즉시: 전략 최적화
    - 30초 후: Paper Trading 시작 (3회 iteration)
    - 3분 30초 후: Paper Trading 종료 + 리포트
    """
    # logs 디렉토리 생성
    Path('logs').mkdir(exist_ok=True)
    Path('reports/test').mkdir(parents=True, exist_ok=True)

    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 스케줄러 생성
    scheduler = BlockingScheduler(timezone='Asia/Seoul')

    logger.info("=" * 60)
    logger.info("테스트 스케줄러 (단축 간격)")
    logger.info("=" * 60)
    logger.info("시간대: Asia/Seoul")
    logger.info("테스트 스케줄:")
    logger.info("  즉시 - 전략 최적화")
    logger.info("  30초 후 - Paper Trading 시작 (3회 iteration)")
    logger.info("  3분 30초 후 - Trading 종료 + 리포트")
    logger.info("=" * 60)
    logger.info("")

    now = datetime.now()

    # TEST 1: 즉시 실행
    scheduler.add_job(
        optimize_strategy,
        DateTrigger(run_date=now + timedelta(seconds=1)),
        id='test_optimize',
        name='[TEST 1] 전략 최적화'
    )

    # TEST 2: 30초 후 실행
    scheduler.add_job(
        start_paper_trading,
        DateTrigger(run_date=now + timedelta(seconds=30)),
        id='test_start_trading',
        name='[TEST 2] Paper Trading 시작'
    )

    # TEST 3: 3분 30초 후 실행 (30초 시작 + 3분 실행)
    scheduler.add_job(
        stop_paper_trading,
        DateTrigger(run_date=now + timedelta(seconds=210)),
        id='test_stop_trading',
        name='[TEST 3] Paper Trading 종료'
    )

    # 스케줄러 시작
    logger.info("✓ 테스트 스케줄러 시작")
    logger.info("중지하려면 Ctrl+C를 누르세요\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        signal_handler(None, None)


if __name__ == '__main__':
    main()
