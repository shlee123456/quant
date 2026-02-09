"""
RSI + MACD 복합 전략 백테스트 예제

기술주 반등 시나리오에 최적화된 복합 전략 테스트
"""
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.strategies import RSIMACDComboStrategy, RSIStrategy, MACDStrategy
from trading_bot.backtester import Backtester
from trading_bot.simulation_data import SimulationDataGenerator
import pandas as pd
from datetime import datetime, timedelta


def fetch_historical_data(symbol: str, days: int = 180) -> pd.DataFrame:
    """
    시뮬레이션 데이터 생성 (실제 마켓과 유사한 패턴)

    Args:
        symbol: 종목 코드 (예: 'AAPL', 'MSFT')
        days: 조회 기간 (일)

    Returns:
        OHLCV DataFrame
    """
    # 종목별 특성 시뮬레이션
    stock_params = {
        'AAPL': {'drift': 0.0003, 'volatility': 0.02, 'base_price': 180.0},
        'MSFT': {'drift': 0.0004, 'volatility': 0.018, 'base_price': 400.0},
        'NVDA': {'drift': 0.0005, 'volatility': 0.03, 'base_price': 500.0},
        'GOOGL': {'drift': 0.0003, 'volatility': 0.02, 'base_price': 140.0},
    }

    params = stock_params.get(symbol, {'drift': 0.0003, 'volatility': 0.02, 'base_price': 100.0})

    generator = SimulationDataGenerator(seed=42)

    # 반등 시나리오 시뮬레이션:
    # 1. 하락장 → 2. 상승장으로 연결
    # 첫 40% 기간: 하락
    df_down = generator.generate_trend_data(
        initial_price=params['base_price'],
        periods=int(days * 0.4),
        timeframe='1d',
        trend='bearish',
        volatility=params['volatility'] * 1.5
    )

    # 나머지 60% 기간: 반등 (상승)
    df_up = generator.generate_trend_data(
        initial_price=df_down['close'].iloc[-1],  # 하락 후 가격에서 시작
        periods=int(days * 0.6),
        timeframe='1d',
        trend='bullish',
        volatility=params['volatility']
    )

    # 두 데이터프레임 연결 (이미 timestamp가 인덱스)
    df = pd.concat([df_down, df_up])

    return df


def run_single_backtest(symbol: str, strategy, initial_capital: float = 10000.0):
    """
    단일 종목 백테스트 실행

    Args:
        symbol: 종목 코드
        strategy: 전략 인스턴스
        initial_capital: 초기 자본

    Returns:
        백테스트 결과
    """
    print(f"\n{'='*60}")
    print(f"백테스트 실행: {symbol}")
    print(f"전략: {strategy}")
    print(f"{'='*60}\n")

    # 1. 데이터 조회
    print(f"1. {symbol} 데이터 조회 중...")
    df = fetch_historical_data(symbol, days=180)
    print(f"   데이터 기간: {df.index[0]} ~ {df.index[-1]}")
    print(f"   총 {len(df)}개 캔들")

    # 2. 백테스트 실행
    print(f"\n2. 백테스트 실행 중...")
    backtester = Backtester(
        strategy=strategy,
        initial_capital=initial_capital,
        position_size=0.95,
        commission=0.001  # 0.1%
    )

    results = backtester.run(df)

    # 3. 결과 출력
    print(f"\n3. 백테스트 결과:")
    print(f"   {'항목':<20} {'값':>15}")
    print(f"   {'-'*37}")
    print(f"   {'초기 자본':<20} ${results['initial_capital']:>14,.2f}")
    print(f"   {'최종 자본':<20} ${results['final_capital']:>14,.2f}")
    print(f"   {'총 수익률':<20} {results['total_return']:>14.2f}%")
    print(f"   {'샤프 비율':<20} {results['sharpe_ratio']:>14.2f}")
    print(f"   {'최대 낙폭':<20} {results['max_drawdown']:>14.2f}%")
    print(f"   {'승률':<20} {results['win_rate']:>14.2f}%")
    print(f"   {'총 거래 횟수':<20} {results['total_trades']:>15}")

    return results


