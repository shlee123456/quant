"""
한국투자증권 API 테스트
해외주식 시세 조회 기능 확인
"""

import os
from dotenv import load_dotenv
from pykis import PyKis

# .env 파일 로드
load_dotenv()

def test_kis_connection():
    """API 연결 테스트"""
    print("=" * 60)
    print("한국투자증권 API 연결 테스트")
    print("=" * 60)

    # 환경 변수에서 API 키 로드
    user_id = os.getenv('KIS_ID')
    appkey = os.getenv('KIS_APPKEY')
    appsecret = os.getenv('KIS_APPSECRET')
    account = os.getenv('KIS_ACCOUNT')
    mock = os.getenv('KIS_MOCK', 'true').lower() == 'true'

    print(f"\n📌 설정 정보:")
    print(f"   ID: {user_id}")
    print(f"   APPKEY: {appkey[:10]}..." if appkey else "   APPKEY: 없음")
    print(f"   APPSECRET: {appsecret[:10]}..." if appsecret else "   APPSECRET: 없음")
    print(f"   계좌번호: {account}")
    print(f"   모의투자: {mock}")

    if not user_id or not appkey or not appsecret or not account:
        print("\n❌ 오류: .env 파일에 API 키가 설정되지 않았습니다.")
        return None

    try:
        # PyKis 객체 생성
        print(f"\n🔗 한국투자증권 API 연결 중...")
        # PyKis는 실전과 모의투자 설정을 모두 제공해야 함
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
        return kis

    except Exception as e:
        print(f"❌ API 연결 실패: {e}")
        return None


def test_overseas_stock_quote(kis, symbol='AAPL'):
    """해외주식 현재가 조회 테스트"""
    print("\n" + "=" * 60)
    print(f"해외주식 현재가 조회 테스트: {symbol}")
    print("=" * 60)

    try:
        # 해외주식 현재가 조회
        # 미국 주식: 거래소 코드 'NASDAQ'(나스닥) 또는 'NYSE'(뉴욕증권거래소)
        print(f"\n📊 {symbol} 현재가 조회 중...")

        # 해외주식 현재가 조회 (나스닥)
        # PyKis는 stock() 메서드로 주식 객체를 가져옴
        stock = kis.stock(symbol, market='NASDAQ')  # 나스닥
        quote = stock.quote()

        if quote:
            print(f"\n✅ {symbol} 시세 정보:")
            print(f"   현재가: ${quote.price:,.2f}")
            print(f"   전일 대비: {quote.sign} ${quote.change:,.2f} ({quote.rate:+.2f}%)")
            print(f"   시가: ${quote.open:,.2f}")
            print(f"   고가: ${quote.high:,.2f}")
            print(f"   저가: ${quote.low:,.2f}")
            print(f"   거래량: {quote.volume:,}")

            return True
        else:
            print(f"❌ {symbol} 시세 조회 실패")
            return False

    except Exception as e:
        print(f"❌ 시세 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_stocks(kis):
    """여러 종목 시세 조회 테스트"""
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

    return len(results) > 0


def main():
    """메인 테스트 실행"""
    print("\n🚀 한국투자증권 API 테스트 시작\n")

    # 1. API 연결
    kis = test_kis_connection()
    if not kis:
        print("\n⚠️  API 연결에 실패했습니다. 테스트를 종료합니다.")
        return

    # 2. 단일 종목 시세 조회
    success = test_overseas_stock_quote(kis, 'AAPL')

    if success:
        # 3. 여러 종목 시세 조회
        test_multiple_stocks(kis)

    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
