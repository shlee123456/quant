"""
Production-level integration tests for the Limit Order System

실제 운영 환경을 시뮬레이션하여 모든 기능을 검증합니다:
1. 프리셋 → 세션 → 체결 → 체인 → 정산 전체 라이프사이클
2. PaperTrader의 실제 execute_buy/sell을 통한 자본/포지션 변화
3. DB 영속성 및 정합성
4. 동시성(멀티 스레드) 안전성
5. 엣지 케이스 및 에러 복구
"""

import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_bot.limit_order import LimitOrderManager, PendingOrder
from trading_bot.database import TradingDatabase
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.strategies import RSIStrategy


# ---- Production-like Mock Broker ----

class ProductionMockBroker:
    """
    프로덕션 환경을 시뮬레이션하는 MockBroker.
    시세를 단계별로 변화시킬 수 있습니다.
    """

    def __init__(self, initial_prices: Dict[str, float] = None):
        self._prices: Dict[str, Dict[str, float]] = {}
        self._price_history: Dict[str, List[Dict]] = {}

        if initial_prices:
            for symbol, price in initial_prices.items():
                self.set_price(symbol, price)

    def set_price(self, symbol: str, last: float,
                  high: float = None, low: float = None,
                  open_: float = None, volume: float = 1000000):
        """시세 설정 (high/low 자동 계산)"""
        self._prices[symbol] = {
            'symbol': symbol,
            'last': last,
            'high': high or last * 1.01,
            'low': low or last * 0.99,
            'open': open_ or last,
            'volume': volume,
            'change': 0.0,
            'rate': 0.0,
            'timestamp': int(datetime.now().timestamp() * 1000),
        }

    def fetch_ticker(self, symbol, **kwargs):
        if symbol not in self._prices:
            self.set_price(symbol, 100.0)
        return self._prices[symbol]

    def fetch_ohlcv(self, symbol, timeframe='1d', limit=100, **kwargs):
        price = self._prices.get(symbol, {}).get('last', 100.0)
        dates = pd.date_range(end=datetime.now(), periods=limit, freq='D')

        # 점진적 상승 데이터 (RSI가 다양한 시그널을 생성하도록)
        closes = [price * (0.9 + 0.2 * i / limit) for i in range(limit)]
        return pd.DataFrame({
            'open': [c * 0.995 for c in closes],
            'high': [c * 1.02 for c in closes],
            'low': [c * 0.98 for c in closes],
            'close': closes,
            'volume': [1000000] * limit,
        }, index=dates)


# ---- Fixtures ----

@pytest.fixture
def temp_dir():
    """임시 디렉토리"""
    d = tempfile.mkdtemp()
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_db(temp_dir):
    """프로덕션 DB (임시 파일)"""
    db_path = os.path.join(temp_dir, 'production_test.db')
    return TradingDatabase(db_path=db_path)


@pytest.fixture
def preset_manager(temp_dir):
    """프리셋 매니저 (임시 파일)"""
    preset_file = os.path.join(temp_dir, 'test_presets.json')
    return StrategyPresetManager(presets_file=preset_file)


@pytest.fixture
def broker():
    return ProductionMockBroker({
        'NVDA': 175.0,
        'AAPL': 155.0,
        'MSFT': 410.0,
    })


# ==================================================================
# 시나리오 1: NVDA $172 매수 → $190 매도 전체 라이프사이클
# ==================================================================

