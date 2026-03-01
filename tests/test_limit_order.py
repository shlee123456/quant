"""
Unit and integration tests for the Limit Order System

Tests:
- PendingOrder dataclass
- LimitOrderManager CRUD
- Paper trading fill simulation
- Chain order creation
- Expiration handling
- DB persistence
- PaperTrader integration
"""

import pytest
import os
import tempfile
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import MagicMock

import pandas as pd

from trading_bot.limit_order import LimitOrderManager, PendingOrder
from trading_bot.database import TradingDatabase
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy


# ---- Fixtures ----

@pytest.fixture
def lock():
    return threading.RLock()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_limit_order.db')
    db = TradingDatabase(db_path=db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)
    # Remove WAL/SHM files if they exist
    for suffix in ('-wal', '-shm'):
        wal_path = db_path + suffix
        if os.path.exists(wal_path):
            os.remove(wal_path)
    os.rmdir(temp_dir)


@pytest.fixture
def manager(lock):
    """LimitOrderManager without DB"""
    return LimitOrderManager(db=None, lock=lock)


@pytest.fixture
def manager_with_db(temp_db, lock):
    """LimitOrderManager with DB"""
    return LimitOrderManager(db=temp_db, lock=lock)


@pytest.fixture
def session_id(temp_db):
    """Create a test session and return its ID"""
    return temp_db.create_session(
        strategy_name='RSI_14_30_70',
        initial_capital=10000.0,
        display_name='Test Session'
    )


class MockBroker:
    """Mock broker for PaperTrader testing"""

    def __init__(self, ticker_data=None, ohlcv_data=None):
        self._ticker_data = ticker_data or {
            'last': 150.0, 'high': 152.0, 'low': 148.0,
            'open': 149.0, 'volume': 1000000
        }
        self._ohlcv_data = ohlcv_data

    def fetch_ticker(self, symbol, **kwargs):
        return {**self._ticker_data, 'symbol': symbol}

    def fetch_ohlcv(self, symbol, timeframe='1d', limit=100, **kwargs):
        if self._ohlcv_data is not None:
            return self._ohlcv_data
        dates = pd.date_range(end=datetime.now(), periods=limit, freq='D')
        return pd.DataFrame({
            'open': [150.0] * limit,
            'high': [152.0] * limit,
            'low': [148.0] * limit,
            'close': [150.0 + i * 0.5 for i in range(limit)],
            'volume': [1000000] * limit
        }, index=dates)


# ---- PendingOrder Tests ----

class TestPendingOrder:

    def test_creation(self):
        """PendingOrder 생성 테스트"""
        order = PendingOrder(
            order_id='test-id',
            session_id='session-1',
            symbol='NVDA',
            side='buy',
            limit_price=172.0,
            amount=5000.0,
        )
        assert order.order_id == 'test-id'
        assert order.symbol == 'NVDA'
        assert order.side == 'buy'
        assert order.limit_price == 172.0
        assert order.amount == 5000.0
        assert order.status == 'pending'
        assert order.source == 'manual'
        assert order.trigger_order is None
        assert order.filled_at is None

    def test_to_db_dict(self):
        """to_db_dict 직렬화 테스트"""
        now = datetime.now()
        order = PendingOrder(
            order_id='test-id',
            session_id='session-1',
            symbol='NVDA',
            side='buy',
            limit_price=172.0,
            amount=5000.0,
            created_at=now,
            trigger_order={'side': 'sell', 'price': 190.0},
        )
        db_dict = order.to_db_dict()

        assert db_dict['order_id'] == 'test-id'
        assert db_dict['created_at'] == now.isoformat()
        assert db_dict['trigger_order'] == '{"side": "sell", "price": 190.0}'
        assert db_dict['filled_at'] is None

    def test_from_db_row(self):
        """from_db_row 역직렬화 테스트"""
        now = datetime.now()
        row = {
            'order_id': 'test-id',
            'session_id': 'session-1',
            'symbol': 'NVDA',
            'side': 'buy',
            'limit_price': 172.0,
            'amount': 5000.0,
            'status': 'pending',
            'created_at': now.isoformat(),
            'filled_at': None,
            'fill_price': None,
            'expires_at': None,
            'trigger_order': '{"side": "sell", "price": 190.0}',
            'broker_order_id': None,
            'source': 'preset',
        }
        order = PendingOrder.from_db_row(row)

        assert order.order_id == 'test-id'
        assert order.symbol == 'NVDA'
        assert order.trigger_order == {'side': 'sell', 'price': 190.0}
        assert order.source == 'preset'
        assert isinstance(order.created_at, datetime)

    def test_roundtrip_serialization(self):
        """to_db_dict -> from_db_row 라운드트립 테스트"""
        original = PendingOrder(
            order_id='roundtrip-id',
            session_id='session-1',
            symbol='AAPL',
            side='sell',
            limit_price=190.0,
            amount=10.5,
            trigger_order={'side': 'buy', 'price': 170.0},
            source='chained',
        )
        db_dict = original.to_db_dict()
        restored = PendingOrder.from_db_row(db_dict)

        assert restored.order_id == original.order_id
        assert restored.symbol == original.symbol
        assert restored.side == original.side
        assert restored.limit_price == original.limit_price
        assert restored.amount == original.amount
        assert restored.trigger_order == original.trigger_order
        assert restored.source == original.source


