"""
Pre-market strategy optimization logic.

Handles:
- KIS broker initialization
- Real market data fetching
- Multi-strategy parameter optimization
- Regime detection integration
"""

import os
import logging
from typing import Optional, List

import pandas as pd

from trading_bot.brokers import KoreaInvestmentBroker
from trading_bot.strategies import (
    RSIStrategy, MACDStrategy, BollingerBandsStrategy,
    RSIMACDComboStrategy,
)
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.simulation_data import SimulationDataGenerator

import trading_bot.scheduler.scheduler_state as state

logger = logging.getLogger(__name__)


def _create_kis_broker() -> Optional[KoreaInvestmentBroker]:
    """
    Streamlit 의존성 없이 KIS 브로커를 직접 초기화합니다.
    환경 변수에서 인증 정보를 읽어 브로커를 생성합니다.
    """
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

    best_df = max(all_dfs, key=len)
    logger.info(f"최적화 기준 데이터: {len(best_df)}개 봉")

    return best_df


def optimize_strategy():
    """
    장전 작업: 전략 파라미터 최적화
    장 시작 30분 전 실행

    실제 시장 데이터를 사용하여 최적화합니다.
    실제 데이터 조회 실패 시 시뮬레이션 데이터로 폴백합니다.
    """
    logger.info("=" * 60)
    logger.info("전략 최적화 시작...")
    logger.info("=" * 60)

    state.scheduler_health.update('optimizing')

    try:
        # 1. 실제 시장 데이터로 최적화 시도
        df = None
        data_source = "시뮬레이션"
        optimization_symbols_str = os.getenv('OPTIMIZATION_SYMBOLS', 'AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,WMT')
        optimization_symbols = [s.strip() for s in optimization_symbols_str.split(',')]

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
        if state.global_regime_detector and len(df) > 0:
            try:
                regime_result = state.global_regime_detector.detect(df)
                logger.info(f"현재 시장 레짐: {regime_result.regime.value} (신뢰도: {regime_result.confidence:.2f})")
                logger.info(f"  ADX: {regime_result.adx:.1f}, 추세: {regime_result.trend_direction:.2f}")
                logger.info(f"  변동성 백분위: {regime_result.volatility_percentile:.1f}%")
                logger.info(f"  추천 전략: {', '.join(regime_result.recommended_strategies)}")

                # LLM 레짐 판단 보강 (14B 모델)
                if state.global_llm_client:
                    try:
                        from dataclasses import asdict
                        regime_dict = asdict(regime_result)
                        regime_dict['regime'] = regime_result.regime.value
                        recent_returns = df['close'].pct_change().tail(10).tolist()
                        judgment = state.global_llm_client.judge_regime({
                            'statistical_regime': regime_dict,
                            'market_data': {'recent_returns': recent_returns},
                            'active_strategies': list(state.STRATEGY_CLASS_MAP.keys()),
                        })
                        if judgment:
                            logger.info(f"LLM 레짐 판단: override={judgment.regime_override}, 신뢰도={judgment.confidence:.2f}")
                            logger.info(f"  분석: {judgment.analysis[:200]}")
                    except Exception as e:
                        logger.warning(f"LLM 레짐 판단 실패 (무시): {e}")
            except Exception as e:
                logger.warning(f"레짐 감지 실패 (무시): {e}")

        # 3. 다전략 비교 최적화
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
        state.notifier.send_slack(
            f"*전략 최적화 완료* (데이터: {data_source})\n\n"
            f"최적 전략: {best_strategy_name}\n"
            f"최적 파라미터: {best_result['params']}\n"
            f"샤프 비율: {best_result['sharpe_ratio']:.2f}\n"
            f"총 수익률: {best_result['total_return']:.2f}%\n"
            f"거래 횟수: {best_result.get('total_trades', 'N/A')}회",
            color='good'
        )

        # 최적 파라미터와 전략 클래스를 전역 변수에 저장 (다음 트레이딩 세션에서 사용)
        state.optimized_params = best_result['params']
        state.optimized_strategy_class = best_strategy_class

        logger.info(f"✓ 최적 파라미터 전역 변수에 저장 완료 (전략: {best_strategy_name})")

    except Exception as e:
        logger.error(f"✗ 최적화 실패: {e}", exc_info=True)
        state.optimized_params = None
        state.optimized_strategy_class = None
        state.notifier.notify_error(f"전략 최적화 실패: {e}", context="장전 작업")