class TestScenario1_FullLifecycle:
    """
    프로덕션 시나리오:
    1. 프리셋 생성 (NVDA $172 매수, 체결 후 $190 매도)
    2. PaperTrader 시작 → 지정가 주문 등록
    3. 가격 하락 → 매수 체결 → 자본/포지션 변화 확인
    4. 체인 매도 주문 자동 생성 확인
    5. 가격 상승 → 매도 체결 → 수익 실현
    6. 세션 종료 → DB 최종 상태 확인
    """

    def test_full_buy_sell_lifecycle(self, temp_db, broker):
        """전체 매수→매도 라이프사이클"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)

        trader = PaperTrader(
            strategy=strategy,
            symbols=['NVDA'],
            broker=broker,
            initial_capital=10000.0,
            position_size=0.95,
            db=temp_db,
            limit_orders=[{
                'symbol': 'NVDA',
                'side': 'buy',
                'price': 172.0,
                'trigger_order': {'side': 'sell', 'price': 190.0},
            }],
        )

        # 1. 세션 시작 → 지정가 주문 등록
        trader.start()
        assert trader.session_id is not None

        mgr = trader.limit_order_manager
        pending = mgr.get_pending_orders(session_id=trader.session_id)
        assert len(pending) == 1
        assert pending[0].side == 'buy'
        assert pending[0].limit_price == 172.0

        initial_capital = trader.capital
        assert initial_capital == 10000.0

        # 2. 가격 하락: NVDA $170 (low=$168) → 매수 체결 (limit_price=$172)
        broker.set_price('NVDA', last=170.0, high=173.0, low=168.0)
        ticker = broker.fetch_ticker('NVDA')
        now = datetime.now()

        filled = mgr.check_and_fill_paper(
            symbol='NVDA',
            ticker=ticker,
            timestamp=now,
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled) == 1
        assert filled[0].status == 'filled'
        assert filled[0].fill_price == 172.0

        # 3. 자본/포지션 변화 확인
        assert trader.capital < initial_capital  # 자본 감소
        assert trader.positions['NVDA'] > 0  # 포지션 보유
        assert trader.entry_prices['NVDA'] == 172.0  # 진입가 기록

        # 매수 금액 검증: initial_capital * position_size = $9,500
        trade_capital = initial_capital * 0.95  # $9,500
        expected_shares = trade_capital / 172.0 * (1 - trader.commission)
        assert abs(trader.positions['NVDA'] - expected_shares) < 0.01

        # 잔여 자본: $10,000 - $9,500 = $500
        assert abs(trader.capital - (initial_capital - trade_capital)) < 0.01

        # 4. 체인 매도 주문 자동 생성 확인
        sell_pending = mgr.get_pending_orders(session_id=trader.session_id)
        assert len(sell_pending) == 1
        assert sell_pending[0].side == 'sell'
        assert sell_pending[0].limit_price == 190.0
        assert sell_pending[0].source == 'chained'

        # 5. 가격 상승: NVDA $191 (high=$193) → 매도 체결 (limit_price=$190)
        broker.set_price('NVDA', last=191.0, high=193.0, low=189.0)
        ticker2 = broker.fetch_ticker('NVDA')

        filled2 = mgr.check_and_fill_paper(
            symbol='NVDA',
            ticker=ticker2,
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled2) == 1
        assert filled2[0].status == 'filled'
        assert filled2[0].fill_price == 190.0

        # 6. 포지션 청산 + 수익 실현
        assert trader.positions['NVDA'] == 0  # 포지션 청산
        assert trader.capital > initial_capital  # 수익 실현

        # 수익 계산: (190 - 172) / 172 ≈ +10.5% (수수료 제외)
        profit_pct = (trader.capital - initial_capital) / initial_capital * 100
        assert profit_pct > 0, f"수익이 양수여야 함: {profit_pct:.2f}%"

        # 7. 더 이상 대기 주문 없음
        final_pending = mgr.get_pending_orders(session_id=trader.session_id)
        assert len(final_pending) == 0

        # 8. DB에 거래 기록 확인
        trades = temp_db.get_session_trades(trader.session_id)
        assert len(trades) == 2  # BUY + SELL

        buy_trade = next(t for t in trades if t['type'] == 'BUY')
        sell_trade = next(t for t in trades if t['type'] == 'SELL')
        assert buy_trade['price'] == 172.0
        assert sell_trade['price'] == 190.0

        # 9. 세션 종료
        trader.stop()

    def test_buy_no_fill_price_too_high(self, temp_db, broker):
        """가격이 지정가에 도달하지 않으면 미체결"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, position_size=0.95, db=temp_db,
            limit_orders=[{'symbol': 'NVDA', 'side': 'buy', 'price': 160.0}],
        )
        trader.start()

        # 가격이 $170~$175 범위 → $160 매수 주문 미체결
        broker.set_price('NVDA', last=172.0, high=175.0, low=170.0)
        ticker = broker.fetch_ticker('NVDA')

        filled = trader.limit_order_manager.check_and_fill_paper(
            symbol='NVDA', ticker=ticker, timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled) == 0
        assert trader.capital == 10000.0  # 자본 변화 없음
        assert trader.positions['NVDA'] == 0  # 포지션 없음

        trader.stop()


