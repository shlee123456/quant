"""
Broker Tests

브로커 모듈의 통합 테스트입니다.
각 브로커의 기본 기능을 테스트합니다.

Note:
    실제 API 호출 없이 Mock을 사용하여 테스트합니다.
    실제 API 테스트는 별도의 integration test에서 수행합니다.
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from trading_bot.brokers import (
    BaseBroker,
    CCXTBroker,
    KoreaInvestmentBroker,
    BrokerError,
    AuthenticationError,
    InsufficientFunds,
    OrderNotFound,
    RateLimitExceeded
)


# ==================== BaseBroker Tests ====================

class ConcreteBroker(BaseBroker):
    """테스트용 구체 브로커 클래스"""

    def __init__(self):
        super().__init__(name='TestBroker', market_type='test')

    def fetch_ohlcv(self, symbol, timeframe='1d', since=None, limit=100):
        return pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=limit, freq='1D'),
            'open': [100] * limit,
            'high': [110] * limit,
            'low': [90] * limit,
            'close': [105] * limit,
            'volume': [1000] * limit
        })

    def fetch_balance(self):
        return {
            'free': {'KRW': 1000000},
            'used': {'KRW': 0},
            'total': {'KRW': 1000000}
        }

    def create_order(self, symbol, order_type, side, amount, price=None):
        return {
            'id': '12345',
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'amount': amount,
            'price': price,
            'status': 'open',
            'timestamp': int(datetime.now().timestamp() * 1000)
        }

    def cancel_order(self, order_id, symbol=None):
        return {
            'id': order_id,
            'status': 'canceled'
        }

    def fetch_ticker(self, symbol):
        return {
            'symbol': symbol,
            'last': 100.0,
            'bid': 99.0,
            'ask': 101.0,
            'high': 110.0,
            'low': 90.0,
            'volume': 1000.0,
            'timestamp': int(datetime.now().timestamp() * 1000)
        }

    def fetch_order(self, order_id, symbol=None):
        return {
            'id': order_id,
            'symbol': symbol,
            'status': 'closed',
            'amount': 10,
            'price': 100.0
        }


def test_base_broker_interface():
    """BaseBroker 인터페이스 테스트"""
    broker = ConcreteBroker()

    assert broker.name == 'TestBroker'
    assert broker.market_type == 'test'

    # fetch_ohlcv
    df = broker.fetch_ohlcv('TEST', '1d', limit=10)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 10
    assert 'close' in df.columns

    # fetch_balance
    balance = broker.fetch_balance()
    assert 'total' in balance
    assert balance['total']['KRW'] == 1000000

    # create_order
    order = broker.create_order('TEST', 'market', 'buy', 10)
    assert order['id'] == '12345'
    assert order['status'] == 'open'

    # cancel_order
    result = broker.cancel_order('12345')
    assert result['status'] == 'canceled'

    # fetch_ticker
    ticker = broker.fetch_ticker('TEST')
    assert ticker['last'] == 100.0

    # fetch_order
    order = broker.fetch_order('12345', 'TEST')
    assert order['status'] == 'closed'


def test_base_broker_optional_methods():
    """BaseBroker 선택 메서드 테스트"""
    broker = ConcreteBroker()

    # fetch_open_orders - 기본 구현은 NotImplementedError 발생
    with pytest.raises(NotImplementedError):
        broker.fetch_open_orders('TEST')

    # fetch_closed_orders - 기본 구현은 NotImplementedError 발생
    with pytest.raises(NotImplementedError):
        broker.fetch_closed_orders('TEST')


def test_base_broker_repr():
    """BaseBroker __repr__ 테스트"""
    broker = ConcreteBroker()
    repr_str = repr(broker)
    assert 'ConcreteBroker' in repr_str
    assert 'TestBroker' in repr_str
    assert 'test' in repr_str


# ==================== Exception Tests ====================

def test_broker_exceptions():
    """브로커 예외 클래스 테스트"""

    # BrokerError
    with pytest.raises(BrokerError):
        raise BrokerError("Test error")

    # AuthenticationError
    with pytest.raises(AuthenticationError):
        raise AuthenticationError("Auth failed")

    # InsufficientFunds
    with pytest.raises(InsufficientFunds):
        raise InsufficientFunds("Not enough balance")

    # OrderNotFound
    with pytest.raises(OrderNotFound):
        raise OrderNotFound("Order not found")

    # RateLimitExceeded
    with pytest.raises(RateLimitExceeded):
        raise RateLimitExceeded("Rate limit exceeded")


def test_exception_inheritance():
    """예외 클래스 상속 관계 테스트"""
    assert issubclass(AuthenticationError, BrokerError)
    assert issubclass(InsufficientFunds, BrokerError)
    assert issubclass(OrderNotFound, BrokerError)
    assert issubclass(RateLimitExceeded, BrokerError)


# ==================== CCXTBroker Tests ====================

@patch('trading_bot.brokers.ccxt_broker.ccxt')
def test_ccxt_broker_init(mock_ccxt):
    """CCXTBroker 초기화 테스트"""
    mock_exchange_class = Mock()
    mock_exchange = Mock()
    mock_exchange_class.return_value = mock_exchange
    mock_ccxt.binance = mock_exchange_class

    broker = CCXTBroker('binance', api_key='KEY', secret='SECRET')

    assert broker.name == 'CCXT-binance'
    assert broker.market_type == 'crypto'
    assert broker.exchange_id == 'binance'
    mock_exchange_class.assert_called_once()


@patch('trading_bot.brokers.ccxt_broker.ccxt')
def test_ccxt_broker_fetch_ohlcv(mock_ccxt):
    """CCXTBroker fetch_ohlcv 테스트"""
    mock_exchange_class = Mock()
    mock_exchange = Mock()
    mock_exchange.fetch_ohlcv.return_value = [
        [1609459200000, 29000, 29500, 28500, 29200, 1000],
        [1609545600000, 29200, 29800, 29000, 29500, 1100]
    ]
    mock_exchange_class.return_value = mock_exchange
    mock_ccxt.binance = mock_exchange_class

    broker = CCXTBroker('binance')
    df = broker.fetch_ohlcv('BTC/USDT', '1h', limit=2)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert df.iloc[0]['close'] == 29200
    assert df.iloc[1]['close'] == 29500
    mock_exchange.fetch_ohlcv.assert_called_once()


@patch('trading_bot.brokers.ccxt_broker.ccxt')
def test_ccxt_broker_fetch_balance(mock_ccxt):
    """CCXTBroker fetch_balance 테스트"""
    mock_exchange_class = Mock()
    mock_exchange = Mock()
    mock_exchange.fetch_balance.return_value = {
        'free': {'USDT': 10000},
        'used': {'USDT': 0},
        'total': {'USDT': 10000}
    }
    mock_exchange_class.return_value = mock_exchange
    mock_ccxt.binance = mock_exchange_class

    broker = CCXTBroker('binance', api_key='KEY', secret='SECRET')
    balance = broker.fetch_balance()

    assert balance['total']['USDT'] == 10000
    mock_exchange.fetch_balance.assert_called_once()


@patch('trading_bot.brokers.ccxt_broker.ccxt')
def test_ccxt_broker_create_order(mock_ccxt):
    """CCXTBroker create_order 테스트"""
    mock_exchange_class = Mock()
    mock_exchange = Mock()
    mock_exchange.create_order.return_value = {
        'id': '12345',
        'symbol': 'BTC/USDT',
        'type': 'limit',
        'side': 'buy',
        'amount': 1.0,
        'price': 42000,
        'status': 'open'
    }
    mock_exchange_class.return_value = mock_exchange
    mock_ccxt.binance = mock_exchange_class

    broker = CCXTBroker('binance', api_key='KEY', secret='SECRET')
    order = broker.create_order('BTC/USDT', 'limit', 'buy', 1.0, 42000)

    assert order['id'] == '12345'
    assert order['status'] == 'open'
    mock_exchange.create_order.assert_called_once()


@patch('trading_bot.brokers.ccxt_broker.ccxt')
def test_ccxt_broker_error_handling(mock_ccxt):
    """CCXTBroker 에러 처리 테스트"""
    mock_exchange_class = Mock()
    mock_exchange = Mock()
    mock_exchange_class.return_value = mock_exchange
    mock_ccxt.binance = mock_exchange_class
    mock_ccxt.InsufficientFunds = Exception

    # InsufficientFunds 에러
    mock_exchange.create_order.side_effect = mock_ccxt.InsufficientFunds("Not enough funds")

    broker = CCXTBroker('binance', api_key='KEY', secret='SECRET')

    with pytest.raises(InsufficientFunds):
        broker.create_order('BTC/USDT', 'market', 'buy', 10.0)


# ==================== KoreaInvestmentBroker Tests ====================

@patch('pykis.PyKis')
def test_korea_investment_broker_init(mock_pykis):
    """KoreaInvestmentBroker 초기화 테스트"""
    # Mock PyKis
    mock_api = Mock()
    mock_pykis.return_value = mock_api

    broker = KoreaInvestmentBroker(
        appkey='TEST_APPKEY' * 3,  # 36자
        appsecret='TEST_APPSECRET',
        account='12345678-01'
    )

    assert broker.name == 'KoreaInvestment'
    assert broker.market_type == 'stock_global'
    assert broker.appkey == 'TEST_APPKEY' * 3
    assert broker.appsecret == 'TEST_APPSECRET'
    assert broker.account == '12345678-01'
    assert broker.user_id == '12345678-01'  # user_id defaults to account
    assert broker.mock is False


@patch('pykis.PyKis')
def test_korea_investment_broker_with_user_id(mock_pykis):
    """KoreaInvestmentBroker user_id 명시 테스트"""
    # Mock PyKis
    mock_api = Mock()
    mock_pykis.return_value = mock_api

    broker = KoreaInvestmentBroker(
        appkey='TEST_APPKEY' * 3,  # 36자
        appsecret='TEST_APPSECRET',
        account='12345678-01',
        user_id='@test_user'
    )

    assert broker.user_id == '@test_user'  # user_id explicitly set
    assert broker.account == '12345678-01'


@patch('pykis.PyKis')
def test_korea_investment_broker_mock_mode(mock_pykis):
    """KoreaInvestmentBroker 모의투자 모드 테스트"""
    # Mock PyKis
    mock_api = Mock()
    mock_pykis.return_value = mock_api

    broker = KoreaInvestmentBroker(
        appkey='TEST_APPKEY' * 3,  # 36자
        appsecret='TEST_APPSECRET',
        account='12345678-01',
        mock=True
    )

    assert broker.mock is True


@patch('pykis.PyKis')
def test_korea_investment_broker_methods_available(mock_pykis):
    """KoreaInvestmentBroker 메서드 사용 가능 테스트"""
    # Mock PyKis
    mock_api = Mock()
    mock_pykis.return_value = mock_api

    broker = KoreaInvestmentBroker(
        appkey='TEST_APPKEY' * 3,  # 36자
        appsecret='TEST_APPSECRET',
        account='12345678-01'
    )

    # 메서드들이 존재하는지 확인 (구현 여부와 관계없이)
    assert hasattr(broker, 'fetch_ohlcv')
    assert hasattr(broker, 'fetch_balance')
    assert hasattr(broker, 'create_order')
    assert hasattr(broker, 'fetch_ticker')


# ==================== RateLimiter Tests ====================

def test_rate_limiter():
    """RateLimiter 테스트"""
    from trading_bot.brokers.korea_investment_broker import RateLimiter
    import time

    limiter = RateLimiter(max_calls=3, period=1.0)

    # 3회 호출 (제한 내)
    start = time.time()
    for _ in range(3):
        limiter.wait()
    elapsed = time.time() - start
    assert elapsed < 0.1  # 거의 즉시

    # 4번째 호출 (제한 초과, 대기 필요)
    start = time.time()
    limiter.wait()
    elapsed = time.time() - start
    assert elapsed >= 0.9  # 약 1초 대기


# ==================== Integration Tests (Placeholder) ====================

def test_broker_integration_placeholder():
    """
    브로커 통합 테스트 (Placeholder).

    실제 API를 사용한 통합 테스트는 별도의 integration test에서 수행합니다.
    여기서는 Mock을 사용한 기본 테스트만 수행합니다.
    """
    # TODO: 실제 API 사용 통합 테스트 추가
    # - 실제 CCXT API로 시세 조회
    # - 한국투자증권 모의투자 API로 주문 테스트
    pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
