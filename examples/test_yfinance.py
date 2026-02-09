"""
yfinance 기능 테스트

PLTR, SHOP 등 다양한 종목 조회 테스트
"""

from dashboard.yfinance_helper import (
    fetch_ticker_yfinance,
    fetch_ohlcv_yfinance,
    get_company_info,
    validate_symbol
)

def test_ticker():
    """시세 조회 테스트"""
    print("=" * 60)
    print("시세 조회 테스트")
    print("=" * 60)

    symbols = ['PLTR', 'SHOP', 'COIN', 'UBER', 'ABNB', 'RBLX']

    for symbol in symbols:
        print(f"\n[{symbol}]")
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
            print(f"  ❌ 조회 실패")


def test_ohlcv():
    """OHLCV 데이터 조회 테스트"""
    print("\n" + "=" * 60)
    print("OHLCV 데이터 조회 테스트 (PLTR, 최근 5일)")
    print("=" * 60)

    df = fetch_ohlcv_yfinance('PLTR', period='5d', interval='1d')

    if df is not None:
        print(f"\n✅ 데이터 개수: {len(df)}개")
        print("\n최근 데이터:")
        print(df.tail().to_string(index=False))
    else:
        print("❌ OHLCV 조회 실패")


def test_company_info():
    """회사 정보 조회 테스트"""
    print("\n" + "=" * 60)
    print("회사 정보 조회 테스트 (PLTR)")
    print("=" * 60)

    info = get_company_info('PLTR')

    if info:
        print(f"\n✅ {info['name']}")
        print(f"  섹터: {info['sector']}")
        print(f"  산업: {info['industry']}")
        print(f"  거래소: {info['exchange']}")
        print(f"  시가총액: ${info['market_cap']:,}")
        print(f"  직원 수: {info['employees']:,}")
        print(f"\n  설명: {info['description'][:200]}...")
    else:
        print("❌ 회사 정보 조회 실패")


def test_validation():
    """심볼 유효성 검증 테스트"""
    print("\n" + "=" * 60)
    print("심볼 유효성 검증 테스트")
    print("=" * 60)

    test_symbols = [
        ('AAPL', True),
        ('PLTR', True),
        ('INVALID123', False),
        ('NOTEXIST', False)
    ]

    for symbol, expected in test_symbols:
        is_valid = validate_symbol(symbol)
        status = "✅" if is_valid == expected else "❌"
        print(f"{status} {symbol}: {'유효' if is_valid else '유효하지 않음'}")


if __name__ == "__main__":
    test_ticker()
    test_ohlcv()
    test_company_info()
    test_validation()

    print("\n" + "=" * 60)
    print("✅ 모든 테스트 완료!")
    print("=" * 60)