# ==================================================================
# 시나리오 2: 멀티 심볼 지정가 주문
# ==================================================================

class TestScenario2_MultiSymbol:
    """
    멀티 심볼 동시 운용:
    - NVDA $172 매수
    - AAPL $150 매수
    - 각각 독립적으로 체결/미체결
    """

    def test_multi_symbol_independent_fills(self, temp_db, broker):
        """멀티 심볼: 각 심볼 독립적으로 체결"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy,
            symbols=['NVDA', 'AAPL'],
            broker=broker,
            initial_capital=20000.0,
            position_size=0.45,  # 각 종목 45%
            db=temp_db,
            limit_orders=[
                {'symbol': 'NVDA', 'side': 'buy', 'price': 172.0, 'amount': 9000.0},
                {'symbol': 'AAPL', 'side': 'buy', 'price': 150.0, 'amount': 9000.0},
            ],
        )
        trader.start()

        mgr = trader.limit_order_manager

        # NVDA 체결, AAPL 미체결
        broker.set_price('NVDA', last=170.0, high=173.0, low=168.0)
        broker.set_price('AAPL', last=155.0, high=157.0, low=153.0)  # 150 도달 안 됨

        filled_nvda = mgr.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )
        filled_aapl = mgr.check_and_fill_paper(
            symbol='AAPL', ticker=broker.fetch_ticker('AAPL'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled_nvda) == 1
        assert len(filled_aapl) == 0
        assert trader.positions['NVDA'] > 0
        assert trader.positions['AAPL'] == 0

        # AAPL도 체결
        broker.set_price('AAPL', last=149.0, high=151.0, low=148.0)
        filled_aapl2 = mgr.check_and_fill_paper(
            symbol='AAPL', ticker=broker.fetch_ticker('AAPL'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled_aapl2) == 1
        assert trader.positions['AAPL'] > 0
        assert trader.positions['NVDA'] > 0  # 여전히 보유

        trader.stop()


# ==================================================================
# 시나리오 3: 프리셋 시스템 통합
# ==================================================================

class TestScenario3_PresetIntegration:
    """프리셋 저장/로드 → PaperTrader 통합"""

    def test_preset_save_load_with_limit_orders(self, preset_manager):
        """지정가 주문이 포함된 프리셋 저장/로드"""
        limit_orders = [
            {
                'symbol': 'NVDA',
                'side': 'buy',
                'price': 172.0,
                'trigger_order': {'side': 'sell', 'price': 190.0},
            },
            {
                'symbol': 'AAPL',
                'side': 'buy',
                'price': 150.0,
                'amount': 5000.0,
            },
        ]

        result = preset_manager.save_preset(
            name="지정가 매매 테스트",
            strategy="RSI Strategy",
            strategy_params={"period": 14, "overbought": 70, "oversold": 30},
            symbols=["NVDA", "AAPL"],
            initial_capital=20000.0,
            position_size=0.45,
            limit_orders=limit_orders,
        )
        assert result is True

        # 로드
        preset = preset_manager.load_preset("지정가 매매 테스트")
        assert preset is not None
        assert len(preset['limit_orders']) == 2

        lo_nvda = next(lo for lo in preset['limit_orders'] if lo['symbol'] == 'NVDA')
        assert lo_nvda['price'] == 172.0
        assert lo_nvda['trigger_order'] == {'side': 'sell', 'price': 190.0}

        lo_aapl = next(lo for lo in preset['limit_orders'] if lo['symbol'] == 'AAPL')
        assert lo_aapl['price'] == 150.0
        assert lo_aapl['amount'] == 5000.0

    def test_preset_without_limit_orders_backward_compatible(self, preset_manager):
        """기존 프리셋(limit_orders 없음)과의 하위 호환성"""
        preset_manager.save_preset(
            name="기존 전략",
            strategy="RSI Strategy",
            strategy_params={"period": 14},
            symbols=["AAPL"],
        )

        preset = preset_manager.load_preset("기존 전략")
        assert preset is not None
        assert preset.get('limit_orders', []) == []

    def test_preset_to_paper_trader_full_path(self, preset_manager, temp_db, broker):
        """프리셋 → PaperTrader 전체 경로"""
        # 1. 프리셋 저장
        preset_manager.save_preset(
            name="NVDA 지정가",
            strategy="RSI Strategy",
            strategy_params={"period": 14, "overbought": 70, "oversold": 30},
            symbols=["NVDA"],
            initial_capital=10000.0,
            position_size=0.95,
            limit_orders=[{
                'symbol': 'NVDA', 'side': 'buy', 'price': 172.0,
                'trigger_order': {'side': 'sell', 'price': 190.0},
            }],
        )

        # 2. 프리셋 로드
        config = preset_manager.load_preset("NVDA 지정가")

        # 3. session_manager 경로 시뮬레이션 (config → PaperTrader)
        strategy = RSIStrategy(**config['strategy_params'])
        limit_orders = config.get('limit_orders', [])

        trader = PaperTrader(
            strategy=strategy,
            symbols=config['symbols'],
            broker=broker,
            initial_capital=config['initial_capital'],
            position_size=config['position_size'],
            db=temp_db,
            limit_orders=limit_orders if limit_orders else None,
        )

        # 4. 세션 시작 → 주문 등록 확인
        trader.start()
        pending = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending) == 1
        assert pending[0].symbol == 'NVDA'
        assert pending[0].limit_price == 172.0
        assert pending[0].trigger_order == {'side': 'sell', 'price': 190.0}

        trader.stop()

    def test_preset_export_import_with_limit_orders(self, preset_manager, temp_dir):
        """프리셋 내보내기/가져오기 (limit_orders 포함)"""
        # 저장
        preset_manager.save_preset(
            name="내보낼 전략",
            strategy="RSI Strategy",
            strategy_params={"period": 14},
            symbols=["NVDA"],
            limit_orders=[{'symbol': 'NVDA', 'side': 'buy', 'price': 172.0}],
        )

        # 내보내기
        export_path = os.path.join(temp_dir, 'exported.json')
        preset_manager.export_preset("내보낼 전략", export_path)
        assert os.path.exists(export_path)

        # 새 매니저에서 가져오기
        import_file = os.path.join(temp_dir, 'imported_presets.json')
        mgr2 = StrategyPresetManager(presets_file=import_file)
        result = mgr2.import_preset(export_path)
        assert result is True

        loaded = mgr2.load_preset("내보낼 전략")
        assert loaded is not None
        assert len(loaded.get('limit_orders', [])) == 1
        assert loaded['limit_orders'][0]['price'] == 172.0


# ==================================================================
# 시나리오 4: DB 영속성 및 복구
# ==================================================================

class TestScenario4_DBPersistence:
    """DB 영속성: 재시작 후 복구, 주문 상태 일관성"""

    def test_restart_recovery(self, temp_db):
        """세션 재시작 후 대기 주문 복원"""
        lock = threading.RLock()

        # 세션 1: 주문 생성
        session_id = temp_db.create_session('RSI_14_30_70', 10000.0, 'Test')

        mgr1 = LimitOrderManager(db=temp_db, lock=lock)
        mgr1.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            trigger_order={'side': 'sell', 'price': 190.0},
            source='preset',
        )
        mgr1.create_limit_order(
            session_id=session_id, symbol='AAPL', side='buy',
            limit_price=150.0, amount=3000.0,
            source='preset',
        )

        # 세션 2: 재시작 (새 매니저 인스턴스)
        mgr2 = LimitOrderManager(db=temp_db, lock=lock)
        assert len(mgr2.get_pending_orders()) == 0  # 메모리 비어있음

        mgr2.load_from_db(session_id)

        pending = mgr2.get_pending_orders(session_id=session_id)
        assert len(pending) == 2

        # 데이터 정합성 확인
        nvda = next(o for o in pending if o.symbol == 'NVDA')
        assert nvda.limit_price == 172.0
        assert nvda.trigger_order == {'side': 'sell', 'price': 190.0}
        assert nvda.source == 'preset'

        aapl = next(o for o in pending if o.symbol == 'AAPL')
        assert aapl.limit_price == 150.0

    def test_filled_orders_persist_correctly(self, temp_db):
        """체결된 주문이 DB에 올바르게 저장됨"""
        lock = threading.RLock()
        session_id = temp_db.create_session('RSI_14_30_70', 10000.0, 'Test')

        mgr = LimitOrderManager(db=temp_db, lock=lock)
        mgr.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )

        # 체결
        now = datetime.now()
        mgr.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 168.0},
            timestamp=now,
            execute_buy_fn=lambda s, p, t, **kw: None,
            execute_sell_fn=lambda s, p, t, reason='': None,
        )

        # DB에서 직접 확인
        all_orders = temp_db.get_all_orders(session_id)
        assert len(all_orders) == 1
        assert all_orders[0]['status'] == 'filled'
        assert all_orders[0]['fill_price'] == 172.0
        assert all_orders[0]['filled_at'] is not None

        # pending 조회 시 나오지 않아야 함
        pending = temp_db.get_pending_orders(session_id)
        assert len(pending) == 0

    def test_chain_orders_persist_to_db(self, temp_db):
        """체인 주문도 DB에 저장됨"""
        lock = threading.RLock()
        session_id = temp_db.create_session('RSI_14_30_70', 10000.0, 'Test')

        mgr = LimitOrderManager(db=temp_db, lock=lock)
        mgr.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            trigger_order={'side': 'sell', 'price': 190.0},
        )

        # 매수 체결 → 체인 매도 주문 생성
        mgr.check_and_fill_paper(
            symbol='NVDA',
            ticker={'last': 170.0, 'high': 173.0, 'low': 168.0},
            timestamp=datetime.now(),
            execute_buy_fn=lambda s, p, t, **kw: None,
            execute_sell_fn=lambda s, p, t, reason='': None,
        )

        # DB에 2개 주문: 원본(filled) + 체인(pending)
        all_orders = temp_db.get_all_orders(session_id)
        assert len(all_orders) == 2

        filled = [o for o in all_orders if o['status'] == 'filled']
        pending = [o for o in all_orders if o['status'] == 'pending']
        assert len(filled) == 1
        assert len(pending) == 1

        assert filled[0]['side'] == 'buy'
        assert pending[0]['side'] == 'sell'
        assert pending[0]['limit_price'] == 190.0
        assert pending[0]['source'] == 'chained'

    def test_session_delete_cascades_to_pending_orders(self, temp_db):
        """세션 삭제 시 pending_orders도 함께 삭제"""
        lock = threading.RLock()
        session_id = temp_db.create_session('RSI_14_30_70', 10000.0, 'Test')

        mgr = LimitOrderManager(db=temp_db, lock=lock)
        mgr.create_limit_order(
            session_id=session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
        )

        # 주문 존재 확인
        assert len(temp_db.get_all_orders(session_id)) == 1

        # 세션을 completed로 전환 후 삭제 (active 세션은 삭제 불가)
        temp_db.update_session(session_id, {
            'status': 'completed',
            'final_capital': 10000.0,
            'total_return': 0.0,
        })
        temp_db.delete_session(session_id)

        # 주문도 삭제됨
        assert len(temp_db.get_all_orders(session_id)) == 0


# ==================================================================
# 시나리오 5: 동시성 안전성
# ==================================================================

class TestScenario5_Concurrency:
    """멀티 스레드 환경에서의 안전성"""

    def test_concurrent_order_creation(self, temp_db):
        """동시에 여러 스레드에서 주문 생성"""
        lock = threading.RLock()
        session_id = temp_db.create_session('RSI_14_30_70', 10000.0, 'Test')
        mgr = LimitOrderManager(db=temp_db, lock=lock)

        errors = []
        created_orders = []

        def create_order(i):
            try:
                order = mgr.create_limit_order(
                    session_id=session_id,
                    symbol=f'SYM{i}',
                    side='buy',
                    limit_price=100.0 + i,
                    amount=1000.0,
                )
                created_orders.append(order.order_id)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=create_order, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(created_orders) == 20

        # 모든 주문이 DB에 저장됨
        all_orders = temp_db.get_all_orders(session_id)
        assert len(all_orders) == 20

    def test_concurrent_fill_and_cancel(self, temp_db):
        """동시에 체결과 취소가 발생해도 안전"""
        lock = threading.RLock()
        session_id = temp_db.create_session('RSI_14_30_70', 10000.0, 'Test')
        mgr = LimitOrderManager(db=temp_db, lock=lock)

        # 10개 주문 생성
        orders = []
        for i in range(10):
            o = mgr.create_limit_order(
                session_id=session_id,
                symbol='NVDA',
                side='buy',
                limit_price=170.0 + i,
                amount=500.0,
            )
            orders.append(o)

        errors = []

        def cancel_orders():
            """홀수 인덱스 주문 취소"""
            try:
                for i in range(1, 10, 2):
                    mgr.cancel_order(orders[i].order_id)
            except Exception as e:
                errors.append(f"cancel: {e}")

        def fill_orders():
            """짝수 인덱스 주문 체결 시도"""
            try:
                mgr.check_and_fill_paper(
                    symbol='NVDA',
                    ticker={'last': 165.0, 'high': 180.0, 'low': 160.0},
                    timestamp=datetime.now(),
                    execute_buy_fn=lambda s, p, t, **kw: None,
                    execute_sell_fn=lambda s, p, t, reason='': None,
                )
            except Exception as e:
                errors.append(f"fill: {e}")

        t1 = threading.Thread(target=cancel_orders)
        t2 = threading.Thread(target=fill_orders)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"Errors: {errors}"

        # 최종 상태: 모든 주문이 유효한 상태
        all_orders = mgr.get_all_orders(session_id=session_id)
        for order in all_orders:
            assert order.status in ('pending', 'filled', 'canceled')


# ==================================================================
# 시나리오 6: 엣지 케이스
# ==================================================================

class TestScenario6_EdgeCases:
    """프로덕션 엣지 케이스"""

    def test_duplicate_buy_ignored_when_already_in_position(self, temp_db, broker):
        """이미 포지션 보유 중이면 추가 매수 무시"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, position_size=0.5, db=temp_db,
            limit_orders=[
                {'symbol': 'NVDA', 'side': 'buy', 'price': 172.0, 'amount': 5000.0},
                {'symbol': 'NVDA', 'side': 'buy', 'price': 168.0, 'amount': 3000.0},
            ],
        )
        trader.start()

        mgr = trader.limit_order_manager

        # 두 주문 모두 체결 조건 충족
        broker.set_price('NVDA', last=165.0, high=173.0, low=163.0)
        filled = mgr.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        # 첫 번째는 체결, 두 번째는 이미 포지션 있어서 execute_buy가 무시
        # (PaperTrader.execute_buy는 이미 포지션 있으면 skip)
        assert len(filled) == 2  # 둘 다 filled 상태이지만
        # 실제 포지션은 첫 매수만 반영
        assert trader.positions['NVDA'] > 0

        trader.stop()

    def test_sell_without_position_ignored(self, temp_db, broker):
        """포지션 없이 매도 주문 체결 시도 → 무시"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, db=temp_db,
            limit_orders=[
                {'symbol': 'NVDA', 'side': 'sell', 'price': 190.0, 'amount': 10.0},
            ],
        )
        trader.start()

        broker.set_price('NVDA', last=192.0, high=195.0, low=189.0)
        filled = trader.limit_order_manager.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        # 체결은 시도되지만 포지션 없으므로 execute_sell이 skip
        assert trader.capital == 10000.0  # 자본 변화 없음

        trader.stop()

    def test_zero_commission_exact_amount(self, temp_db, broker):
        """수수료 0%일 때 정확한 금액 계산"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, position_size=1.0,  # 100% 투자
            db=temp_db,
            limit_orders=[{
                'symbol': 'NVDA', 'side': 'buy', 'price': 200.0,
                'trigger_order': {'side': 'sell', 'price': 220.0},
            }],
        )
        trader.commission = 0.0  # 수수료 제거
        trader.start()

        mgr = trader.limit_order_manager

        # 매수 체결
        broker.set_price('NVDA', last=198.0, high=201.0, low=197.0)
        mgr.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert trader.positions['NVDA'] == 10000.0 / 200.0  # 정확히 50주
        assert trader.capital == 0.0  # 전액 투자

        # 매도 체결
        broker.set_price('NVDA', last=221.0, high=223.0, low=219.0)
        mgr.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert trader.positions['NVDA'] == 0
        # 수익: 50주 * ($220 - $200) = $1,000
        assert trader.capital == 11000.0

        trader.stop()

    def test_expiration_before_fill(self, temp_db, broker):
        """만료 시간이 지나면 가격 도달해도 체결 안 됨"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, db=temp_db,
        )
        trader.start()

        mgr = trader.limit_order_manager
        # 이미 만료된 주문 생성
        mgr.create_limit_order(
            session_id=trader.session_id, symbol='NVDA', side='buy',
            limit_price=172.0, amount=5000.0,
            expires_at=datetime.now() - timedelta(hours=1),
        )

        broker.set_price('NVDA', last=170.0, high=173.0, low=168.0)
        filled = mgr.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled) == 0
        assert trader.capital == 10000.0

        trader.stop()

    def test_stop_cancels_all_pending(self, temp_db, broker):
        """세션 종료 시 모든 대기 주문 취소"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA', 'AAPL'], broker=broker,
            initial_capital=10000.0, db=temp_db,
            limit_orders=[
                {'symbol': 'NVDA', 'side': 'buy', 'price': 172.0, 'amount': 5000.0},
                {'symbol': 'AAPL', 'side': 'buy', 'price': 150.0, 'amount': 3000.0},
            ],
        )
        trader.start()

        pending_before = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending_before) == 2

        trader.stop()

        pending_after = trader.limit_order_manager.get_pending_orders(
            session_id=trader.session_id
        )
        assert len(pending_after) == 0

        # DB에서도 canceled 상태
        all_orders = temp_db.get_all_orders(trader.session_id)
        for order in all_orders:
            assert order['status'] == 'canceled'