# ---- LimitOrderManager Unit Tests ----

class TestLimitOrderManagerCreation:

    def test_create_buy_order(self, manager):
        """매수 지정가 주문 생성"""
        order = manager.create_limit_order(
            session_id='session-1',
            symbol='NVDA',
            side='buy',
            limit_price=172.0,
            amount=5000.0,
        )
        assert order.side == 'buy'
        assert order.limit_price == 172.0
        assert order.status == 'pending'
        assert len(order.order_id) == 36  # UUID format

    def test_create_sell_order(self, manager):
        """매도 지정가 주문 생성"""
        order = manager.create_limit_order(
            session_id='session-1',
            symbol='NVDA',
            side='sell',
            limit_price=190.0,
            amount=29.07,
        )
        assert order.side == 'sell'
        assert order.limit_price == 190.0

    def test_create_order_with_trigger(self, manager):
        """트리거(체인) 주문 포함 생성"""
        trigger = {'side': 'sell', 'price': 190.0}
        order = manager.create_limit_order(
            session_id='session-1',
            symbol='NVDA',
            side='buy',
            limit_price=172.0,
            amount=5000.0,
            trigger_order=trigger,
        )
        assert order.trigger_order == trigger

    def test_create_order_with_expiry(self, manager):
        """만료 시간 포함 생성"""
        expires = datetime.now() + timedelta(hours=24)
        order = manager.create_limit_order(
            session_id='session-1',
            symbol='NVDA',
            side='buy',
            limit_price=172.0,
            amount=5000.0,
            expires_at=expires,
        )
        assert order.expires_at == expires

    def test_invalid_side_raises(self, manager):
        """잘못된 side 값 검증"""
        with pytest.raises(ValueError, match="Invalid side"):
            manager.create_limit_order(
                session_id='s', symbol='X', side='invalid',
                limit_price=100.0, amount=100.0,
            )

    def test_invalid_price_raises(self, manager):
        """0 이하 가격 검증"""
        with pytest.raises(ValueError, match="Invalid limit_price"):
            manager.create_limit_order(
                session_id='s', symbol='X', side='buy',
                limit_price=-1.0, amount=100.0,
            )

    def test_invalid_amount_raises(self, manager):
        """0 이하 금액 검증"""
        with pytest.raises(ValueError, match="Invalid amount"):
            manager.create_limit_order(
                session_id='s', symbol='X', side='buy',
                limit_price=100.0, amount=0,
            )


