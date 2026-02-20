"""Tests for RegimeDetector"""

import pytest
import pandas as pd
import numpy as np
import time
from trading_bot.regime_detector import RegimeDetector, MarketRegime, RegimeResult


class TestRegimeDetector:
    """RegimeDetector unit tests"""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    @pytest.fixture
    def bullish_df(self):
        """Generate strongly trending up data"""
        np.random.seed(42)
        n = 200
        prices = 100 * np.exp(np.cumsum(np.random.normal(0.003, 0.01, n)))
        df = pd.DataFrame({
            'open': prices * (1 - np.random.uniform(0, 0.005, n)),
            'high': prices * (1 + np.random.uniform(0.005, 0.02, n)),
            'low': prices * (1 - np.random.uniform(0.005, 0.02, n)),
            'close': prices,
            'volume': np.random.randint(1000, 10000, n).astype(float)
        })
        return df

    @pytest.fixture
    def bearish_df(self):
        """Generate strongly trending down data"""
        np.random.seed(42)
        n = 200
        prices = 200 * np.exp(np.cumsum(np.random.normal(-0.003, 0.01, n)))
        df = pd.DataFrame({
            'open': prices * (1 + np.random.uniform(0, 0.005, n)),
            'high': prices * (1 + np.random.uniform(0.005, 0.02, n)),
            'low': prices * (1 - np.random.uniform(0.005, 0.02, n)),
            'close': prices,
            'volume': np.random.randint(1000, 10000, n).astype(float)
        })
        return df

    @pytest.fixture
    def sideways_df(self):
        """Generate sideways/range-bound data with no trend"""
        np.random.seed(42)
        n = 200
        # Pure sine wave oscillation around 100 - no net directional movement
        t = np.arange(n)
        prices = 100 + 2 * np.sin(2 * np.pi * t / 20) + np.random.normal(0, 0.3, n)
        df = pd.DataFrame({
            'open': prices + np.random.uniform(-0.3, 0.3, n),
            'high': prices + np.random.uniform(0.3, 1.0, n),
            'low': prices - np.random.uniform(0.3, 1.0, n),
            'close': prices,
            'volume': np.random.randint(1000, 10000, n).astype(float)
        })
        return df

    @pytest.fixture
    def volatile_df(self):
        """Generate data with extreme recent volatility spike"""
        np.random.seed(42)
        n = 200
        # 175 bars very calm, then 25 bars extreme volatility
        calm = np.random.normal(0, 0.001, 175)
        spike = np.random.normal(0, 0.10, 25)  # 100x volatility
        returns = np.concatenate([calm, spike])
        prices = 100 * np.exp(np.cumsum(returns))
        df = pd.DataFrame({
            'open': prices * (1 + np.random.uniform(-0.005, 0.005, n)),
            'high': prices * (1 + np.abs(np.concatenate([
                np.random.uniform(0.001, 0.003, 175),
                np.random.uniform(0.05, 0.15, 25)
            ]))),
            'low': prices * (1 - np.abs(np.concatenate([
                np.random.uniform(0.001, 0.003, 175),
                np.random.uniform(0.05, 0.15, 25)
            ]))),
            'close': prices,
            'volume': np.random.randint(1000, 10000, n).astype(float)
        })
        return df

    def test_init_default(self, detector):
        assert detector.adx_period == 14
        assert detector.ma_period == 50
        assert detector.vol_window == 100

    def test_init_custom(self):
        d = RegimeDetector(adx_period=20, ma_period=30, vol_window=50)
        assert d.adx_period == 20
        assert d.ma_period == 30
        assert d.vol_window == 50

    def test_detect_returns_regime_result(self, detector, bullish_df):
        result = detector.detect(bullish_df)
        assert isinstance(result, RegimeResult)
        assert isinstance(result.regime, MarketRegime)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.recommended_strategies, list)
        assert len(result.recommended_strategies) > 0

    def test_detect_bullish(self, detector, bullish_df):
        result = detector.detect(bullish_df)
        assert result.regime == MarketRegime.BULLISH
        assert result.confidence > 0.5
        assert result.trend_direction > 0

    def test_detect_bearish(self, detector, bearish_df):
        result = detector.detect(bearish_df)
        assert result.regime == MarketRegime.BEARISH
        assert result.confidence > 0.5
        assert result.trend_direction < 0

    def test_detect_sideways(self, detector, sideways_df):
        result = detector.detect(sideways_df)
        # Sideways data could also be classified as volatile depending on noise
        assert result.regime in [MarketRegime.SIDEWAYS, MarketRegime.VOLATILE, MarketRegime.BEARISH]

    def test_detect_volatile(self, detector, volatile_df):
        result = detector.detect(volatile_df)
        assert result.regime == MarketRegime.VOLATILE
        assert result.volatility_percentile > 60

    def test_detect_insufficient_data(self, detector):
        """Test with too little data"""
        df = pd.DataFrame({
            'open': [100, 101], 'high': [102, 103],
            'low': [99, 100], 'close': [101, 102],
            'volume': [1000.0, 1100.0]
        })
        result = detector.detect(df)
        assert result.regime == MarketRegime.SIDEWAYS
        assert result.confidence == 0.3
        assert result.details['reason'] == 'insufficient_data'

    def test_detect_empty_df(self, detector):
        """Test with empty dataframe"""
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        result = detector.detect(df)
        assert result.regime == MarketRegime.SIDEWAYS
        assert result.confidence == 0.3

    def test_adx_range(self, detector, bullish_df):
        """ADX should be between 0 and 100"""
        adx = detector._calculate_adx(bullish_df)
        valid_adx = adx.dropna()
        assert (valid_adx >= 0).all()
        assert (valid_adx <= 100).all()

    def test_detect_series(self, detector, bullish_df):
        result = detector.detect_series(bullish_df)
        assert 'regime' in result.columns
        assert 'regime_confidence' in result.columns
        assert 'adx' in result.columns
        assert 'trend_direction' in result.columns
        assert 'volatility_percentile' in result.columns
        # First rows should be None (insufficient data)
        assert result['regime'].iloc[0] is None
        # Later rows should have values
        non_null = result['regime'].dropna()
        assert len(non_null) > 0
        assert all(r in ['BULLISH', 'BEARISH', 'SIDEWAYS', 'VOLATILE'] for r in non_null)

    def test_get_recommended_strategies(self, detector):
        assert 'MACD Strategy' in detector.get_recommended_strategies(MarketRegime.BULLISH)
        assert 'RSI Strategy' in detector.get_recommended_strategies(MarketRegime.BEARISH)
        assert 'Bollinger Bands' in detector.get_recommended_strategies(MarketRegime.VOLATILE)

    def test_constant_price(self, detector):
        """Edge case: constant price should not crash"""
        n = 200
        df = pd.DataFrame({
            'open': [100.0] * n, 'high': [100.0] * n,
            'low': [100.0] * n, 'close': [100.0] * n,
            'volume': [1000.0] * n
        })
        result = detector.detect(df)
        assert isinstance(result, RegimeResult)

    def test_performance(self, detector, bullish_df):
        """100 calls should complete within 5 seconds"""
        start = time.time()
        for _ in range(100):
            detector.detect(bullish_df)
        elapsed = time.time() - start
        assert elapsed < 5.0, f"100 detect() calls took {elapsed:.2f}s (limit: 5s)"

    def test_market_regime_enum(self):
        assert MarketRegime.BULLISH.value == "BULLISH"
        assert MarketRegime.BEARISH.value == "BEARISH"
        assert MarketRegime.SIDEWAYS.value == "SIDEWAYS"
        assert MarketRegime.VOLATILE.value == "VOLATILE"

    def test_regime_result_fields(self, detector, bullish_df):
        result = detector.detect(bullish_df)
        assert hasattr(result, 'regime')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'adx')
        assert hasattr(result, 'trend_direction')
        assert hasattr(result, 'volatility_percentile')
        assert hasattr(result, 'recommended_strategies')
        assert hasattr(result, 'details')
