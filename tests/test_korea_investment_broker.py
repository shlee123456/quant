"""
한국투자증권 브로커 단위 테스트

KoreaInvestmentBroker 클래스의 기능을 검증합니다.
"""

import os
import pytest
from dotenv import load_dotenv

from trading_bot.brokers import KoreaInvestmentBroker
from trading_bot.brokers.base_broker import (
    BrokerError,
    AuthenticationError
)

# .env 파일 로드
load_dotenv()


@pytest.fixture
def broker_credentials():
    """테스트용 브로커 인증 정보"""
    return {
        'user_id': os.getenv('KIS_ID'),
        'appkey': os.getenv('KIS_APPKEY'),
        'appsecret': os.getenv('KIS_APPSECRET'),
        'account': os.getenv('KIS_ACCOUNT'),
        'mock': os.getenv('KIS_MOCK', 'true').lower() == 'true'
    }


@pytest.fixture
def broker(broker_credentials):
    """테스트용 브로커 인스턴스"""
    # 환경 변수가 설정되지 않으면 테스트 건너뛰기
    if not all([
        broker_credentials['user_id'],
        broker_credentials['appkey'],
        broker_credentials['appsecret'],
        broker_credentials['account']
    ]):
        pytest.skip("KIS API credentials not set in .env")

    return KoreaInvestmentBroker(**broker_credentials)


class TestKoreaInvestmentBrokerInitialization:
    """브로커 초기화 테스트"""

    def test_broker_initialization_success(self, broker_credentials):
        """정상적인 초기화 테스트"""
        if not all(broker_credentials.values()):
            pytest.skip("KIS API credentials not set")

        broker = KoreaInvestmentBroker(**broker_credentials)
        assert broker is not None
        assert broker.name == 'KoreaInvestment'
        assert broker.market_type == 'stock_global'
        assert broker.api is not None

    def test_broker_attributes(self, broker):
        """브로커 속성 확인"""
        assert hasattr(broker, 'user_id')
        assert hasattr(broker, 'appkey')
        assert hasattr(broker, 'appsecret')
        assert hasattr(broker, 'account')
        assert hasattr(broker, 'mock')
        assert hasattr(broker, 'api')
        assert hasattr(broker, '_rate_limiter')


class TestFetchTicker:
    """현재가 조회 테스트"""

    def test_fetch_ticker_overseas_stock(self, broker):
        """해외주식 현재가 조회 테스트"""
        ticker = broker.fetch_ticker('AAPL', overseas=True, market='NASDAQ')

        assert ticker is not None
        assert 'symbol' in ticker
        assert 'last' in ticker
        assert 'open' in ticker
        assert 'high' in ticker
        assert 'low' in ticker
        assert 'volume' in ticker
        assert 'change' in ticker
        assert 'rate' in ticker
        assert 'timestamp' in ticker

        assert ticker['symbol'] == 'AAPL'
        assert ticker['last'] > 0
        assert ticker['volume'] >= 0

    def test_fetch_ticker_multiple_stocks(self, broker):
        """여러 종목 시세 조회 테스트"""
        symbols = ['AAPL', 'MSFT', 'GOOGL']

        for symbol in symbols:
            ticker = broker.fetch_ticker(symbol, overseas=True, market='NASDAQ')
            assert ticker['symbol'] == symbol
            assert ticker['last'] > 0

    def test_fetch_ticker_invalid_symbol(self, broker):
        """잘못된 종목 코드 테스트"""
        # 존재하지 않는 종목 코드
        with pytest.raises(BrokerError):
            broker.fetch_ticker('INVALID_SYMBOL_XYZ', overseas=True, market='NASDAQ')


