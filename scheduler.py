"""
Automated Trading Scheduler

Schedules paper trading sessions during US market hours:
- Pre-market: 23:00 KST - Strategy optimization
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
import argparse
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

import pandas as pd

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
from dotenv import load_dotenv

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy, RSIMACDComboStrategy
from trading_bot.database import TradingDatabase, generate_display_name
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.notifications import NotificationService
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.reports import ReportGenerator
from trading_bot.brokers import KoreaInvestmentBroker

# Regime detection + LLM (optional)
try:
    from trading_bot.regime_detector import RegimeDetector
    _has_regime = True
except ImportError:
    RegimeDetector = None
    _has_regime = False

try:
    from trading_bot.llm_client import LLMClient, LLMConfig
    _has_llm = True
except ImportError:
    LLMClient = LLMConfig = None
    _has_llm = False

# Market analysis (optional)
try:
    from trading_bot.market_analyzer import MarketAnalyzer
    from trading_bot.market_analysis_prompt import build_analysis_prompt
    _has_market_analyzer = True
except ImportError:
    MarketAnalyzer = None
    build_analysis_prompt = None
    _has_market_analyzer = False

import subprocess
import os

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

# 전략 이름 → 클래스 매핑
STRATEGY_CLASS_MAP = {
    'RSI Strategy': RSIStrategy,
    'MACD Strategy': MACDStrategy,
    'Bollinger Bands': BollingerBandsStrategy,
    'RSI+MACD Combo': RSIMACDComboStrategy,
    'RSI+MACD Combo Strategy': RSIMACDComboStrategy,
}

# 멀티 세션 관리 (label → PaperTrader)
active_traders: Dict[str, PaperTrader] = {}
trader_threads: Dict[str, threading.Thread] = {}
traders_lock = threading.Lock()

# Global notification service
notifier = NotificationService()

# Global preset manager
preset_manager = StrategyPresetManager()

# Optimized parameters (loaded from optimization)
optimized_params = None
# 최적화에서 선택된 전략 클래스 (기본: RSIMACDComboStrategy)
optimized_strategy_class = None

# Global regime detector + LLM client (optional)
global_regime_detector = RegimeDetector() if _has_regime else None
global_llm_client = None
if _has_llm:
    import os as _os
    _llm_config = LLMConfig(
        base_url=_os.getenv('LLM_BASE_URL', 'http://192.168.45.222:8080'),
        enabled=_os.getenv('LLM_ENABLED', 'true').lower() in ('true', '1', 'yes'),
    )
    global_llm_client = LLMClient(_llm_config)


def _create_kis_broker() -> Optional[KoreaInvestmentBroker]:
    """
    Streamlit 의존성 없이 KIS 브로커를 직접 초기화합니다.
    환경 변수에서 인증 정보를 읽어 브로커를 생성합니다.
    """
    import os

    appkey = os.getenv('KIS_APPKEY', '').strip()
    appsecret = os.getenv('KIS_APPSECRET', '').strip()
    account = os.getenv('KIS_ACCOUNT', '').strip()

    if not appkey or not appsecret or not account:
        logger.warning("KIS API 환경 변수 미설정 - 브로커 초기화 불가")
        return None

    user_id = os.getenv('KIS_USER_ID', account).strip()
    mock_str = os.getenv('KIS_MOCK', 'true').strip().lower()
    mock = mock_str in ('true', '1', 'yes', 'on')

    try:
        broker = KoreaInvestmentBroker(
            appkey=appkey,
            appsecret=appsecret,
            account=account,
            user_id=user_id,
            mock=mock
        )
        logger.info(f"KIS 브로커 초기화 성공 (mock={mock})")
        return broker
    except Exception as e:
        logger.error(f"KIS 브로커 초기화 실패: {e}")
        return None


def _get_symbol_exchange(symbol: str) -> str:
    """
    심볼의 거래소를 반환합니다 (NASDAQ/NYSE/AMEX).
    StockSymbolDB를 사용하여 거래소 정보를 조회합니다.
    """
    # 주요 종목 거래소 매핑 (빠른 조회용)
    NYSE_SYMBOLS = {
        'LLY', 'WMT', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK',
        'V', 'MA', 'AXP', 'JNJ', 'UNH', 'ABBV', 'MRK', 'TMO', 'ABT',
        'XOM', 'CVX', 'COP', 'SLB', 'EOG',
        'PG', 'KO', 'PM', 'MO',
        'DIS', 'HD', 'LOW', 'MCD', 'NKE', 'TGT',
        'CRM', 'ORCL',
        'BA', 'CAT', 'GE', 'UPS', 'FDX', 'MMM',
        'F', 'GM', 'AMT', 'PLD', 'SPG',
        'LIN', 'APD', 'DD', 'NEE', 'DUK', 'SO',
        'SPY', 'DIA', 'VOO', 'VTI', 'IWM',
        'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU',
        'SNOW', 'NOW', 'PLTR', 'SHOP', 'SQ', 'UBER', 'RBLX', 'U',
        'ARKK',
    }

    if symbol.upper() in NYSE_SYMBOLS:
        return 'NYSE'

    # 기본값: NASDAQ (대부분의 빅테크가 NASDAQ)
    return 'NASDAQ'


def _fetch_real_market_data(broker: KoreaInvestmentBroker, symbols: List[str], limit: int = 100) -> Optional[pd.DataFrame]:
    """
    KIS 브로커로 실제 시장 과거 데이터를 가져옵니다.
    여러 심볼의 데이터를 가져와 하나로 합쳐 최적화에 사용합니다.
    심볼별 거래소(NASDAQ/NYSE)를 자동 감지합니다.

    Args:
        broker: KIS 브로커 인스턴스
        symbols: 종목 코드 리스트
        limit: 각 종목당 가져올 봉 수

    Returns:
        합쳐진 OHLCV DataFrame 또는 None (실패 시)
    """
    import time as _time

    all_dfs = []

    for symbol in symbols:
        try:
            exchange = _get_symbol_exchange(symbol)
            logger.info(f"  {symbol} ({exchange}) 일봉 데이터 조회 중 (최대 {limit}개)...")
            df = broker.fetch_ohlcv(
                symbol=symbol,
                timeframe='1d',
                limit=limit,
                overseas=True,
                market=exchange
            )

            if df is not None and not df.empty:
                logger.info(f"  {symbol}: {len(df)}개 봉 조회 성공 (기간: {df.index[0]} ~ {df.index[-1]})")
                all_dfs.append(df)
            else:
                logger.warning(f"  {symbol}: 데이터 없음")

            # API rate limit 대기
            _time.sleep(0.5)

        except Exception as e:
            logger.warning(f"  {symbol} 데이터 조회 실패: {e}")
            continue

    if not all_dfs:
        logger.error("실제 시장 데이터를 가져올 수 없습니다")
        return None

    # 가장 긴 데이터를 기준으로 사용 (대표 종목)
    # 여러 종목을 개별 최적화하면 더 좋지만, 현재는 대표 종목 1개로 최적화
    best_df = max(all_dfs, key=len)
    logger.info(f"최적화 기준 데이터: {len(best_df)}개 봉")

    return best_df

# 프리셋에서 로드된 설정 목록 (--preset/--presets 인자로 지정)
preset_configs: List[Dict] = []


def optimize_strategy():
    """
    장전 작업: 전략 파라미터 최적화
    장 시작 30분 전 실행

    실제 시장 데이터를 사용하여 최적화합니다.
    실제 데이터 조회 실패 시 시뮬레이션 데이터로 폴백합니다.
    """
    global optimized_params, optimized_strategy_class

    logger.info("=" * 60)
    logger.info("전략 최적화 시작...")
    logger.info("=" * 60)

    try:
        # 1. 실제 시장 데이터로 최적화 시도
        df = None
        data_source = "시뮬레이션"
        optimization_symbols = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'LLY', 'WMT']

        broker = _create_kis_broker()
        if broker:
            logger.info("실제 시장 데이터 조회 시도...")
            df = _fetch_real_market_data(broker, optimization_symbols, limit=200)
            if df is not None and len(df) >= 50:
                data_source = "실제 시장"
                logger.info(f"실제 시장 데이터 사용: {len(df)}개 봉")
            else:
                logger.warning("실제 시장 데이터 부족 - 시뮬레이션 데이터로 폴백")
                df = None

        # 2. 실제 데이터 실패 시 시뮬레이션 폴백
        if df is None:
            logger.info("시뮬레이션 데이터로 최적화 진행...")
            data_gen = SimulationDataGenerator(seed=42)
            df_bullish = data_gen.generate_trend_data(periods=200, trend='bullish', initial_price=150.0)
            df_bearish = data_gen.generate_trend_data(periods=200, trend='bearish', initial_price=150.0)
            df_sideways = data_gen.generate_trend_data(periods=200, trend='sideways', initial_price=150.0)
            df = pd.concat([df_bullish, df_bearish, df_sideways], ignore_index=True)
            data_source = "시뮬레이션"

        logger.info(f"최적화 데이터 소스: {data_source} ({len(df)}개 봉)")

        # 2.5. 레짐 감지 (최적화 전 시장 상태 파악)
        if global_regime_detector and len(df) > 0:
            try:
                regime_result = global_regime_detector.detect(df)
                logger.info(f"현재 시장 레짐: {regime_result.regime.value} (신뢰도: {regime_result.confidence:.2f})")
                logger.info(f"  ADX: {regime_result.adx:.1f}, 추세: {regime_result.trend_direction:.2f}")
                logger.info(f"  변동성 백분위: {regime_result.volatility_percentile:.1f}%")
                logger.info(f"  추천 전략: {', '.join(regime_result.recommended_strategies)}")

                # LLM 레짐 판단 보강 (14B 모델)
                if global_llm_client:
                    try:
                        from dataclasses import asdict
                        regime_dict = asdict(regime_result)
                        regime_dict['regime'] = regime_result.regime.value
                        recent_returns = df['close'].pct_change().tail(10).tolist()
                        judgment = global_llm_client.judge_regime({
                            'statistical_regime': regime_dict,
                            'market_data': {'recent_returns': recent_returns},
                            'active_strategies': list(STRATEGY_CLASS_MAP.keys()),
                        })
                        if judgment:
                            logger.info(f"LLM 레짐 판단: override={judgment.regime_override}, 신뢰도={judgment.confidence:.2f}")
                            logger.info(f"  분석: {judgment.analysis[:200]}")
                    except Exception as e:
                        logger.warning(f"LLM 레짐 판단 실패 (무시): {e}")
            except Exception as e:
                logger.warning(f"레짐 감지 실패 (무시): {e}")

        # 3. 다전략 비교 최적화
        # RSI/MACD 단독 전략이 Combo보다 신호 빈도가 높아 거래 발생 가능성이 큼
        optimizer = StrategyOptimizer(initial_capital=10000.0)

        strategy_configs = [
            {
                'name': 'RSI',
                'class': RSIStrategy,
                'grid': {
                    'period': [10, 14, 20],
                    'overbought': [65, 70, 75],
                    'oversold': [25, 30, 35],
                },
            },
            {
                'name': 'MACD',
                'class': MACDStrategy,
                'grid': {
                    'fast_period': [8, 12],
                    'slow_period': [21, 26],
                    'signal_period': [7, 9],
                },
            },
            {
                'name': 'Bollinger Bands',
                'class': BollingerBandsStrategy,
                'grid': {
                    'period': [15, 20, 25],
                    'std_dev': [1.5, 2.0, 2.5],
                },
            },
            {
                'name': 'RSI+MACD Combo',
                'class': RSIMACDComboStrategy,
                'grid': {
                    'rsi_period': [10, 14, 20],
                    'rsi_overbought': [65, 70, 75],
                    'rsi_oversold': [25, 30, 35],
                    'macd_fast': [12],
                    'macd_slow': [26],
                    'macd_signal': [9],
                },
            },
        ]

        # 4. 각 전략별 최적화 실행 후 비교
        all_candidates = []

        for config in strategy_configs:
            logger.info(f"{config['name']} 전략 최적화 중...")
            try:
                result = optimizer.optimize(config['class'], df, config['grid'])
                result['_strategy_name'] = config['name']
                result['_strategy_class'] = config['class']

                trades = result.get('total_trades', 0)
                logger.info(f"  {config['name']}: 거래 {trades}회, 수익률 {result['total_return']:.2f}%, Sharpe {result['sharpe_ratio']:.2f}")

                if trades > 0:
                    all_candidates.append(result)
            except Exception as e:
                logger.warning(f"  {config['name']} 최적화 실패: {e}")

        # 5. 거래가 발생한 전략 중 최적 선택
        best_result = None
        best_strategy_name = "RSI+MACD Combo Strategy"
        best_strategy_class = RSIMACDComboStrategy

        if all_candidates:
            # Sharpe ratio 기준 정렬 (동일하면 거래 횟수 많은 것 우선)
            all_candidates.sort(key=lambda x: (x['sharpe_ratio'], x.get('total_trades', 0)), reverse=True)
            best_result = all_candidates[0]
            best_strategy_name = best_result['_strategy_name']
            best_strategy_class = best_result['_strategy_class']

            logger.info(f"최적 전략: {best_strategy_name}")
            logger.info(f"  후보 전략 수: {len(all_candidates)}개")
            for c in all_candidates:
                logger.info(f"  - {c['_strategy_name']}: Sharpe {c['sharpe_ratio']:.2f}, 수익률 {c['total_return']:.2f}%, 거래 {c.get('total_trades', 0)}회")
        else:
            logger.warning("모든 전략에서 거래 0건 - RSI 기본 파라미터 사용")
            best_result = {
                'params': {'period': 14, 'overbought': 70, 'oversold': 30},
                'sharpe_ratio': 0.0,
                'total_return': 0.0,
                'total_trades': 0
            }
            best_strategy_name = "RSI"
            best_strategy_class = RSIStrategy

        # 전략 이름을 STRATEGY_CLASS_MAP 키로 변환
        strategy_map_name = {
            'RSI': 'RSI Strategy',
            'MACD': 'MACD Strategy',
            'RSI+MACD Combo': 'RSI+MACD Combo Strategy',
            'Bollinger Bands': 'Bollinger Bands',
        }
        mapped_strategy_name = strategy_map_name.get(best_strategy_name, best_strategy_name)

        logger.info(f"✓ 최적화 완료!")
        logger.info(f"  데이터 소스: {data_source}")
        logger.info(f"  최적 전략: {best_strategy_name}")
        logger.info(f"  최적 파라미터: {best_result['params']}")
        logger.info(f"  샤프 비율: {best_result['sharpe_ratio']:.2f}")
        logger.info(f"  총 수익률: {best_result['total_return']:.2f}%")
        logger.info(f"  거래 횟수: {best_result.get('total_trades', 'N/A')}회")

        # 알림 전송
        notifier.send_slack(
            f"*전략 최적화 완료* (데이터: {data_source})\n\n"
            f"최적 전략: {best_strategy_name}\n"
            f"최적 파라미터: {best_result['params']}\n"
            f"샤프 비율: {best_result['sharpe_ratio']:.2f}\n"
            f"총 수익률: {best_result['total_return']:.2f}%\n"
            f"거래 횟수: {best_result.get('total_trades', 'N/A')}회",
            color='good'
        )

        # 최적 파라미터와 전략 클래스를 전역 변수에 저장 (다음 트레이딩 세션에서 사용)
        optimized_params = best_result['params']
        optimized_strategy_class = best_strategy_class

        # 프리셋으로 저장 (영속성)
        preset_name = f"자동최적화_{datetime.now().strftime('%Y%m%d_%H%M')}"
        preset_manager.save_preset(
            name=preset_name,
            description=f"자동 최적화 결과 (데이터: {data_source}, 전략: {best_strategy_name}, Sharpe: {best_result['sharpe_ratio']:.2f}, 거래: {best_result.get('total_trades', 0)}회)",
            strategy=mapped_strategy_name,
            strategy_params=best_result['params'],
            symbols=optimization_symbols,
            initial_capital=10000.0,
            position_size=0.2,
            stop_loss_pct=0.03,
            take_profit_pct=0.05,
            enable_stop_loss=True,
            enable_take_profit=True
        )

        logger.info(f"✓ 최적 파라미터 프리셋 저장: {preset_name}")

    except Exception as e:
        logger.error(f"✗ 최적화 실패: {e}", exc_info=True)
        notifier.notify_error(f"전략 최적화 실패: {e}", context="장전 작업")


def _start_single_session(label: str, config: Optional[Dict]):
    """
    단일 트레이딩 세션을 daemon thread로 시작하는 헬퍼

    Args:
        label: 세션 라벨 (로그 접두어로 사용)
        config: 프리셋 설정 dict 또는 None (기본 설정 사용)
    """
    log_prefix = f"[{label}]"

    try:
        # 브로커 초기화
        broker = _create_kis_broker()
        if not broker:
            logger.error(f"{log_prefix} ✗ KIS 브로커 초기화 실패 - 세션을 시작할 수 없습니다")
            notifier.notify_error(f"KIS 브로커 초기화 실패", context=f"세션 시작: {label}")
            return

        # 데이터베이스 초기화
        db = TradingDatabase()

        # 기본 설정 (Top 10 US Market Cap)
        strategy_name = "RSI+MACD Combo Strategy"
        strategy_params = None
        symbols = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'LLY', 'WMT']
        initial_capital = 10000.0
        position_size = 0.1  # 10종목 × 10% = 100%
        stop_loss_pct = 0.03
        take_profit_pct = 0.05
        enable_stop_loss = True
        enable_take_profit = True

        # 프리셋에서 설정 적용
        if config:
            strategy_name = config.get('strategy', strategy_name)
            strategy_params = config.get('strategy_params')
            symbols = config.get('symbols', symbols)
            initial_capital = config.get('initial_capital', initial_capital)
            position_size = config.get('position_size', position_size)
            stop_loss_pct = config.get('stop_loss_pct', stop_loss_pct)
            take_profit_pct = config.get('take_profit_pct', take_profit_pct)
            enable_stop_loss = config.get('enable_stop_loss', enable_stop_loss)
            enable_take_profit = config.get('enable_take_profit', enable_take_profit)
            logger.info(f"{log_prefix} 프리셋 설정 적용됨: {config.get('_preset_name', label)}")

        # 전략 클래스 결정
        strategy_class = STRATEGY_CLASS_MAP.get(strategy_name, RSIMACDComboStrategy)

        # 전략 생성 (우선순위: CLI 프리셋 > 최적화 결과 > 기본값)
        if config and strategy_params:
            logger.info(f"{log_prefix} CLI 프리셋 파라미터 사용 (--preset 우선): {strategy_params}")
            strategy = strategy_class(**strategy_params)
        elif optimized_params and optimized_strategy_class:
            # 최적화에서 선택된 전략 클래스와 파라미터 사용
            strategy_class = optimized_strategy_class
            logger.info(f"{log_prefix} 최적화된 전략 사용: {strategy_class.__name__}, 파라미터: {optimized_params}")
            strategy = strategy_class(**optimized_params)
        elif optimized_params:
            logger.info(f"{log_prefix} 최적화된 파라미터 사용: {optimized_params}")
            strategy = strategy_class(**optimized_params)
        else:
            logger.info(f"{log_prefix} 기본 파라미터 사용 (프리셋/최적화 없음) - {strategy_name}")
            strategy = strategy_class()

        logger.info(f"{log_prefix} 전략: {strategy.name}")
        logger.info(f"{log_prefix} 종목: {', '.join(symbols)}")

        # display_name 생성
        display_name = generate_display_name(
            strategy_name=strategy.name,
            symbols=symbols,
            preset_name=label if config else None
        )

        # 페이퍼 트레이더 생성 (레짐 감지 + LLM 통합)
        trader = PaperTrader(
            strategy=strategy,
            symbols=symbols,
            broker=broker,
            initial_capital=initial_capital,
            position_size=position_size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            enable_stop_loss=enable_stop_loss,
            enable_take_profit=enable_take_profit,
            db=db,
            display_name=display_name,
            regime_detector=global_regime_detector,
            llm_client=global_llm_client,
        )

        # Attach notifier to trader for stop loss/take profit notifications
        trader.notifier = notifier

        logger.info(f"{log_prefix} ✓ 페이퍼 트레이더 초기화 완료")
        logger.info(f"{log_prefix}   초기 자본: ${trader.initial_capital:,.2f}")
        logger.info(f"{log_prefix}   포지션 크기: {trader.position_size:.0%}")
        logger.info(f"{log_prefix}   손절매: {trader.stop_loss_pct:.0%} ({'활성' if trader.enable_stop_loss else '비활성'})")
        logger.info(f"{log_prefix}   익절매: {trader.take_profit_pct:.0%} ({'활성' if trader.enable_take_profit else '비활성'})")

        # 세션 시작 알림 전송
        notifier.notify_session_start({
            'strategy_name': display_name,
            'symbols': symbols,
            'initial_capital': trader.initial_capital
        })

        # active_traders에 등록
        with traders_lock:
            active_traders[label] = trader

        # daemon thread로 실시간 트레이딩 시작
        def run_trading():
            _run_trader_thread(label, trader)

        thread = threading.Thread(target=run_trading, name=f"trader-{label}", daemon=True)
        with traders_lock:
            trader_threads[label] = thread
        thread.start()

        logger.info(f"{log_prefix} 실시간 트레이딩 루프 시작 (60초 간격, 1시간봉)...")

    except Exception as e:
        logger.error(f"{log_prefix} ✗ 페이퍼 트레이딩 실패: {e}", exc_info=True)
        notifier.notify_error(f"페이퍼 트레이딩 실패: {e}", context=f"세션: {label}")
        with traders_lock:
            active_traders.pop(label, None)
            trader_threads.pop(label, None)


def _run_trader_thread(label: str, trader: PaperTrader):
    """
    daemon thread에서 실행되는 트레이딩 루프

    Args:
        label: 세션 라벨
        trader: PaperTrader 인스턴스
    """
    log_prefix = f"[{label}]"
    try:
        trader.run_realtime(interval_seconds=60, timeframe='1h')
    except Exception as e:
        logger.error(f"{log_prefix} ✗ 트레이딩 루프 오류: {e}", exc_info=True)
    finally:
        logger.info(f"{log_prefix} 트레이딩 루프 종료됨")


def start_paper_trading():
    """
    장 시작 작업: 페이퍼 트레이딩 세션 시작
    장 시작 시각 (23:30 KST) 실행

    preset_configs에 등록된 프리셋 수만큼 세션을 동시 시작합니다.
    프리셋이 없으면 기본 설정 1개 세션을 시작합니다.
    """
    logger.info("=" * 60)
    logger.info("페이퍼 트레이딩 세션 시작...")
    logger.info("=" * 60)

    if preset_configs:
        logger.info(f"총 {len(preset_configs)}개 프리셋 세션 시작")
        for cfg in preset_configs:
            label = cfg.get('_preset_name', 'unknown')
            _start_single_session(label, cfg)
    else:
        # 프리셋 없이 기본 설정 1개 세션
        _start_single_session("기본", None)

    with traders_lock:
        logger.info(f"✓ 활성 세션 수: {len(active_traders)}")


def _stop_single_session(label: str):
    """
    단일 트레이딩 세션 중지 및 리포트 생성 헬퍼

    Args:
        label: 세션 라벨
    """
    log_prefix = f"[{label}]"

    with traders_lock:
        trader = active_traders.pop(label, None)
        thread = trader_threads.pop(label, None)

    if trader is None:
        logger.warning(f"{log_prefix} ⚠ 중지할 세션 없음")
        return

    try:
        # 트레이딩 루프에 종료 시그널 전송
        trader.is_running = False
        trader._stop_event.set()

        # 트레이딩 루프가 실제로 종료될 때까지 대기 (최대 120초)
        logger.info(f"{log_prefix} 트레이딩 루프 종료 대기 중...")
        if thread and thread.is_alive():
            thread.join(timeout=120)
            if thread.is_alive():
                logger.warning(f"{log_prefix} ⚠ 트레이딩 스레드가 120초 내에 종료되지 않음 - 강제 종료 진행")
            else:
                logger.info(f"{log_prefix} ✓ 트레이딩 스레드 정상 종료")
        else:
            # thread가 없거나 이미 종료된 경우 _loop_exited 이벤트로 대기
            exited = trader._loop_exited.wait(timeout=120)
            if exited:
                logger.info(f"{log_prefix} ✓ 트레이딩 루프 정상 종료")
            else:
                logger.warning(f"{log_prefix} ⚠ 트레이딩 루프가 120초 내에 종료되지 않음 - 강제 종료 진행")

        # 세션 종료 및 DB 업데이트
        trader.stop()

        # 세션 요약 조회
        if trader.session_id and trader.db:
            summary = trader.db.get_session_summary(trader.session_id)

            if summary:
                logger.info(f"{log_prefix} ✓ 세션 중지 성공")
                logger.info(f"{log_prefix}   세션 ID: {trader.session_id}")
                logger.info(f"{log_prefix}   최종 자본: ${summary['final_capital']:,.2f}" if summary['final_capital'] is not None else f"{log_prefix}   최종 자본: N/A")
                logger.info(f"{log_prefix}   총 수익률: {summary['total_return']:.2f}%" if summary['total_return'] is not None else f"{log_prefix}   총 수익률: N/A")
                logger.info(f"{log_prefix}   샤프 비율: {summary['sharpe_ratio']:.2f}" if summary['sharpe_ratio'] is not None else f"{log_prefix}   샤프 비율: N/A (데이터 부족)")
                logger.info(f"{log_prefix}   최대 낙폭: {summary['max_drawdown']:.2f}%" if summary['max_drawdown'] is not None else f"{log_prefix}   최대 낙폭: N/A (데이터 부족)")
                logger.info(f"{log_prefix}   승률: {summary['win_rate']:.2f}%" if summary['win_rate'] is not None else f"{log_prefix}   승률: N/A (매도 거래 없음)")

                # 거래 횟수 조회
                trades = trader.db.get_session_trades(trader.session_id)
                logger.info(f"{log_prefix}   총 거래: {len(trades)}회")

                # 리포트 생성 및 Slack 업로드
                try:
                    report_gen = ReportGenerator(trader.db)
                    report_files = report_gen.generate_session_report(
                        trader.session_id,
                        output_dir='reports/',
                        formats=['csv', 'json']
                    )

                    logger.info(f"{log_prefix} ✓ 리포트 생성 완료:")
                    for format_name, file_path in report_files.items():
                        logger.info(f"{log_prefix}   {format_name.upper()}: {file_path}")

                    # 리포트 파일을 Slack에 업로드
                    file_paths = list(report_files.values())

                    logger.info(f"{log_prefix} 📤 Slack으로 리포트 파일 업로드 중... ({len(file_paths)}개)")

                    # 세션 요약과 함께 파일 업로드
                    upload_success = notifier.notify_daily_report_with_files(
                        session_summary={
                            'strategy_name': summary.get('display_name') or f"{label} - {summary.get('strategy_name', 'Unknown')}",
                            'total_return': summary['total_return'] if summary['total_return'] is not None else 0.0,
                            'sharpe_ratio': summary['sharpe_ratio'] if summary['sharpe_ratio'] is not None else 0.0,
                            'max_drawdown': summary['max_drawdown'] if summary['max_drawdown'] is not None else 0.0,
                            'win_rate': summary['win_rate'] if summary['win_rate'] is not None else 0.0,
                            'num_trades': len(trades)
                        },
                        report_files=file_paths
                    )

                    if upload_success:
                        logger.info(f"{log_prefix} ✓ Slack 리포트 업로드 완료")
                    else:
                        logger.warning(f"{log_prefix} ⚠ Slack 리포트 업로드 실패 (Bot Token/Channel 확인 필요)")

                except Exception as e:
                    logger.error(f"{log_prefix} ✗ 리포트 생성 실패: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"{log_prefix} ✗ 트레이딩 세션 중지 실패: {e}", exc_info=True)
        notifier.notify_error(f"트레이딩 세션 중지 실패: {e}", context=f"장 마감: {label}")


def stop_paper_trading():
    """
    장 마감 작업: 모든 페이퍼 트레이딩 세션 중지 및 리포트 생성
    장 마감 시각 (06:00 KST) 실행
    """
    logger.info("=" * 60)
    logger.info("모든 페이퍼 트레이딩 세션 중지 중...")
    logger.info("=" * 60)

    with traders_lock:
        labels = list(active_traders.keys())

    if not labels:
        logger.warning("⚠ 중지할 활성 트레이딩 세션 없음")
        return

    logger.info(f"총 {len(labels)}개 세션 중지 시작")

    for label in labels:
        _stop_single_session(label)

    logger.info(f"✓ 전체 {len(labels)}개 세션 중지 완료")


def run_market_analysis():
    """
    장 마감 후 시장 분석: MarketAnalyzer로 데이터 수집 + Claude로 노션 작성
    06:10 KST 실행
    """
    logger.info("=" * 60)
    logger.info("시장 분석 시작...")
    logger.info("=" * 60)

    if not _has_market_analyzer:
        logger.warning("MarketAnalyzer 모듈 미설치 - 시장 분석 건너뜀")
        return

    # 환경 변수에서 설정 읽기
    enabled = os.getenv('MARKET_ANALYSIS_ENABLED', 'true').strip().lower()
    if enabled not in ('true', '1', 'yes'):
        logger.info("MARKET_ANALYSIS_ENABLED=false - 시장 분석 비활성화됨")
        return

    symbols_str = os.getenv(
        'MARKET_ANALYSIS_SYMBOLS',
        'AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,WMT'
    )
    symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]

    try:
        # 브로커 초기화
        broker = _create_kis_broker()
        if not broker:
            logger.error("KIS 브로커 초기화 실패 - 시장 분석 불가")
            notifier.notify_error("KIS 브로커 초기화 실패", context="시장 분석")
            return

        # MarketAnalyzer로 데이터 수집
        analyzer = MarketAnalyzer()
        logger.info(f"분석 대상 종목: {', '.join(symbols)}")
        result = analyzer.analyze(symbols, broker)

        # JSON 저장
        json_path = analyzer.save_json(result)
        logger.info(f"분석 결과 저장: {json_path}")

        # Claude로 노션 작성
        prompt = build_analysis_prompt(json_path)
        logger.info("Claude에게 노션 작성 요청 중...")

        # CLAUDECODE 환경 변수 제거 (중첩 세션 방지), stdin으로 프롬프트 전달
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDECODE'}
        proc = subprocess.run(
            ["claude", "-p", "--model", "opus", "--allowedTools", "mcp__claude_ai_Notion__*,Read"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )

        if proc.returncode == 0:
            logger.info("노션 작성 완료")
            notifier.send_slack(
                f"*시장 분석 완료*\n\n"
                f"분석 종목: {', '.join(symbols)}\n"
                f"결과 파일: {json_path}\n"
                f"노션 페이지 작성 완료",
                color='good'
            )
        else:
            logger.warning(f"Claude 노션 작성 실패 (returncode={proc.returncode})")
            logger.warning(f"stderr: {proc.stderr[:500] if proc.stderr else 'N/A'}")
            notifier.send_slack(
                f"*시장 분석 완료 (노션 작성 실패)*\n\n"
                f"분석 종목: {', '.join(symbols)}\n"
                f"결과 파일: {json_path}\n"
                f"노션 작성 오류: {proc.stderr[:200] if proc.stderr else 'unknown'}",
                color='warning'
            )

    except subprocess.TimeoutExpired:
        logger.error("Claude 노션 작성 타임아웃 (120초 초과)")
        notifier.notify_error("Claude 노션 작성 타임아웃", context="시장 분석")
    except Exception as e:
        logger.error(f"시장 분석 실패: {e}", exc_info=True)
        notifier.notify_error(f"시장 분석 실패: {e}", context="시장 분석")


def signal_handler(signum, frame):
    """종료 신호를 우아하게 처리"""
    logger.info("\n\n⚠ 종료 신호 수신")
    with traders_lock:
        has_active = len(active_traders) > 0
    if has_active:
        logger.info("활성 트레이딩 세션 중지 중...")
        try:
            stop_paper_trading()
        except Exception as e:
            logger.error(f"✗ 세션 중지 중 에러 (무시): {e}", exc_info=True)
    logger.info("스케줄러 중지됨")
    sys.exit(0)


def main():
    """
    메인 스케줄러 진입점
    """
    global preset_configs

    # CLI 인자 파싱
    parser = argparse.ArgumentParser(description='자동매매 트레이딩 스케줄러')
    parser.add_argument('--preset', type=str, default=None,
                        help='사용할 프리셋 이름 (예: "스윙트레이딩 - RSI 보수적")')
    parser.add_argument('--presets', type=str, nargs='+', default=None,
                        help='동시 실행할 프리셋 이름 목록 (예: "RSI 보수적" "MACD 추세")')
    parser.add_argument('--list-presets', action='store_true',
                        help='저장된 프리셋 목록 표시')
    args = parser.parse_args()

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

    # 프리셋 이름 목록 통합 (--preset → 1개짜리 리스트로 변환)
    preset_names: List[str] = []
    if args.presets:
        preset_names = args.presets
    elif args.preset:
        preset_names = [args.preset]

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
            preset_configs.append(loaded)
            logger.info(f"✓ 프리셋 '{name}' 로드 완료")
            logger.info(f"  전략: {loaded['strategy']}")
            logger.info(f"  종목: {', '.join(loaded.get('symbols', []))}")
            logger.info(f"  파라미터: {loaded.get('strategy_params', {})}")

    # logs 디렉토리가 없으면 생성
    Path('logs').mkdir(exist_ok=True)

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
    if preset_configs:
        logger.info(f"프리셋 ({len(preset_configs)}개):")
        for cfg in preset_configs:
            logger.info(f"  - {cfg['_preset_name']} ({cfg['strategy']})")
    else:
        logger.info("프리셋: 없음 (기본 설정 1개 세션)")
    logger.info("시간대: Asia/Seoul")
    logger.info("스케줄:")
    logger.info("  23:00 KST - 전략 최적화")
    logger.info("  23:30 KST - 페이퍼 트레이딩 시작")
    logger.info("  06:00 KST - 트레이딩 중지 및 리포트")
    logger.info("  06:10 KST - 시장 분석 + 노션 작성")
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

    # 장 마감 후: 시장 분석 + 노션 작성 (06:10 KST)
    scheduler.add_job(
        run_market_analysis,
        CronTrigger(hour=6, minute=10),
        id='market_analysis',
        name='시장 분석 + 노션 작성',
        misfire_grace_time=600
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
