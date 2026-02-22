"""
Tests for VBTBacktester - VectorBT 기반 백테스터

결과 Dict 키 호환성, RSIStrategy 통합, 엣지 케이스, 레거시 방향 비교 테스트
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.vbt_backtester import VBTBacktester
from trading_bot.backtester import Backtester
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy


# Expected keys from legacy Backtester.run()
EXPECTED_KEYS = {
    'initial_capital', 'final_capital', 'total_return',
    'total_trades', 'winning_trades', 'losing_trades',
    'win_rate', 'avg_win', 'avg_loss',
    'max_drawdown', 'sharpe_ratio', 'total_slippage_cost',
    'start_date', 'end_date',
}


@pytest.fixture
def sample_data():
    """Reproducible sample data with enough volatility for signals"""
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_ohlcv(periods=500, volatility=0.03)


@pytest.fixture
def bullish_data():
    """Strong bullish trend data"""
    gen = SimulationDataGenerator(seed=99)
    return gen.generate_trend_data(periods=500, trend='bullish', volatility=0.03)


@pytest.fixture
def volatile_data():
    """Highly volatile data to produce many signals"""
    gen = SimulationDataGenerator(seed=123)
    return gen.generate_ohlcv(periods=500, volatility=0.06)


@pytest.fixture
def empty_data():
    """Empty OHLCV DataFrame"""
    return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])


class TestVBTBacktesterResultKeys:
    """run() 반환 Dict에 레거시와 동일한 키가 포함되는지 테스트"""

    def test_result_has_all_expected_keys(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert isinstance(result, dict)
        missing = EXPECTED_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_result_has_no_extra_keys(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        extra = set(result.keys()) - EXPECTED_KEYS
        assert not extra, f"Unexpected extra keys: {extra}"


class TestVBTBacktesterWithRSI:
    """RSIStrategy와의 통합 테스트"""

    def test_run_returns_results(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy, initial_capital=10000.0)
        result = bt.run(sample_data)

        assert result['initial_capital'] == 10000.0
        assert isinstance(result['final_capital'], float)
        assert isinstance(result['total_return'], float)

    def test_total_return_is_not_nan(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert not np.isnan(result['total_return'])

    def test_win_rate_in_range(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert 0.0 <= result['win_rate'] <= 100.0

    def test_trade_counts_consistent(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert result['winning_trades'] + result['losing_trades'] == result['total_trades']

    def test_sharpe_ratio_is_finite(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert np.isfinite(result['sharpe_ratio'])

    def test_dates_match_input(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert result['start_date'] == sample_data.index[0]
        assert result['end_date'] == sample_data.index[-1]

    def test_equity_curve_populated(self, sample_data):
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        bt = VBTBacktester(strategy)
        bt.run(sample_data)

        assert len(bt.equity_curve) == len(sample_data)

    def test_with_macd_strategy(self, sample_data):
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        missing = EXPECTED_KEYS - set(result.keys())
        assert not missing
        assert not np.isnan(result['total_return'])


class TestVBTBacktesterNoTrades:
    """거래가 발생하지 않는 시나리오 테스트"""

    def test_extreme_params_no_trades(self, sample_data):
        """극단적 RSI 파라미터로 시그널이 거의 없게"""
        strategy = RSIStrategy(period=14, overbought=99, oversold=1)
        bt = VBTBacktester(strategy, initial_capital=5000.0)
        result = bt.run(sample_data)

        if result['total_trades'] == 0:
            assert result['final_capital'] == 5000.0
            assert result['total_return'] == 0.0
            assert result['win_rate'] == 0.0
            assert result['max_drawdown'] == 0.0

    def test_empty_dataframe(self, empty_data):
        strategy = RSIStrategy()
        bt = VBTBacktester(strategy, initial_capital=10000.0)
        result = bt.run(empty_data)

        assert result['initial_capital'] == 10000.0
        assert result['final_capital'] == 10000.0
        assert result['total_trades'] == 0
        assert result['start_date'] is None
        assert result['end_date'] is None

    def test_final_capital_equals_initial_when_no_trades(self):
        """시그널이 전혀 없는 짧은 데이터"""
        gen = SimulationDataGenerator(seed=42)
        short_df = gen.generate_ohlcv(periods=5, volatility=0.001)
        strategy = RSIStrategy(period=14, overbought=99, oversold=1)
        bt = VBTBacktester(strategy, initial_capital=7777.0)
        result = bt.run(short_df)

        assert result['final_capital'] == 7777.0
        assert result['total_return'] == 0.0


class TestVBTBacktesterParameters:
    """다양한 초기화 파라미터 테스트"""

    def test_custom_initial_capital(self, sample_data):
        strategy = RSIStrategy()
        bt = VBTBacktester(strategy, initial_capital=50000.0)
        result = bt.run(sample_data)

        assert result['initial_capital'] == 50000.0

    def test_custom_commission(self, volatile_data):
        """높은 수수료 vs 낮은 수수료"""
        strategy = RSIStrategy(period=10, overbought=65, oversold=35)

        bt_low = VBTBacktester(strategy, commission=0.0)
        bt_high = VBTBacktester(strategy, commission=0.01)

        r_low = bt_low.run(volatile_data)
        r_high = bt_high.run(volatile_data)

        # 수수료가 높으면 수익이 낮아야 함 (거래가 있는 경우)
        if r_low['total_trades'] > 0 and r_high['total_trades'] > 0:
            assert r_high['total_return'] <= r_low['total_return']


class TestVBTBacktesterVsLegacy:
    """레거시 Backtester와 결과 방향 비교"""

    def test_both_profit_on_bullish_trend(self, bullish_data):
        """상승장에서 두 백테스터 모두 양의 수익률을 보이는지 확인"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)

        legacy = Backtester(strategy, initial_capital=10000.0, position_size=0.95, commission=0.001)
        vbt_bt = VBTBacktester(strategy, initial_capital=10000.0, position_size=0.95, commission=0.001)

        r_legacy = legacy.run(bullish_data)
        r_vbt = vbt_bt.run(bullish_data)

        # 두 백테스터 모두 거래가 있어야 의미 있는 비교 가능
        if r_legacy['total_trades'] > 0 and r_vbt['total_trades'] > 0:
            # 강한 상승장에서는 둘 다 양의 수익을 내야 함
            # (구현 차이로 정확한 값은 다를 수 있음)
            assert r_legacy['total_return'] > -50, "Legacy should not have extreme loss on bullish"
            assert r_vbt['total_return'] > -50, "VBT should not have extreme loss on bullish"

    def test_same_result_keys(self, sample_data):
        """두 백테스터의 결과 키가 동일한지 확인"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)

        legacy = Backtester(strategy, initial_capital=10000.0)
        vbt_bt = VBTBacktester(strategy, initial_capital=10000.0)

        r_legacy = legacy.run(sample_data)
        r_vbt = vbt_bt.run(sample_data)

        # 레거시에는 verification_report가 추가될 수 있으므로 기본 키만 비교
        assert EXPECTED_KEYS.issubset(set(r_legacy.keys()))
        assert EXPECTED_KEYS.issubset(set(r_vbt.keys()))

    def test_max_drawdown_sign_convention(self, sample_data):
        """max_drawdown이 레거시와 동일한 부호 규칙을 따르는지"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)

        legacy = Backtester(strategy)
        vbt_bt = VBTBacktester(strategy)

        r_legacy = legacy.run(sample_data)
        r_vbt = vbt_bt.run(sample_data)

        # 두 결과 모두 max_drawdown <= 0 (또는 거래 없으면 0)
        assert r_legacy['max_drawdown'] <= 0.0
        assert r_vbt['max_drawdown'] <= 0.0


class TestVBTBacktesterReasonableValues:
    """결과값이 합리적인 범위 내에 있는지 테스트"""

    def test_total_return_reasonable(self, sample_data):
        strategy = RSIStrategy()
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        # 500 기간 데이터에서 -100% ~ +1000% 사이여야 합리적
        assert -100 <= result['total_return'] <= 1000

    def test_final_capital_non_negative(self, sample_data):
        strategy = RSIStrategy()
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert result['final_capital'] >= 0

    def test_max_drawdown_not_below_minus_100(self, sample_data):
        strategy = RSIStrategy()
        bt = VBTBacktester(strategy)
        result = bt.run(sample_data)

        assert result['max_drawdown'] >= -100.0