class TestLimitOrderManagerCancel:

    def test_cancel_pending_order(self, manager):
        """대기 주문 취소"""
        order = manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )
        result = manager.cancel_order(order.order_id)
        assert result is True
        assert order.status == 'canceled'

    def test_cancel_nonexistent_order(self, manager):
        """존재하지 않는 주문 취소 실패"""
        result = manager.cancel_order('nonexistent-id')
        assert result is False

    def test_cancel_already_filled_order(self, manager):
        """이미 체결된 주문은 취소 불가"""
        order = manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )
        order.status = 'filled'
        result = manager.cancel_order(order.order_id)
        assert result is False

    def test_cancel_all(self, manager):
        """세션 전체 주문 취소"""
        manager.create_limit_order(
            session_id='session-1', symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
        )
        manager.create_limit_order(
            session_id='session-1', symbol='MSFT', side='buy',
            limit_price=400.0, amount=2000.0,
        )
        manager.create_limit_order(
            session_id='session-2', symbol='GOOGL', side='buy',
            limit_price=140.0, amount=1000.0,
        )

        canceled = manager.cancel_all('session-1')
        assert canceled == 2

        # session-2 orders should remain
        pending = manager.get_pending_orders(session_id='session-2')
        assert len(pending) == 1


class TestLimitOrderManagerQuery:

    def test_get_pending_orders_by_session(self, manager):
        """세션별 대기 주문 조회"""
        manager.create_limit_order(
            session_id='session-1', symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
        )
        manager.create_limit_order(
            session_id='session-2', symbol='MSFT', side='buy',
            limit_price=400.0, amount=2000.0,
        )

        result = manager.get_pending_orders(session_id='session-1')
        assert len(result) == 1
        assert result[0].symbol == 'AAPL'

    def test_get_pending_orders_by_symbol(self, manager):
        """심볼별 대기 주문 조회"""
        manager.create_limit_order(
            session_id='session-1', symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
        )
        manager.create_limit_order(
            session_id='session-1', symbol='MSFT', side='buy',
            limit_price=400.0, amount=2000.0,
        )

        result = manager.get_pending_orders(symbol='MSFT')
        assert len(result) == 1
        assert result[0].symbol == 'MSFT'

    def test_get_pending_orders_excludes_filled(self, manager):
        """체결된 주문은 대기 조회에서 제외"""
        order = manager.create_limit_order(
            session_id='session-1', symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
        )
        order.status = 'filled'

        result = manager.get_pending_orders(session_id='session-1')
        assert len(result) == 0

    def test_get_all_orders(self, manager):
        """모든 주문 조회 (상태 무관)"""
        o1 = manager.create_limit_order(
            session_id='session-1', symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
        )
        o2 = manager.create_limit_order(
            session_id='session-1', symbol='MSFT', side='buy',
            limit_price=400.0, amount=2000.0,
        )
        o1.status = 'filled'

        result = manager.get_all_orders(session_id='session-1')
        assert len(result) == 2


# ---- Paper Fill Tests ----

