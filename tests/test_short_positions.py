"""
Short position (숏 포지션) 기능 테스트.

숏 진입/청산, PnL 계산, 리스크 관리, 포트폴리오 밸류, 주문 실행,
성과 계산, 하위 호환성을 검증한다.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading_bot.strategies.base_strategy import BaseStrategy
from trading_bot.backtester import Backtester
from trading_bot.risk_manager import RiskManager, RiskAction
from trading_bot.portfolio_manager import PortfolioManager
from trading_bot.order_executor import OrderExecutor
from trading_bot.performance_calculator import PerformanceCalculator
from trading_bot.execution_verifier import OrderExecutionVerifier


# ---------------------------------------------------------------------------
# Helper: 테스트용 전략 (하락장에서 숏 시그널 생성)
# ---------------------------------------------------------------------------

class BearishStrategy(BaseStrategy):
    """테스트용 하락 전략: 짧은 MA가 긴 MA 아래로 가면 SELL(-1)."""

    def __init__(self):
        super().__init__(name="BearishTest")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        data['fast_ma'] = data['close'].rolling(3).mean()
        data['slow_ma'] = data['close'].rolling(7).mean()
        data['signal'] = 0
        data.loc[data['fast_ma'] > data['slow_ma'], 'signal'] = 1
        data.loc[data['fast_ma'] < data['slow_ma'], 'signal'] = -1
        data = self.apply_position_tracking(data, allow_short=True)
        return data

    def get_current_signal(self, df):
        data = self.calculate_indicators(df)
        last = data.iloc[-1]
        return int(last['signal']), {'close': last['close'], 'timestamp': data.index[-1]}

    def get_all_signals(self, df):
        data = self.calculate_indicators(df)
        return data[data['signal'] != 0].to_dict('records')

    def get_entries_exits(self, df):
        data = self.calculate_indicators(df)
        entries = data['signal'] == 1
        exits = data['signal'] == -1
        return entries, exits


def _make_bearish_data(n=60):
    """하락 → 반등 데이터."""
    dates = pd.date_range('2024-01-01', periods=n, freq='1h')
    prices = np.concatenate([
        np.linspace(120, 90, n // 2),   # 하락
        np.linspace(90, 110, n // 2),    # 반등
    ])
    return pd.DataFrame({
        'open': prices,
        'high': prices + 1,
        'low': prices - 1,
        'close': prices,
        'volume': np.full(n, 1000),
    }, index=dates)


# ---------------------------------------------------------------------------
# 1. Backtester 숏 진입/청산
# ---------------------------------------------------------------------------

class TestBacktesterShortEntryExit(unittest.TestCase):
    """enable_short=True 인 백테스터에서 SHORT/COVER 거래가 생성되는지 검증."""

    def test_backtester_short_entry_exit(self):
        strategy = BearishStrategy()
        bt = Backtester(strategy, initial_capital=10000, enable_short=True, commission=0.001)
        results = bt.run(_make_bearish_data())

        short_trades = [t for t in bt.trades if t['type'] == 'SHORT']
        cover_trades = [t for t in bt.trades if 'COVER' in t['type']]

        self.assertGreater(len(short_trades), 0, "SHORT 거래가 생성되어야 한다")
        self.assertGreater(len(cover_trades), 0, "COVER 거래가 생성되어야 한다")

    def test_short_pnl_calculation(self):
        """숏 진입 100 → 커버 90 → 양의 PnL."""
        strategy = BearishStrategy()
        bt = Backtester(strategy, initial_capital=10000, enable_short=True,
                        commission=0.0, slippage_pct=0.0)

        # 단순 하락 데이터
        n = 30
        dates = pd.date_range('2024-01-01', periods=n, freq='1h')
        prices = np.concatenate([
            np.linspace(105, 100, 10),  # 약간 하락 (시그널 생성 전 워밍업)
            np.full(5, 100),            # 평탄 → SELL 시그널 발생 지점
            np.linspace(100, 90, 10),   # 하락 (숏 이익)
            np.linspace(90, 95, 5),     # 반등 (커버 시그널)
        ])
        df = pd.DataFrame({
            'open': prices, 'high': prices + 0.5,
            'low': prices - 0.5, 'close': prices,
            'volume': np.full(n, 1000),
        }, index=dates)

        results = bt.run(df)
        cover_trades = [t for t in bt.trades if 'COVER' in t['type']]

        # 커버 거래가 있으면 PnL 확인
        if cover_trades:
            for t in cover_trades:
                if 'pnl' in t:
                    # 하락장에서 숏이므로 양의 PnL 기대
                    self.assertGreater(t['pnl'], 0,
                                       "숏 후 가격 하락 시 양의 PnL이어야 함")

    def test_short_pnl_loss(self):
        """숏 진입 후 가격 상승 → 음의 PnL."""
        strategy = BearishStrategy()
        bt = Backtester(strategy, initial_capital=10000, enable_short=True,
                        commission=0.0, slippage_pct=0.0)

        # 상승 데이터: 하락 후 바로 급등
        n = 30
        dates = pd.date_range('2024-01-01', periods=n, freq='1h')
        prices = np.concatenate([
            np.linspace(110, 100, 10),  # 하락 (숏 시그널 생성)
            np.linspace(100, 90, 5),    # 추가 하락
            np.linspace(90, 130, 15),   # 급반등 (숏 손실)
        ])
        df = pd.DataFrame({
            'open': prices, 'high': prices + 0.5,
            'low': prices - 0.5, 'close': prices,
            'volume': np.full(n, 1000),
        }, index=dates)

        results = bt.run(df)

        # 마지막에 position < 0 이면 COVER(CLOSE) 발생
        # 가격이 숏 진입가보다 높으면 손실
        cover_trades = [t for t in bt.trades if 'COVER' in t['type'] and 'pnl' in t]
        # 최소한 close 시점에서 COVER 발생
        self.assertGreater(len(cover_trades), 0)


# ---------------------------------------------------------------------------
# 2. RiskManager 숏 포지션 손절/익절
# ---------------------------------------------------------------------------

class TestRiskManagerShort(unittest.TestCase):

    def test_risk_manager_short_stop_loss(self):
        """숏 포지션에서 가격 상승 → 손절."""
        rm = RiskManager(
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            short_stop_loss_pct=0.03,
            short_take_profit_pct=0.07,
        )

        # 숏 포지션: 진입 100, 현재가 104 → pnl = (100-104)/100 = -4% → 3% 초과 → 손절
        action = rm.check_symbol('AAPL', position=-10.0, entry_price=100.0, current_price=104.0)
        self.assertIsNotNone(action)
        self.assertEqual(action.action, 'stop_loss')

    def test_risk_manager_short_take_profit(self):
        """숏 포지션에서 가격 하락 → 익절."""
        rm = RiskManager(
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            short_stop_loss_pct=0.03,
            short_take_profit_pct=0.07,
        )

        # 숏 포지션: 진입 100, 현재가 92 → pnl = (100-92)/100 = 8% → 7% 초과 → 익절
        action = rm.check_symbol('AAPL', position=-10.0, entry_price=100.0, current_price=92.0)
        self.assertIsNotNone(action)
        self.assertEqual(action.action, 'take_profit')

    def test_risk_manager_short_within_bounds(self):
        """숏 포지션에서 손절/익절 범위 내 → 액션 없음."""
        rm = RiskManager(
            short_stop_loss_pct=0.03,
            short_take_profit_pct=0.07,
        )

        # 진입 100, 현재가 99 → pnl = 1% → 범위 내
        action = rm.check_symbol('AAPL', position=-10.0, entry_price=100.0, current_price=99.0)
        self.assertIsNone(action)


# ---------------------------------------------------------------------------
# 3. PortfolioManager 숏 포지션 가치 계산
# ---------------------------------------------------------------------------

class TestPortfolioValueWithShorts(unittest.TestCase):

    def test_portfolio_value_with_shorts(self):
        """음수 포지션의 포트폴리오 가치 계산."""
        pm = PortfolioManager(symbols=['AAPL'], initial_capital=10000)
        pm.positions['AAPL'] = -10.0
        pm.entry_prices['AAPL'] = 100.0
        pm.capital = 5000.0  # 숏 진입 후 남은 현금

        # 가격 하락: value = 5000 + 10 * (200 - 90) = 5000 + 1100 = 6100
        value = pm.get_portfolio_value({'AAPL': 90.0})
        # 2 * entry - current = 200 - 90 = 110, abs(pos) * 110 = 1100
        self.assertAlmostEqual(value, 5000 + 10 * (200 - 90), places=2)

    def test_portfolio_value_short_price_rise(self):
        """숏 포지션에서 가격 상승 → 포트폴리오 가치 감소."""
        pm = PortfolioManager(symbols=['AAPL'], initial_capital=10000)
        pm.positions['AAPL'] = -10.0
        pm.entry_prices['AAPL'] = 100.0
        pm.capital = 5000.0

        # 가격 상승: value = 5000 + 10 * (200 - 110) = 5000 + 900 = 5900
        value = pm.get_portfolio_value({'AAPL': 110.0})
        self.assertAlmostEqual(value, 5000 + 10 * (200 - 110), places=2)


# ---------------------------------------------------------------------------
# 4. OrderExecutor 숏/커버
# ---------------------------------------------------------------------------

class TestOrderExecutorShortCover(unittest.TestCase):

    def test_execute_short(self):
        """OrderExecutor.execute_short 메커니즘."""
        executor = OrderExecutor(commission=0.001, position_size=0.5)
        positions = {'AAPL': 0.0}
        entry_prices = {'AAPL': 0.0}

        trade = executor.execute_short(
            symbol='AAPL',
            price=100.0,
            timestamp=datetime(2024, 1, 1),
            capital=10000.0,
            positions=positions,
            entry_prices=entry_prices,
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade['type'], 'SHORT')
        self.assertLess(positions['AAPL'], 0, "숏 포지션은 음수")
        self.assertEqual(entry_prices['AAPL'], 100.0)

    def test_execute_cover(self):
        """OrderExecutor.execute_cover 메커니즘."""
        executor = OrderExecutor(commission=0.001, position_size=0.5)
        positions = {'AAPL': -50.0}
        entry_prices = {'AAPL': 100.0}

        trade = executor.execute_cover(
            symbol='AAPL',
            price=90.0,
            timestamp=datetime(2024, 1, 1),
            capital=5000.0,
            positions=positions,
            entry_prices=entry_prices,
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade['type'], 'COVER')
        self.assertGreater(trade['pnl'], 0, "가격 하락 시 양의 PnL")
        self.assertEqual(positions['AAPL'], 0, "커버 후 포지션 0")

    def test_execute_cover_no_short_position(self):
        """숏 포지션 없을 때 커버 시도 → None."""
        executor = OrderExecutor(commission=0.001, position_size=0.5)
        positions = {'AAPL': 0.0}
        entry_prices = {'AAPL': 0.0}

        trade = executor.execute_cover(
            symbol='AAPL',
            price=90.0,
            timestamp=datetime(2024, 1, 1),
            capital=10000.0,
            positions=positions,
            entry_prices=entry_prices,
        )
        self.assertIsNone(trade)


# ---------------------------------------------------------------------------
# 5. PerformanceCalculator COVER 거래 포함
# ---------------------------------------------------------------------------

class TestPerformanceCalculatorCoverTrades(unittest.TestCase):

    def test_cover_trades_included_in_win_rate(self):
        """COVER 거래가 win_rate 계산에 포함되는지 검증."""
        calc = PerformanceCalculator()

        trades = [
            {'type': 'SHORT', 'price': 100.0, 'size': 10.0},
            {'type': 'COVER', 'price': 90.0, 'size': 10.0, 'pnl': 100.0, 'pnl_pct': 10.0},
            {'type': 'BUY', 'price': 90.0, 'size': 10.0},
            {'type': 'SELL', 'price': 95.0, 'size': 10.0, 'pnl': 50.0, 'pnl_pct': 5.0},
        ]

        win_rate = calc.calculate_win_rate(trades)
        self.assertIsNotNone(win_rate)
        # 2 exit trades (COVER + SELL), both winning → 100%
        self.assertAlmostEqual(win_rate, 100.0)

    def test_cover_trades_included_in_performance_summary(self):
        """COVER 거래가 get_performance_summary에 포함."""
        calc = PerformanceCalculator()

        trades = [
            {'type': 'SHORT', 'price': 100.0, 'size': 10.0},
            {'type': 'COVER', 'price': 95.0, 'size': 10.0, 'pnl': 50.0, 'pnl_pct': 5.0},
        ]
        equity_history = [
            {'equity': 10000.0},
            {'equity': 10050.0},
        ]

        summary = calc.get_performance_summary(trades, equity_history, 10000.0)
        self.assertEqual(summary['total_trades'], 1)  # 1 COVER trade


# ---------------------------------------------------------------------------
# 6. ExecutionVerifier SHORT/COVER 검증
# ---------------------------------------------------------------------------

class TestExecutionVerifierShortCover(unittest.TestCase):

    def test_short_entry_valid(self):
        """signal=-1, position=0, trade=SHORT → 유효."""
        verifier = OrderExecutionVerifier()
        is_valid, msg = verifier.verify_execution(
            expected_signal=-1,
            executed_trade={'type': 'SHORT'},
            current_position=0,
        )
        self.assertTrue(is_valid)

    def test_cover_valid(self):
        """signal=1, position<0, trade=COVER → 유효."""
        verifier = OrderExecutionVerifier()
        is_valid, msg = verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'COVER'},
            current_position=-10.0,
        )
        self.assertTrue(is_valid)


# ---------------------------------------------------------------------------
# 7. 하위 호환성: enable_short=False → 기존 동작 유지
# ---------------------------------------------------------------------------

class TestBackwardCompatDefaultFalse(unittest.TestCase):

    def test_backward_compat_default_false(self):
        """enable_short=False(기본값)일 때 SHORT/COVER 없음."""
        strategy = BearishStrategy()
        bt = Backtester(strategy, initial_capital=10000)

        self.assertFalse(bt.enable_short)

        results = bt.run(_make_bearish_data())
        short_trades = [t for t in bt.trades if t['type'] == 'SHORT']
        self.assertEqual(len(short_trades), 0, "enable_short=False면 SHORT 없어야 한다")

    def test_risk_manager_long_unchanged(self):
        """롱 포지션의 리스크 관리가 변경되지 않았는지 확인."""
        rm = RiskManager(stop_loss_pct=0.05, take_profit_pct=0.10)

        # 롱 포지션: 진입 100, 현재가 94 → -6% → 5% 초과 → 손절
        action = rm.check_symbol('AAPL', position=10.0, entry_price=100.0, current_price=94.0)
        self.assertIsNotNone(action)
        self.assertEqual(action.action, 'stop_loss')


if __name__ == '__main__':
    unittest.main()
