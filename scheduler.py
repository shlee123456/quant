"""
Automated Trading Scheduler

Schedules paper trading sessions during US market hours:
- Pre-market: 23:00 KST - Strategy optimization
- Market open: 23:30 KST - Start paper trading
- Market close: 06:00 KST - Stop trading and generate reports

Usage:
    python scheduler.py

Requirements:
    - .env file with KIS API credentials
    - APScheduler installed (pip install APScheduler)
"""

import sys
import signal
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy
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
        logging.FileHandler('logs/scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global trader instance (managed across scheduled jobs)
current_trader: Optional[PaperTrader] = None

# Global notification service
notifier = NotificationService()

# Global preset manager
preset_manager = StrategyPresetManager()

# Optimized parameters (loaded from optimization)
optimized_params = None


def optimize_strategy():
    """
    장전 작업: 전략 파라미터 최적화
    장 시작 30분 전 실행
    """
    global optimized_params

    logger.info("=" * 60)
    logger.info("전략 최적화 시작...")
    logger.info("=" * 60)

    try:
        # 최적화용 샘플 데이터 생성
        data_gen = SimulationDataGenerator(seed=42)
        df = data_gen.generate_trend_data(periods=500, trend='bullish')

        # RSI 전략 파라미터 그리드 정의
        param_grid = {
            'period': [10, 14, 20],
            'overbought': [70, 75, 80],
            'oversold': [20, 25, 30]
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
            f"📊 *전략 최적화 완료*\n\n"
            f"최적 파라미터: {best_result['params']}\n"
            f"샤프 비율: {best_result['sharpe_ratio']:.2f}\n"
            f"총 수익률: {best_result['total_return']:.2f}%",
            color='good'
        )

        # 최적 파라미터를 전역 변수에 저장 (다음 트레이딩 세션에서 사용)
        optimized_params = best_result['params']

        # 프리셋으로 저장 (영속성)
        preset_name = f"자동최적화_{datetime.now().strftime('%Y%m%d_%H%M')}"
        preset_manager.save_preset(
            name=preset_name,
            description=f"자동 최적화 결과 (Sharpe: {best_result['sharpe_ratio']:.2f})",
            strategy="RSI Strategy",
            strategy_params=best_result['params'],
            symbols=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
            initial_capital=10000.0,
            position_size=0.3,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            enable_stop_loss=True,
            enable_take_profit=True
        )

        logger.info(f"✓ 최적 파라미터 프리셋 저장: {preset_name}")

    except Exception as e:
        logger.error(f"✗ 최적화 실패: {e}", exc_info=True)
        notifier.notify_error(f"전략 최적화 실패: {e}", context="장전 작업")


def start_paper_trading():
    """
    장 시작 작업: 페이퍼 트레이딩 세션 시작
    장 시작 시각 (23:30 KST) 실행
    """
    global current_trader

    logger.info("=" * 60)
    logger.info("페이퍼 트레이딩 세션 시작...")
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

        # 거래할 종목 선택
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']
        logger.info(f"종목: {', '.join(symbols)}")

        # 페이퍼 트레이더 생성
        current_trader = PaperTrader(
            strategy=strategy,
            symbols=symbols,
            broker=broker,
            initial_capital=10000.0,
            position_size=0.3,  # 거래당 30%
            stop_loss_pct=0.05,  # 5% 손절
            take_profit_pct=0.10,  # 10% 익절
            enable_stop_loss=True,
            enable_take_profit=True,
            db=db
        )

        # Attach notifier to trader for stop loss/take profit notifications
        current_trader.notifier = notifier

        logger.info("✓ 페이퍼 트레이더 초기화 완료")
        logger.info(f"  초기 자본: ${current_trader.initial_capital:,.2f}")
        logger.info(f"  포지션 크기: {current_trader.position_size:.0%}")
        logger.info(f"  손절매: {current_trader.stop_loss_pct:.0%} ({'활성' if current_trader.enable_stop_loss else '비활성'})")
        logger.info(f"  익절매: {current_trader.take_profit_pct:.0%} ({'활성' if current_trader.enable_take_profit else '비활성'})")

        # 세션 시작 알림 전송
        notifier.notify_session_start({
            'strategy_name': strategy.name,
            'symbols': symbols,
            'initial_capital': current_trader.initial_capital
        })

        # 실시간 트레이딩 시작 (현재 스레드에서 실행)
        # stop_paper_trading()이 호출될 때까지 블로킹됨
        logger.info("실시간 트레이딩 루프 시작 (60초 간격)...")
        current_trader.run_realtime(interval_seconds=60, timeframe='1d')

    except Exception as e:
        logger.error(f"✗ 페이퍼 트레이딩 실패: {e}", exc_info=True)
        notifier.notify_error(f"페이퍼 트레이딩 실패: {e}", context="트레이딩 세션")
        current_trader = None


def stop_paper_trading():
    """
    장 마감 작업: 페이퍼 트레이딩 중지 및 리포트 생성
    장 마감 시각 (06:00 KST) 실행
    """
    global current_trader

    logger.info("=" * 60)
    logger.info("페이퍼 트레이딩 세션 중지 중...")
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
                logger.info(f"  최종 자본: ${summary['final_capital']:,.2f}")
                logger.info(f"  총 수익률: {summary['total_return']:.2f}%")
                logger.info(f"  샤프 비율: {summary['sharpe_ratio']:.2f}")
                logger.info(f"  최대 낙폭: {summary['max_drawdown']:.2f}%")
                logger.info(f"  승률: {summary['win_rate']:.2f}%")

                # 거래 횟수 조회
                trades = current_trader.db.get_session_trades(current_trader.session_id)
                logger.info(f"  총 거래: {len(trades)}회")

                # 리포트 생성 및 Slack 업로드
                # (세션 종료 알림은 리포트 업로드와 함께 전송됨)
                try:
                    report_gen = ReportGenerator(current_trader.db)
                    report_files = report_gen.generate_session_report(
                        current_trader.session_id,
                        output_dir='reports/',
                        formats=['csv', 'json']
                    )

                    logger.info("✓ 리포트 생성 완료:")
                    for format_name, file_path in report_files.items():
                        logger.info(f"  {format_name.upper()}: {file_path}")

                    # 리포트 파일을 Slack에 업로드
                    # report_files는 {'summary': 'path1', 'snapshots': 'path2', 'report': 'path3'} 형태
                    file_paths = list(report_files.values())

                    logger.info(f"📤 Slack으로 리포트 파일 업로드 중... ({len(file_paths)}개)")

                    # 세션 요약과 함께 파일 업로드
                    upload_success = notifier.notify_daily_report_with_files(
                        session_summary={
                            'strategy_name': summary.get('strategy_name', 'Unknown'),
                            'total_return': summary['total_return'],
                            'sharpe_ratio': summary['sharpe_ratio'],
                            'max_drawdown': summary['max_drawdown'],
                            'win_rate': summary['win_rate'],
                            'num_trades': len(trades)
                        },
                        report_files=file_paths
                    )

                    if upload_success:
                        logger.info("✓ Slack 리포트 업로드 완료")
                    else:
                        logger.warning("⚠ Slack 리포트 업로드 실패 (Bot Token/Channel 확인 필요)")

                except Exception as e:
                    logger.error(f"✗ 리포트 생성 실패: {e}", exc_info=True)

        current_trader = None

    except Exception as e:
        logger.error(f"✗ 트레이딩 세션 중지 실패: {e}", exc_info=True)
        notifier.notify_error(f"트레이딩 세션 중지 실패: {e}", context="장 마감")


def signal_handler(signum, frame):
    """종료 신호를 우아하게 처리"""
    logger.info("\n\n⚠ 종료 신호 수신")
    if current_trader:
        logger.info("활성 트레이딩 세션 중지 중...")
        stop_paper_trading()
    logger.info("스케줄러 중지됨")
    sys.exit(0)


def main():
    """
    메인 스케줄러 진입점
    """
    # logs 디렉토리가 없으면 생성
    Path('logs').mkdir(exist_ok=True)

    # 우아한 종료를 위한 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 스케줄러 생성
    scheduler = BlockingScheduler(timezone='Asia/Seoul')

    logger.info("=" * 60)
    logger.info("자동매매 트레이딩 스케줄러")
    logger.info("=" * 60)
    logger.info("시간대: Asia/Seoul")
    logger.info("스케줄:")
    logger.info("  23:00 KST - 전략 최적화")
    logger.info("  23:30 KST - 페이퍼 트레이딩 시작")
    logger.info("  06:00 KST - 트레이딩 중지 및 리포트")
    logger.info("=" * 60)

    # 스케줄 작업 추가

    # 장전: 전략 최적화 (23:00 KST)
    scheduler.add_job(
        optimize_strategy,
        CronTrigger(hour=23, minute=0),
        id='optimize_strategy',
        name='전략 최적화',
        misfire_grace_time=300  # 5분 유예 기간
    )

    # 장 시작: 트레이딩 시작 (23:30 KST)
    scheduler.add_job(
        start_paper_trading,
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

    # 스케줄러 시작 (블로킹)
    logger.info("\n✓ 스케줄러 시작 성공")
    logger.info("중지하려면 Ctrl+C를 누르세요\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        signal_handler(None, None)


if __name__ == '__main__':
    main()