class TestPaperFill:

    def _make_callbacks(self):
        """Helper to create buy/sell callback mocks"""
        buys = []
        sells = []

        def buy_fn(symbol, price, timestamp, **kwargs):
            buys.append({'symbol': symbol, 'price': price, 'timestamp': timestamp})

        def sell_fn(symbol, price, timestamp, reason=''):
            sells.append({'symbol': symbol, 'price': price, 'timestamp': timestamp, 'reason': reason})

        return buy_fn, sell_fn, buys, sells

    def test_buy_limit_fill_when_low_reaches_price(self, manager):
        """매수 지정가: low <= limit_price -> 체결"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 171.0, 'high': 175.0, 'low': 170.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 1
        assert filled[0].status == 'filled'
        assert filled[0].fill_price == 172.0
        assert len(buys) == 1
        assert buys[0]['price'] == 172.0

    def test_buy_limit_no_fill_when_low_above_price(self, manager):
        """매수 지정가: low > limit_price -> 미체결"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 175.0, 'high': 178.0, 'low': 173.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 0
        assert len(buys) == 0

    def test_sell_limit_fill_when_high_reaches_price(self, manager):
        """매도 지정가: high >= limit_price -> 체결"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='sell',
            limit_price=190.0, amount=29.0,
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 191.0, 'high': 192.0, 'low': 189.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 1
        assert filled[0].fill_price == 190.0
        assert len(sells) == 1
        assert sells[0]['price'] == 190.0
        assert sells[0]['reason'] == 'limit_order'

    def test_sell_limit_no_fill_when_high_below_price(self, manager):
        """매도 지정가: high < limit_price -> 미체결"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='sell',
            limit_price=190.0, amount=29.0,
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 185.0, 'high': 188.0, 'low': 183.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 0
        assert len(sells) == 0

    def test_exact_price_match_fills(self, manager):
        """정확히 지정가와 일치하는 경우 체결"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 172.5, 'high': 175.0, 'low': 172.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 1
        assert filled[0].fill_price == 172.0

    def test_multiple_orders_same_symbol(self, manager):
        """동일 심볼 다수 주문 개별 체결"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=3000.0,
        )
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=168.0, amount=2000.0,
        )

        # low=170 -> 172 fills, 168 does not
        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 171.0, 'high': 175.0, 'low': 170.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 1
        assert filled[0].limit_price == 172.0
        assert len(buys) == 1

    def test_only_matching_symbol_checked(self, manager):
        """다른 심볼 주문은 체크하지 않음"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 140.0, 'high': 145.0, 'low': 135.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 0


# ---- Chain Order Tests ----

class TestChainOrders:

    def _make_callbacks(self):
        buys = []
        sells = []

        def buy_fn(symbol, price, timestamp, **kwargs):
            buys.append({'symbol': symbol, 'price': price})

        def sell_fn(symbol, price, timestamp, reason=''):
            sells.append({'symbol': symbol, 'price': price})

        return buy_fn, sell_fn, buys, sells

    def test_buy_fill_creates_sell_chain(self, manager):
        """매수 체결 후 매도 체인 주문 자동 생성"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            trigger_order={'side': 'sell', 'price': 190.0},
        )

        manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 169.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        # Check chain order was created
        pending = manager.get_pending_orders(session_id='session-1')
        assert len(pending) == 1
        assert pending[0].side == 'sell'
        assert pending[0].limit_price == 190.0
        assert pending[0].source == 'chained'

    def test_chain_order_amount_calculation(self, manager):
        """체인 주문 금액 계산: buy->sell은 수량 (amount/price)"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            trigger_order={'side': 'sell', 'price': 190.0},
        )

        manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 169.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        pending = manager.get_pending_orders(session_id='session-1')
        # Chain sell amount = original_amount / buy_price = 5000 / 172 ≈ 29.07
        expected_amount = 5000.0 / 172.0
        assert abs(pending[0].amount - expected_amount) < 0.01

    def test_full_chain_buy_then_sell(self, manager):
        """전체 체인 흐름: buy -> fill -> chain sell -> fill"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()

        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            trigger_order={'side': 'sell', 'price': 190.0},
        )

        # Step 1: Buy fills
        manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 169.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )
        assert len(buys) == 1

        # Step 2: Chain sell fills
        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 191.0, 'high': 192.0, 'low': 189.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )
        assert len(filled) == 1
        assert filled[0].side == 'sell'
        assert filled[0].fill_price == 190.0
        assert len(sells) == 1

        # No more pending orders
        pending = manager.get_pending_orders(session_id='session-1')
        assert len(pending) == 0


# ---- Expiration Tests ----

class TestExpiration:

    def _make_callbacks(self):
        buys = []
        sells = []
        return (
            lambda s, p, t, **kw: buys.append(1),
            lambda s, p, t, reason='': sells.append(1),
            buys, sells,
        )

    def test_expired_order_not_filled(self, manager):
        """만료된 주문은 체결되지 않음"""
        buy_fn, sell_fn, buys, sells = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            expires_at=datetime.now() - timedelta(hours=1),
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 169.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 0
        assert len(buys) == 0

    def test_expired_order_status(self, manager):
        """만료 처리 후 상태가 expired로 변경"""
        order = manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            expires_at=datetime.now() - timedelta(hours=1),
        )

        buy_fn, sell_fn, _, _ = self._make_callbacks()
        manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 169.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert order.status == 'expired'

    def test_non_expired_order_fills_normally(self, manager):
        """만료 전 주문은 정상 체결"""
        buy_fn, sell_fn, buys, _ = self._make_callbacks()
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            expires_at=datetime.now() + timedelta(hours=24),
        )

        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 169.0},
            timestamp=datetime.now(),
            execute_buy_fn=buy_fn,
            execute_sell_fn=sell_fn,
        )

        assert len(filled) == 1
        assert len(buys) == 1