# ==================================================================
# 시나리오 7: 실제 _realtime_iteration 시뮬레이션
# ==================================================================

class TestScenario7_RealtimeIteration:
    """_realtime_iteration 내에서의 지정가 주문 처리 흐름"""

    def test_realtime_iteration_fills_limit_order(self, temp_db, broker):
        """_realtime_iteration에서 지정가 주문이 체결되는 흐름"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, position_size=0.95, db=temp_db,
            limit_orders=[{
                'symbol': 'NVDA', 'side': 'buy', 'price': 172.0,
            }],
        )
        trader.start()

        # 가격을 지정가 아래로 설정
        broker.set_price('NVDA', last=170.0, high=173.0, low=168.0)

        # _realtime_iteration 직접 호출
        # (run_realtime 대신 단일 반복 실행, timeframe 인자 1개)
        trader._realtime_iteration('1d')

        # 체결 확인
        assert trader.positions['NVDA'] > 0
        assert trader.entry_prices['NVDA'] == 172.0

        trader.stop()

    def test_stop_loss_overrides_limit_order(self, temp_db, broker):
        """손절매가 지정가 주문보다 우선"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, position_size=0.95, db=temp_db,
            stop_loss_pct=0.03,
            enable_stop_loss=True,
        )
        trader.start()

        # 먼저 수동으로 매수
        broker.set_price('NVDA', last=175.0, high=176.0, low=174.0)
        trader.execute_buy('NVDA', 175.0, datetime.now())
        assert trader.positions['NVDA'] > 0

        # 지정가 매도 주문 추가
        trader.limit_order_manager.create_limit_order(
            session_id=trader.session_id, symbol='NVDA',
            side='sell', limit_price=190.0, amount=trader.positions['NVDA'],
        )

        # 가격 급락: 3% 이상 하락 → 손절매 발동
        broker.set_price('NVDA', last=169.0, high=171.0, low=168.0)

        trader._realtime_iteration('1d')

        # 손절매로 포지션 청산 (지정가 매도 아님)
        assert trader.positions['NVDA'] == 0

        trader.stop()