def compare_strategies(symbol: str):
    """
    단일 전략 vs 복합 전략 비교

    Args:
        symbol: 종목 코드
    """
    print(f"\n{'='*60}")
    print(f"전략 비교: {symbol}")
    print(f"{'='*60}\n")

    # 데이터 조회
    df = fetch_historical_data(symbol, days=180)

    # 전략 리스트
    strategies = [
        ('RSI 단독', RSIStrategy(period=14, oversold=30, overbought=70)),
        ('MACD 단독', MACDStrategy(fast_period=12, slow_period=26, signal_period=9)),
        ('RSI+MACD 복합', RSIMACDComboStrategy(
            rsi_period=14,
            rsi_oversold=35,
            rsi_overbought=70,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9
        ))
    ]

    results_list = []

    for name, strategy in strategies:
        print(f"\n{name} 전략 백테스트 중...")
        backtester = Backtester(strategy=strategy, initial_capital=10000.0)
        result = backtester.run(df)
        result['strategy_name'] = name
        results_list.append(result)

    # 비교 테이블 출력
    print(f"\n\n{'='*80}")
    print(f"전략 비교 결과: {symbol}")
    print(f"{'='*80}\n")
    print(f"{'전략':<15} {'수익률':>10} {'샤프':>8} {'낙폭':>8} {'승률':>8} {'거래수':>8}")
    print(f"{'-'*80}")

    for result in results_list:
        print(
            f"{result['strategy_name']:<15} "
            f"{result['total_return']:>9.2f}% "
            f"{result['sharpe_ratio']:>8.2f} "
            f"{result['max_drawdown']:>7.2f}% "
            f"{result['win_rate']:>7.2f}% "
            f"{result['total_trades']:>8}"
        )

    # 최고 전략 찾기
    best_by_return = max(results_list, key=lambda x: x['total_return'])
    best_by_sharpe = max(results_list, key=lambda x: x['sharpe_ratio'])

    print(f"\n✨ 최고 수익률: {best_by_return['strategy_name']} ({best_by_return['total_return']:.2f}%)")
    print(f"✨ 최고 샤프 비율: {best_by_sharpe['strategy_name']} ({best_by_sharpe['sharpe_ratio']:.2f})")


def main():
    """메인 함수"""
    print("\n" + "="*60)
    print("RSI + MACD 복합 전략 백테스트")
    print("기술주 반등 시나리오 테스트")
    print("="*60)

    # 테스트할 기술주 목록
    tech_stocks = ['AAPL', 'MSFT', 'NVDA', 'GOOGL']

    # 복합 전략 인스턴스
    combo_strategy = RSIMACDComboStrategy(
        rsi_period=14,
        rsi_oversold=35,  # RSI 35 이하 (과매도)
        rsi_overbought=70,  # RSI 70 이상 (과매수)
        macd_fast=12,
        macd_slow=26,
        macd_signal=9
    )

    # 각 종목별 백테스트
    all_results = []
    for symbol in tech_stocks:
        try:
            result = run_single_backtest(symbol, combo_strategy)
            result['symbol'] = symbol
            all_results.append(result)
        except Exception as e:
            print(f"\n❌ {symbol} 백테스트 실패: {e}")

    # 전체 요약
    if all_results:
        print(f"\n\n{'='*80}")
        print("전체 종목 백테스트 요약")
        print(f"{'='*80}\n")
        print(f"{'종목':<10} {'수익률':>10} {'샤프':>8} {'낙폭':>8} {'승률':>8} {'거래수':>8}")
        print(f"{'-'*80}")

        for result in all_results:
            print(
                f"{result['symbol']:<10} "
                f"{result['total_return']:>9.2f}% "
                f"{result['sharpe_ratio']:>8.2f} "
                f"{result['max_drawdown']:>7.2f}% "
                f"{result['win_rate']:>7.2f}% "
                f"{result['total_trades']:>8}"
            )

        # 평균 성과
        avg_return = sum(r['total_return'] for r in all_results) / len(all_results)
        avg_sharpe = sum(r['sharpe_ratio'] for r in all_results) / len(all_results)
        avg_drawdown = sum(r['max_drawdown'] for r in all_results) / len(all_results)

        print(f"\n{'평균':<10} {avg_return:>9.2f}% {avg_sharpe:>8.2f} {avg_drawdown:>7.2f}%")

        # 최고 성과 종목
        best = max(all_results, key=lambda x: x['total_return'])
        print(f"\n🏆 최고 수익률: {best['symbol']} ({best['total_return']:.2f}%)")

    # 전략 비교 (AAPL 기준)
    print("\n\n")
    compare_strategies('AAPL')

    print("\n\n백테스트 완료! 🎉\n")


if __name__ == '__main__':
    main()