# ---- DB Persistence Tests ----

class TestDBPersistence:

    def test_create_order_persists_to_db(self, manager_with_db, temp_db, session_id):
        """주문 생성이 DB에 저장됨"""
        manager_with_db.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            trigger_order={'side': 'sell', 'price': 190.0},
            source='preset',
        )

        rows = temp_db.get_pending_orders(session_id)
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'NVDA'
        assert rows[0]['limit_price'] == 172.0
        assert rows[0]['trigger_order'] == {'side': 'sell', 'price': 190.0}
        assert rows[0]['source'] == 'preset'

    def test_cancel_order_updates_db(self, manager_with_db, temp_db, session_id):
        """주문 취소가 DB에 반영됨"""
        order = manager_with_db.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )
        manager_with_db.cancel_order(order.order_id)

        rows = temp_db.get_pending_orders(session_id, status='canceled')
        assert len(rows) == 1
        assert rows[0]['status'] == 'canceled'

    def test_fill_order_updates_db(self, manager_with_db, temp_db, session_id):
        """체결이 DB에 반영됨"""
        manager_with_db.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )

        now = datetime.now()
        manager_with_db.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 169.0},
            timestamp=now,
            execute_buy_fn=lambda s, p, t, **kw: None,
            execute_sell_fn=lambda s, p, t, reason='': None,
        )

        # Check filled in DB
        rows = temp_db.get_pending_orders(session_id, status='filled')
        assert len(rows) == 1
        assert rows[0]['fill_price'] == 172.0
        assert rows[0]['filled_at'] is not None

    def test_load_from_db_restores_orders(self, temp_db, session_id, lock):
        """DB에서 주문 복원 테스트"""
        # Create order with first manager
        mgr1 = LimitOrderManager(db=temp_db, lock=lock)
        mgr1.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )
        mgr1.create_limit_order(
            session_id=session_id, symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
        )

        # Restore with second manager (simulating restart)
        mgr2 = LimitOrderManager(db=temp_db, lock=lock)
        mgr2.load_from_db(session_id)

        pending = mgr2.get_pending_orders(session_id=session_id)
        assert len(pending) == 2
        symbols = {o.symbol for o in pending}
        assert symbols == {'NVDA', 'AAPL'}

    def test_get_all_orders_from_db(self, manager_with_db, temp_db, session_id):
        """DB에서 모든 주문 조회"""
        manager_with_db.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )
        manager_with_db.create_limit_order(
            session_id=session_id, symbol='AAPL', side='sell',
            limit_price=200.0, amount=10.0,
        )

        all_orders = temp_db.get_all_orders(session_id)
        assert len(all_orders) == 2


# ---- PaperTrader Integration Tests ----

