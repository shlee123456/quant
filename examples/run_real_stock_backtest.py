"""
실제 종목 백테스팅 예제

yfinance를 사용하여 실제 미국 주식의 과거 데이터로 백테스트를 실행합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from trading_bot.strategies import RSIStrategy, MACDStrategy
from trading_bot.backtester import Backtester
from dashboard.yfinance_helper import fetch_ohlcv_yfinance, validate_symbol
import pandas as pd


def run_backtest_on_real_stock(
    symbol: str,
    period: str = '2y',
    strategy_name: str = 'RSI',
    strategy_params: dict = None
):
    """
    실제 종목으로 백테스트 실행

    Args:
        symbol: 주식 심볼 (예: 'AAPL', 'MSFT')
        period: 조회 기간 ('1mo', '3mo', '6mo', '1y', '2y', '5y', 'max')
        strategy_name: 전략 이름 ('RSI', 'MACD')
        strategy_params: 전략 파라미터 (None이면 기본값 사용)
    """
    print(f"\n{'='*60}")
    print(f"실제 종목 백테스팅: {symbol} ({period})")
    print(f"{'='*60}\n")

    # 1. 종목 유효성 검증
    print(f"1️⃣ 종목 '{symbol}' 유효성 검증 중...")
    if not validate_symbol(symbol):
        print(f"❌ '{symbol}'은(는) 유효하지 않은 종목 심볼입니다.")
        return None

    print(f"✅ '{symbol}'은(는) 유효한 종목입니다.")

    # 2. 과거 데이터 조회
    print(f"\n2️⃣ {symbol} 과거 데이터 조회 중 (기간: {period})...")
    df = fetch_ohlcv_yfinance(symbol, period=period, interval='1d')

    if df is None or df.empty:
        print(f"❌ {symbol} 데이터를 조회할 수 없습니다.")
        return None

    print(f"✅ 데이터 조회 완료: {len(df)}개 일봉")
    print(f"   기간: {df['timestamp'].min().date()} ~ {df['timestamp'].max().date()}")

    # 3. 전략 생성
    print(f"\n3️⃣ 전략 생성: {strategy_name}")

    if strategy_params is None:
        strategy_params = {}

    if strategy_name == 'RSI':
        strategy = RSIStrategy(**strategy_params)
    elif strategy_name == 'MACD':
        strategy = MACDStrategy(**strategy_params)
    else:
        print(f"❌ 지원하지 않는 전략: {strategy_name}")
        return None

    print(f"✅ 전략: {strategy.name}")

    # 4. 백테스트 실행
    print(f"\n4️⃣ 백테스트 실행 중...")
    backtester = Backtester(strategy=strategy, initial_capital=10000.0)
    results = backtester.run(df)

    # 5. 결과 출력
    print(f"\n{'='*60}")
    print(f"📊 백테스트 결과")
    print(f"{'='*60}\n")

    print(f"초기 자본:     ${results['initial_capital']:,.2f}")
    print(f"최종 자본:     ${results['final_capital']:,.2f}")
    print(f"총 수익률:     {results['total_return']:.2f}%")
    print(f"Sharpe Ratio:  {results['sharpe_ratio']:.2f}")
    print(f"최대 낙폭:     {results['max_drawdown']:.2f}%")
    print(f"승률:          {results['win_rate']:.2f}%")
    print(f"총 거래 횟수:  {results['total_trades']}")

    print(f"\n{'='*60}\n")

    return results


def compare_multiple_stocks(symbols: list, period: str = '1y'):
    """
    여러 종목에서 동일 전략 비교

    Args:
        symbols: 종목 심볼 리스트
        period: 조회 기간
    """
    print(f"\n{'='*60}")
    print(f"여러 종목 비교 백테스팅 ({period})")
    print(f"{'='*60}\n")

    results_list = []

    for symbol in symbols:
        print(f"\n🔹 {symbol} 백테스팅...")
        results = run_backtest_on_real_stock(
            symbol=symbol,
            period=period,
            strategy_name='RSI',
            strategy_params={'period': 14, 'overbought': 70, 'oversold': 30}
        )

        if results:
            results_list.append({
                'Symbol': symbol,
                'Total Return %': results['total_return'],
                'Sharpe Ratio': results['sharpe_ratio'],
                'Max Drawdown %': results['max_drawdown'],
                'Win Rate %': results['win_rate'],
                'Total Trades': results['total_trades']
            })

    # 비교 테이블 출력
    if results_list:
        df = pd.DataFrame(results_list)
        print(f"\n{'='*60}")
        print(f"📊 종목별 성과 비교")
        print(f"{'='*60}\n")
        print(df.to_string(index=False))
        print(f"\n{'='*60}\n")

        # 최고 성과 종목
        best_return = df.loc[df['Total Return %'].idxmax()]
        print(f"🏆 최고 수익률: {best_return['Symbol']} ({best_return['Total Return %']:.2f}%)")

        best_sharpe = df.loc[df['Sharpe Ratio'].idxmax()]
        print(f"🏆 최고 Sharpe Ratio: {best_sharpe['Symbol']} ({best_sharpe['Sharpe Ratio']:.2f})")


if __name__ == '__main__':
    # 예제 1: AAPL 2년 백테스트
    print("\n" + "="*80)
    print("예제 1: AAPL 2년 백테스트 (RSI 전략)")
    print("="*80)

    run_backtest_on_real_stock(
        symbol='AAPL',
        period='2y',
        strategy_name='RSI',
        strategy_params={'period': 14, 'overbought': 70, 'oversold': 30}
    )

    # 예제 2: TSLA 1년 백테스트 (MACD 전략)
    print("\n" + "="*80)
    print("예제 2: TSLA 1년 백테스트 (MACD 전략)")
    print("="*80)

    run_backtest_on_real_stock(
        symbol='TSLA',
        period='1y',
        strategy_name='MACD',
        strategy_params={'fast_period': 12, 'slow_period': 26, 'signal_period': 9}
    )

    # 예제 3: 여러 종목 비교 (테크 대표 종목)
    print("\n" + "="*80)
    print("예제 3: 테크 대표 종목 비교 (1년)")
    print("="*80)

    compare_multiple_stocks(
        symbols=['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA'],
        period='1y'
    )

    print("\n✅ 모든 백테스트가 완료되었습니다!")
    print("\n💡 대시보드에서 더 자세한 차트를 확인하세요:")
    print("   streamlit run dashboard/app.py")
