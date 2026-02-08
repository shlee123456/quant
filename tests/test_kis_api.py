"""
한국투자증권 API 테스트

해외주식 시세 조회 기능 확인
"""

import pytest


class TestKISConnection:
    """한국투자증권 API 연결 테스트"""

    def test_kis_connection(self, kis):
        """API 연결 테스트"""
        # kis fixture가 성공적으로 생성되었는지 확인
        assert kis is not None
        assert hasattr(kis, 'stock')


class TestOverseasStockQuote:
    """해외주식 현재가 조회 테스트"""

    def test_overseas_stock_quote(self, kis):
        """해외주식 현재가 조회 테스트 - AAPL"""
        symbol = 'AAPL'

        # 해외주식 현재가 조회 (나스닥)
        stock = kis.stock(symbol, market='NASDAQ')
        quote = stock.quote()

        # 시세 정보 검증
        assert quote is not None
        assert hasattr(quote, 'price')
        assert hasattr(quote, 'change')
        assert hasattr(quote, 'rate')
        assert hasattr(quote, 'open')
        assert hasattr(quote, 'high')
        assert hasattr(quote, 'low')
        assert hasattr(quote, 'volume')

        # 가격 정보가 유효한지 확인
        assert quote.price > 0
        assert quote.open > 0
        assert quote.high > 0
        assert quote.low > 0
        assert quote.volume >= 0

    def test_multiple_stocks(self, kis):
        """여러 종목 시세 조회 테스트"""
        symbols = ['AAPL', 'TSLA', 'MSFT']  # 3개만 테스트 (속도 고려)

        results = []
        for symbol in symbols:
            stock = kis.stock(symbol, market='NASDAQ')
            quote = stock.quote()

            assert quote is not None
            assert quote.price > 0

            results.append({
                'symbol': symbol,
                'price': quote.price,
                'change': quote.change,
                'rate': quote.rate
            })

        # 모든 종목 조회 성공 확인
        assert len(results) == len(symbols)


# 수동 실행용 메인 함수 (pytest 외부에서 실행 가능)
def main():
    """메인 테스트 실행 (수동 테스트용)"""
    import os
    from dotenv import load_dotenv
    from pykis import PyKis

    load_dotenv()

    print("\n🚀 한국투자증권 API 테스트 시작\n")

    # 환경 변수 로드
    user_id = os.getenv('KIS_ID')
    appkey = os.getenv('KIS_APPKEY')
    appsecret = os.getenv('KIS_APPSECRET')
    account = os.getenv('KIS_ACCOUNT')

    print(f"📌 설정 정보:")
    print(f"   ID: {user_id}")
    print(f"   APPKEY: {appkey[:10]}..." if appkey else "   APPKEY: 없음")
    print(f"   APPSECRET: {appsecret[:10]}..." if appsecret else "   APPSECRET: 없음")
    print(f"   계좌번호: {account}")

    if not all([user_id, appkey, appsecret, account]):
        print("\n❌ 오류: .env 파일에 API 키가 설정되지 않았습니다.")
        return

    try:
        # PyKis 객체 생성
        print(f"\n🔗 한국투자증권 API 연결 중...")
        kis = PyKis(
            id=user_id,
            appkey=appkey,
            secretkey=appsecret,
            virtual_id=user_id,
            virtual_appkey=appkey,
            virtual_secretkey=appsecret,
            account=account
        )
        print("✅ API 연결 성공!")

        # 단일 종목 시세 조회
        print("\n" + "=" * 60)
        print("해외주식 현재가 조회 테스트: AAPL")
        print("=" * 60)

        stock = kis.stock('AAPL', market='NASDAQ')
        quote = stock.quote()

        if quote:
            print(f"\n✅ AAPL 시세 정보:")
            print(f"   현재가: ${quote.price:,.2f}")
            print(f"   전일 대비: {quote.sign} ${quote.change:,.2f} ({quote.rate:+.2f}%)")
            print(f"   시가: ${quote.open:,.2f}")
            print(f"   고가: ${quote.high:,.2f}")
            print(f"   저가: ${quote.low:,.2f}")
            print(f"   거래량: {quote.volume:,}")

        # 여러 종목 시세 조회
        print("\n" + "=" * 60)
        print("인기 종목 시세 조회 테스트")
        print("=" * 60)

        symbols = ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'NVDA']
        results = []

        for symbol in symbols:
            try:
                print(f"\n📊 {symbol} 조회 중...")
                stock = kis.stock(symbol, market='NASDAQ')
                quote = stock.quote()

                if quote:
                    results.append({
                        'symbol': symbol,
                        'price': quote.price,
                        'change': quote.change,
                        'rate': quote.rate
                    })
                    print(f"   ${quote.price:,.2f} ({quote.rate:+.2f}%)")

            except Exception as e:
                print(f"   ❌ 오류: {e}")

        # 결과 요약
        if results:
            print("\n" + "=" * 60)
            print("📈 조회 결과 요약")
            print("=" * 60)
            print(f"{'종목':<10} {'현재가':>12} {'등락률':>10}")
            print("-" * 60)
            for r in results:
                print(f"{r['symbol']:<10} ${r['price']:>10,.2f} {r['rate']:>9.2f}%")
            print("=" * 60)

        print("\n" + "=" * 60)
        print("✅ 테스트 완료!")
        print("=" * 60)

    except Exception as e:
        print(f"❌ API 연결 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