class TestPaperTraderIntegration:

    @pytest.fixture
    def trader_with_limit_orders(self, temp_db):
        """PaperTrader with limit orders"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        broker = MockBroker()

        trader = PaperTrader(
            strategy=strategy,
            symbols=['NVDA'],
            broker=broker,
            initial_capital=10000.0,
            position_size=0.95,
            db=temp_db,
            limit_orders=[
                {
                    'symbol': 'NVDA',
                    'side': 'buy',
                    'price': 172.0,
                    'trigger_order': {'side': 'sell', 'price': 190.0},
                }
            ],
        )
        return trader

    def test_limit_order_manager_created(self, trader_with_limit_orders):
        """PaperTrader에 LimitOrderManager가 생성됨"""
        trader = trader_with_limit_orders
        assert trader.limit_order_manager is not None

    def test_limit_order_manager_none_without_db(self):
        """DB 없으면 LimitOrderManager가 None"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        trader = PaperTrader(
            strategy=strategy,
            symbols=['NVDA'],
            initial_capital=10000.0,
        )
        assert trader.limit_order_manager is None

    def test_start_registers_initial_limit_orders(self, trader_with_limit_orders, temp_db):
        """start() 호출 시 초기 지정가 주문 등록"""
        trader = trader_with_limit_orders
        trader.start()

        assert trader.session_id is not None

        # Check orders were registered
        pending = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending) == 1
        assert pending[0].symbol == 'NVDA'
        assert pending[0].side == 'buy'
        assert pending[0].limit_price == 172.0
        assert pending[0].source == 'preset'

        # Check trigger order
        assert pending[0].trigger_order == {'side': 'sell', 'price': 190.0}

    def test_start_uses_default_amount_from_capital(self, trader_with_limit_orders):
        """limit_order에 amount 없으면 initial_capital * position_size 사용"""
        trader = trader_with_limit_orders
        trader.start()

        pending = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        expected_amount = 10000.0 * 0.95  # initial_capital * position_size
        assert pending[0].amount == expected_amount

    def test_stop_cancels_pending_orders(self, trader_with_limit_orders, temp_db):
        """stop() 호출 시 대기 주문 전체 취소"""
        trader = trader_with_limit_orders
        trader.start()

        # Verify order exists
        pending = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending) == 1

        trader.stop()

        # All pending orders should be canceled
        pending_after = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending_after) == 0

    def test_multiple_limit_orders_from_preset(self, temp_db):
        """다중 지정가 주문이 프리셋에서 등록됨"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        broker = MockBroker()

        trader = PaperTrader(
            strategy=strategy,
            symbols=['NVDA', 'AAPL'],
            broker=broker,
            initial_capital=10000.0,
            position_size=0.5,
            db=temp_db,
            limit_orders=[
                {'symbol': 'NVDA', 'side': 'buy', 'price': 172.0, 'amount': 3000.0},
                {'symbol': 'AAPL', 'side': 'buy', 'price': 150.0, 'amount': 2000.0},
            ],
        )
        trader.start()

        pending = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending) == 2

        symbols = {o.symbol for o in pending}
        assert symbols == {'NVDA', 'AAPL'}

        trader.stop()

    def test_no_limit_orders_param_is_safe(self, temp_db):
        """limit_orders 파라미터 없이 PaperTrader 정상 동작"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        broker = MockBroker()

        trader = PaperTrader(
            strategy=strategy,
            symbols=['NVDA'],
            broker=broker,
            initial_capital=10000.0,
            db=temp_db,
        )
        trader.start()

        # LimitOrderManager exists but no orders
        assert trader.limit_order_manager is not None
        pending = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending) == 0

        trader.stop()


# ---- Error Handling Tests ----

class TestErrorHandling:

    def test_fill_callback_exception_does_not_crash(self, manager):
        """체결 콜백 예외가 전체 처리를 중단시키지 않음"""
        def bad_buy(symbol, price, timestamp, **kwargs):
            raise RuntimeError("Simulated buy error")

        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )
        manager.create_limit_order(
            session_id='session-1', symbol='NVDA', side='buy',
            limit_price=170.0, amount=3000.0,
        )

        # Should not raise, even though first callback fails
        filled = manager.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 169.0, 'high': 173.0, 'low': 168.0},
            timestamp=datetime.now(),
            execute_buy_fn=bad_buy,
            execute_sell_fn=lambda s, p, t, reason='': None,
        )

        # Neither order should show as filled since both callbacks would fail
        assert len(filled) == 0

    def test_load_from_db_without_db(self, lock):
        """DB 없이 load_from_db 호출해도 에러 없음"""
        mgr = LimitOrderManager(db=None, lock=lock)
        # Should not raise
        mgr.load_from_db('session-1')
