"""
KIS 브로커 연결 테스트

.env 파일의 KIS API 인증 정보를 확인하고 브로커 연결을 테스트합니다.
"""

import os
from dotenv import load_dotenv
from trading_bot.brokers import KoreaInvestmentBroker
from trading_bot.brokers.base_broker import BrokerError, AuthenticationError

# 환경 변수 로드
load_dotenv()

def test_kis_connection():
    """KIS 브로커 연결 테스트"""

    print("=" * 60)
    print("KIS 브로커 연결 테스트")
    print("=" * 60)

    # 1. 환경 변수 확인
    print("\n[1] 환경 변수 확인:")
    appkey = os.getenv('KIS_APPKEY', '')
    appsecret = os.getenv('KIS_APPSECRET', '')
    account = os.getenv('KIS_ACCOUNT', '')
    user_id = os.getenv('KIS_ID', account)
    mock = os.getenv('KIS_MOCK', 'true').lower() == 'true'

    print(f"  - KIS_APPKEY: {'✅ 설정됨' if appkey else '❌ 누락'}")
    print(f"  - KIS_APPSECRET: {'✅ 설정됨' if appsecret else '❌ 누락'}")
    print(f"  - KIS_ACCOUNT: {account if account else '❌ 누락'}")
    print(f"  - KIS_ID: {user_id if user_id else '(KIS_ACCOUNT 값 사용)'}")
    print(f"  - KIS_MOCK: {mock}")

    # 계좌번호 형식 확인
    if account:
        if '-' in account and len(account.split('-')) == 2:
            parts = account.split('-')
            if len(parts[0]) == 8 and len(parts[1]) == 2:
                print(f"  - 계좌번호 형식: ✅ 올바름 ({account})")
            else:
                print(f"  - 계좌번호 형식: ⚠️ 비정상 ({account})")
                print(f"    예상 형식: 12345678-01 (8자리-2자리)")
        else:
            print(f"  - 계좌번호 형식: ❌ 잘못됨 ({account})")
            print(f"    올바른 형식: 12345678-01 (하이픈 필요)")
            return

    if not all([appkey, appsecret, account]):
        print("\n❌ 필수 환경 변수가 누락되었습니다.")
        print("   .env 파일에서 KIS_APPKEY, KIS_APPSECRET, KIS_ACCOUNT를 설정해주세요.")
        return

    # 2. 브로커 초기화
    print("\n[2] 브로커 초기화:")
    try:
        broker = KoreaInvestmentBroker(
            user_id=user_id,
            appkey=appkey,
            appsecret=appsecret,
            account=account,
            mock=mock
        )
        mode = "모의투자" if mock else "실전투자"
        print(f"  ✅ 초기화 성공 ({mode} 모드)")
    except AuthenticationError as e:
        print(f"  ❌ 인증 실패: {e}")
        print("\n해결 방법:")
        print("  1. APPKEY와 APPSECRET이 올바른지 확인하세요.")
        print("  2. 모의투자와 실전투자의 키가 다릅니다. KIS_MOCK 설정을 확인하세요.")
        print("  3. API 키가 만료되었는지 확인하세요.")
        return
    except BrokerError as e:
        print(f"  ❌ 브로커 오류: {e}")
        return
    except Exception as e:
        print(f"  ❌ 예상치 못한 오류: {e}")
        return

    # 3. 해외주식 시세 조회 테스트
    print("\n[3] 해외주식 시세 조회 테스트 (AAPL):")
    try:
        ticker = broker.fetch_ticker('AAPL', overseas=True, market='NASDAQ')
        print(f"  ✅ 시세 조회 성공")
        print(f"    - 현재가: ${ticker['last']:.2f}")
        print(f"    - 시가: ${ticker.get('open', 0):.2f}")
        print(f"    - 고가: ${ticker.get('high', 0):.2f}")
        print(f"    - 저가: ${ticker.get('low', 0):.2f}")
    except Exception as e:
        print(f"  ❌ 시세 조회 실패: {e}")
        return

    # 4. OHLCV 데이터 조회 테스트
    print("\n[4] OHLCV 데이터 조회 테스트 (AAPL, 최근 5일):")
    try:
        df = broker.fetch_ohlcv('AAPL', '1d', limit=5, overseas=True, market='NASDAQ')
        print(f"  ✅ OHLCV 조회 성공")
        print(f"    - 데이터 개수: {len(df)}개")
        print(f"\n  최근 데이터:")
        print(df.tail(3).to_string(index=False))
    except Exception as e:
        print(f"  ❌ OHLCV 조회 실패: {e}")
        return

    print("\n" + "=" * 60)
    print("✅ 모든 테스트 통과!")
    print("=" * 60)


if __name__ == "__main__":
    test_kis_connection()