class TestFetchOHLCV:
    """OHLCV 데이터 조회 테스트"""

    def test_fetch_ohlcv_overseas_stock(self, broker):
        """해외주식 OHLCV 조회 테스트"""
        df = broker.fetch_ohlcv('AAPL', '1d', limit=10, overseas=True, market='NASDAQ')

        assert df is not None
        assert not df.empty
        assert len(df) <= 10

        # 필수 컬럼 확인
        required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            assert col in df.columns

        # 데이터 타입 확인
        assert df['open'].dtype == float
        assert df['high'].dtype == float
        assert df['low'].dtype == float
        assert df['close'].dtype == float
        assert df['volume'].dtype == float

        # OHLC 로직 확인
        assert (df['high'] >= df['low']).all()
        assert (df['high'] >= df['close']).all()
        assert (df['low'] <= df['close']).all()

    def test_fetch_ohlcv_different_limits(self, broker):
        """다양한 limit 값 테스트"""
        limits = [5, 10, 20, 50]

        for limit in limits:
            df = broker.fetch_ohlcv('MSFT', '1d', limit=limit, overseas=True, market='NASDAQ')
            assert len(df) <= limit

    def test_fetch_ohlcv_invalid_symbol(self, broker):
        """잘못된 종목 코드 테스트"""
        with pytest.raises(BrokerError):
            broker.fetch_ohlcv('INVALID_SYMBOL', '1d', limit=10, overseas=True)


class TestFetchBalance:
    """잔고 조회 테스트"""

    def test_fetch_balance_structure(self, broker):
        """잔고 조회 구조 테스트"""
        balance = broker.fetch_balance()

        assert balance is not None
        assert 'free' in balance
        assert 'used' in balance
        assert 'total' in balance

        assert 'KRW' in balance['free']
        assert 'KRW' in balance['used']
        assert 'KRW' in balance['total']

    def test_fetch_balance_values(self, broker):
        """잔고 값 검증"""
        balance = broker.fetch_balance()

        # 값이 숫자인지 확인
        assert isinstance(balance['free']['KRW'], (int, float))
        assert isinstance(balance['used']['KRW'], (int, float))
        assert isinstance(balance['total']['KRW'], (int, float))

        # 값이 음수가 아닌지 확인
        assert balance['free']['KRW'] >= 0
        assert balance['used']['KRW'] >= 0
        assert balance['total']['KRW'] >= 0


class TestRateLimiter:
    """Rate Limiter 테스트"""

    def test_rate_limiter_exists(self, broker):
        """Rate Limiter가 존재하는지 확인"""
        assert hasattr(broker, '_rate_limiter')
        assert broker._rate_limiter is not None

    def test_rate_limiter_attributes(self, broker):
        """Rate Limiter 속성 확인"""
        limiter = broker._rate_limiter
        assert hasattr(limiter, 'max_calls')
        assert hasattr(limiter, 'period')
        assert limiter.max_calls == 15
        assert limiter.period == 1.0


# 주문 관련 테스트는 실제 거래가 발생하므로 신중하게 수행
# 모의투자 환경에서만 실행되도록 설정
@pytest.mark.skipif(
    os.getenv('KIS_MOCK', 'true').lower() != 'true',
    reason="Order tests only run in mock mode"
)
class TestOrders:
    """주문 관련 테스트 (모의투자 전용)"""

    @pytest.mark.skip(reason="실제 주문 테스트는 수동으로 실행")
    def test_create_order_market_buy(self, broker):
        """시장가 매수 주문 테스트"""
        # 실제 주문을 생성하므로 주의!
        order = broker.create_order(
            symbol='AAPL',
            order_type='market',
            side='buy',
            amount=1,
            overseas=True,
            market='NASDAQ'
        )

        assert order is not None
        assert 'id' in order
        assert 'symbol' in order
        assert order['symbol'] == 'AAPL'
        assert order['type'] == 'market'
        assert order['side'] == 'buy'

    @pytest.mark.skip(reason="실제 주문 테스트는 수동으로 실행")
    def test_create_order_limit_buy(self, broker):
        """지정가 매수 주문 테스트"""
        order = broker.create_order(
            symbol='AAPL',
            order_type='limit',
            side='buy',
            amount=1,
            price=100.0,  # 낮은 가격으로 설정 (체결 방지)
            overseas=True,
            market='NASDAQ'
        )

        assert order is not None
        assert order['type'] == 'limit'
        assert order['price'] == 100.0


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