# ==================================================================
# 시나리오 8: amount 파라미터 기반 매수 검증
# ==================================================================

class TestScenario8_AmountBasedBuy:
    """지정가 주문의 amount가 실제 execute_buy에 전달되어 올바르게 적용되는지 검증"""

    def test_custom_amount_used_in_buy(self, temp_db, broker):
        """amount 지정 시 해당 금액만큼 매수"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, position_size=0.95,  # 기본: $9,500
            db=temp_db,
            commission=0.0,
            limit_orders=[{
                'symbol': 'NVDA', 'side': 'buy', 'price': 172.0,
                'amount': 3000.0,  # $3,000만 매수 (기본 $9,500 아님)
            }],
        )
        trader.start()

        broker.set_price('NVDA', last=170.0, high=173.0, low=168.0)
        filled = trader.limit_order_manager.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled) == 1
        # $3,000 / $172 ≈ 17.44 주 (commission=0)
        expected_shares = 3000.0 / 172.0
        assert abs(trader.positions['NVDA'] - expected_shares) < 0.01
        # 자본: $10,000 - $3,000 = $7,000
        assert abs(trader.capital - 7000.0) < 0.01

        trader.stop()

    def test_default_amount_uses_position_size(self, temp_db, broker):
        """amount 미지정 시 capital * position_size 기본값 사용"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=10000.0, position_size=0.5,  # $5,000
            db=temp_db,
            commission=0.0,
            limit_orders=[{
                'symbol': 'NVDA', 'side': 'buy', 'price': 172.0,
                # amount 미지정 → 기본값 = 10000 * 0.5 = $5,000
            }],
        )
        trader.start()

        broker.set_price('NVDA', last=170.0, high=173.0, low=168.0)
        filled = trader.limit_order_manager.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled) == 1
        # $5,000 / $172 ≈ 29.07 주
        expected_shares = 5000.0 / 172.0
        assert abs(trader.positions['NVDA'] - expected_shares) < 0.01
        # 자본: $10,000 - $5,000 = $5,000
        assert abs(trader.capital - 5000.0) < 0.01

        trader.stop()

    def test_amount_capped_at_available_capital(self, temp_db, broker):
        """amount가 보유 자본보다 크면 자본까지만 매수"""
        strategy = RSIStrategy(period=14)
        trader = PaperTrader(
            strategy=strategy, symbols=['NVDA'], broker=broker,
            initial_capital=2000.0, position_size=0.95,
            db=temp_db,
            commission=0.0,
            limit_orders=[{
                'symbol': 'NVDA', 'side': 'buy', 'price': 172.0,
                'amount': 5000.0,  # $5,000 요청하지만 자본은 $2,000
            }],
        )
        trader.start()

        broker.set_price('NVDA', last=170.0, high=173.0, low=168.0)
        filled = trader.limit_order_manager.check_and_fill_paper(
            symbol='NVDA', ticker=broker.fetch_ticker('NVDA'),
            timestamp=datetime.now(),
            execute_buy_fn=trader.execute_buy,
            execute_sell_fn=trader.execute_sell,
        )

        assert len(filled) == 1
        # $2,000 / $172 ≈ 11.63 주 (자본 $2,000으로 cap)
        expected_shares = 2000.0 / 172.0
        assert abs(trader.positions['NVDA'] - expected_shares) < 0.01
        # 자본: 거의 $0
        assert trader.capital < 1.0

        trader.stop()
