"""
플랫 마켓 (모든 가격 동일) 환경에서 전략 divide-by-zero 방어 테스트

모든 OHLCV 값이 동일할 때 ZeroDivisionError, inf, NaN 전파 없이
5개 전략이 정상 실행되는지 확인합니다.
"""

import pandas as pd
import numpy as np
import pytest


def make_flat_ohlcv(price: float = 100.0, rows: int = 100) -> pd.DataFrame:
    """모든 가격이 동일한 OHLCV DataFrame 생성"""
    idx = pd.date_range("2024-01-01", periods=rows, freq="h")
    return pd.DataFrame(
        {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1000.0,
        },
        index=idx,
    )


class TestRSIFlatMarket:
    def test_no_error(self):
        from trading_bot.strategies.rsi_strategy import RSIStrategy

        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        df = make_flat_ohlcv()
        result = strategy.calculate_indicators(df)

        assert "signal" in result.columns
        assert "position" in result.columns
        assert not np.isinf(result["signal"]).any()
        assert not np.isinf(result["position"]).any()

    def test_get_current_signal(self):
        from trading_bot.strategies.rsi_strategy import RSIStrategy

        strategy = RSIStrategy()
        df = make_flat_ohlcv()
        signal, info = strategy.get_current_signal(df)
        assert signal in (-1, 0, 1)


class TestMACDFlatMarket:
    def test_no_error(self):
        from trading_bot.strategies.macd_strategy import MACDStrategy

        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        df = make_flat_ohlcv()
        result = strategy.calculate_indicators(df)

        assert "signal" in result.columns
        assert "position" in result.columns
        assert not np.isinf(result["signal"]).any()
        assert not np.isinf(result["position"]).any()

    def test_get_current_signal(self):
        from trading_bot.strategies.macd_strategy import MACDStrategy

        strategy = MACDStrategy()
        df = make_flat_ohlcv()
        signal, info = strategy.get_current_signal(df)
        assert signal in (-1, 0, 1)


class TestBollingerBandsFlatMarket:
    def test_no_error(self):
        from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy

        strategy = BollingerBandsStrategy(period=20, num_std=2.0)
        df = make_flat_ohlcv()
        result = strategy.calculate_indicators(df)

        assert "signal" in result.columns
        assert "position" in result.columns
        assert not np.isinf(result["signal"]).any()
        assert not np.isinf(result["position"]).any()

    def test_bb_percent_b_no_inf(self):
        """band_width가 0일 때 bb_percent_b가 inf가 아닌 NaN이어야 함"""
        from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy

        strategy = BollingerBandsStrategy(period=20, num_std=2.0)
        df = make_flat_ohlcv()
        result = strategy.calculate_indicators(df)

        # bb_percent_b should be NaN (not inf) when band_width is 0
        bb_valid = result["bb_percent_b"].dropna()
        assert not np.isinf(bb_valid).any()

    def test_get_current_signal(self):
        from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy

        strategy = BollingerBandsStrategy()
        df = make_flat_ohlcv()
        signal, info = strategy.get_current_signal(df)
        assert signal in (-1, 0, 1)


class TestStochasticFlatMarket:
    def test_no_error(self):
        from trading_bot.strategies.stochastic_strategy import StochasticStrategy

        strategy = StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)
        df = make_flat_ohlcv()
        result = strategy.calculate_indicators(df)

        assert "signal" in result.columns
        assert "position" in result.columns
        assert not np.isinf(result["signal"]).any()
        assert not np.isinf(result["position"]).any()

    def test_stochastic_k_no_inf(self):
        """highest_high - lowest_low가 0일 때 stochastic_k가 inf가 아닌 NaN이어야 함"""
        from trading_bot.strategies.stochastic_strategy import StochasticStrategy

        strategy = StochasticStrategy()
        df = make_flat_ohlcv()
        result = strategy.calculate_indicators(df)

        k_valid = result["stochastic_k"].dropna()
        assert not np.isinf(k_valid).any()

    def test_get_current_signal(self):
        from trading_bot.strategies.stochastic_strategy import StochasticStrategy

        strategy = StochasticStrategy()
        df = make_flat_ohlcv()
        signal, info = strategy.get_current_signal(df)
        assert signal in (-1, 0, 1)


class TestRSIMACDComboFlatMarket:
    def test_no_error(self):
        from trading_bot.strategies.rsi_macd_combo_strategy import RSIMACDComboStrategy

        strategy = RSIMACDComboStrategy()
        df = make_flat_ohlcv()
        result = strategy.calculate_indicators(df)

        assert "signal" in result.columns
        assert "position" in result.columns
        assert not np.isinf(result["signal"]).any()
        assert not np.isinf(result["position"]).any()

    def test_get_current_signal(self):
        from trading_bot.strategies.rsi_macd_combo_strategy import RSIMACDComboStrategy

        strategy = RSIMACDComboStrategy()
        df = make_flat_ohlcv()
        signal, info = strategy.get_current_signal(df)
        assert signal in (-1, 0, 1)
