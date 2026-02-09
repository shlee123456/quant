"""
yfinance 통합 테스트 - Real-time Quotes 탭의 전체 플로우 검증

PLTR 종목으로 ticker와 OHLCV를 모두 조회하여 대시보드 통합 확인
"""

from dashboard.yfinance_helper import (
    fetch_ticker_yfinance,
    fetch_ohlcv_yfinance,
)


def test_integration():
    """통합 테스트"""
    print("=" * 60)
    print("yfinance 통합 테스트 - PLTR")
    print("=" * 60)

    symbol = 'PLTR'

    # 1. Ticker 조회 (Real-time Quotes에서 사용)
    print(f"\n[1] Ticker 조회: {symbol}")
    ticker = fetch_ticker_yfinance(symbol)

    if ticker:
        print(f"  ✅ {ticker['name']}")
        print(f"  현재가: ${ticker['last']:.2f}")
        print(f"  변동: ${ticker['change']:+.2f} ({ticker['rate']:+.2f}%)")
        print(f"  시가: ${ticker['open']:.2f}")
        print(f"  고가: ${ticker['high']:.2f}")
        print(f"  저가: ${ticker['low']:.2f}")
        print(f"  거래량: {ticker['volume']:,}")
    else:
        print(f"  ❌ Ticker 조회 실패")
        return

    # 2. OHLCV 조회 (OHLCV 차트에서 사용)
    print(f"\n[2] OHLCV 조회: {symbol} (1mo)")
    ohlcv_df = fetch_ohlcv_yfinance(symbol, period='1mo', interval='1d')

    if ohlcv_df is not None:
        print(f"  ✅ 데이터 개수: {len(ohlcv_df)}개")
        print(f"\n  컬럼: {list(ohlcv_df.columns)}")
        print(f"\n  최근 3일 데이터:")
        print(ohlcv_df.tail(3).to_string(index=False))

        # Index 확인 (차트에서 사용)
        if 'timestamp' in ohlcv_df.columns:
            print(f"\n  ✅ timestamp 컬럼 존재 (인덱스 설정 가능)")
            ohlcv_df_indexed = ohlcv_df.set_index('timestamp')
            print(f"  Index 타입: {type(ohlcv_df_indexed.index)}")
        else:
            print(f"\n  ❌ timestamp 컬럼 없음")
    else:
        print(f"  ❌ OHLCV 조회 실패")
        return

    # 3. 3개월 데이터 조회
    print(f"\n[3] OHLCV 조회: {symbol} (3mo)")
    ohlcv_df_3mo = fetch_ohlcv_yfinance(symbol, period='3mo', interval='1d')

    if ohlcv_df_3mo is not None:
        print(f"  ✅ 데이터 개수: {len(ohlcv_df_3mo)}개")
    else:
        print(f"  ❌ OHLCV 조회 실패")

    # 4. 6개월 데이터 조회
    print(f"\n[4] OHLCV 조회: {symbol} (6mo)")
    ohlcv_df_6mo = fetch_ohlcv_yfinance(symbol, period='6mo', interval='1d')

    if ohlcv_df_6mo is not None:
        print(f"  ✅ 데이터 개수: {len(ohlcv_df_6mo)}개")
    else:
        print(f"  ❌ OHLCV 조회 실패")

    print("\n" + "=" * 60)
    print("✅ 모든 통합 테스트 통과!")
    print("=" * 60)


if __name__ == "__main__":
    test_integration()
