"""
Market Regime Detection Module

Classifies market conditions into regimes:
- BULLISH: Strong uptrend (ADX > 25, positive trend)
- BEARISH: Strong downtrend (ADX > 25, negative trend)
- SIDEWAYS: Low trend strength (ADX <= 25, low volatility)
- VOLATILE: High volatility regardless of trend
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"


@dataclass
class RegimeResult:
    regime: MarketRegime
    confidence: float  # 0.0 ~ 1.0
    adx: float
    trend_direction: float  # positive = up, negative = down
    volatility_percentile: float  # 0 ~ 100
    recommended_strategies: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)


class RegimeDetector:
    """Detects market regime from OHLCV data"""

    # Strategy recommendations per regime
    STRATEGY_MAP = {
        MarketRegime.BULLISH: ['MACD Strategy', 'RSI+MACD Combo Strategy'],
        MarketRegime.BEARISH: ['RSI Strategy', 'Bollinger Bands'],
        MarketRegime.SIDEWAYS: ['RSI Strategy', 'Bollinger Bands'],
        MarketRegime.VOLATILE: ['Bollinger Bands'],
    }

    def __init__(self, adx_period: int = 14, ma_period: int = 50, vol_window: int = 100):
        self.adx_period = adx_period
        self.ma_period = ma_period
        self.vol_window = vol_window

    def detect(self, df: pd.DataFrame) -> RegimeResult:
        """Detect regime for the last bar"""
        min_periods = max(self.adx_period * 2, self.ma_period, self.vol_window) + 10
        if len(df) < min_periods:
            return RegimeResult(
                regime=MarketRegime.SIDEWAYS,
                confidence=0.3,
                adx=0.0,
                trend_direction=0.0,
                volatility_percentile=50.0,
                recommended_strategies=self.STRATEGY_MAP[MarketRegime.SIDEWAYS],
                details={'reason': 'insufficient_data', 'data_length': len(df), 'min_required': min_periods}
            )

        adx_series = self._calculate_adx(df, self.adx_period)
        trend_series = self._calculate_trend_direction(df, self.ma_period)
        vol_pct_series = self._calculate_volatility_percentile(df, self.vol_window)

        last_adx = adx_series.iloc[-1]
        last_trend = trend_series.iloc[-1]
        last_vol_pct = vol_pct_series.iloc[-1]

        regime, confidence = self._classify_regime(last_adx, last_trend, last_vol_pct)

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            adx=float(last_adx) if not pd.isna(last_adx) else 0.0,
            trend_direction=float(last_trend) if not pd.isna(last_trend) else 0.0,
            volatility_percentile=float(last_vol_pct) if not pd.isna(last_vol_pct) else 50.0,
            recommended_strategies=self.get_recommended_strategies(regime),
            details={
                'adx_period': self.adx_period,
                'ma_period': self.ma_period,
                'vol_window': self.vol_window,
            }
        )

    def detect_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect regime for each bar, return DataFrame with regime labels"""
        result = df.copy()

        min_periods = max(self.adx_period * 2, self.ma_period, self.vol_window) + 10

        adx_series = self._calculate_adx(df, self.adx_period)
        trend_series = self._calculate_trend_direction(df, self.ma_period)
        vol_pct_series = self._calculate_volatility_percentile(df, self.vol_window)

        regimes = []
        confidences = []

        for i in range(len(df)):
            adx_val = adx_series.iloc[i]
            trend_val = trend_series.iloc[i]
            vol_val = vol_pct_series.iloc[i]

            if i < min_periods or pd.isna(adx_val) or pd.isna(trend_val) or pd.isna(vol_val):
                regimes.append(None)
                confidences.append(None)
            else:
                regime, conf = self._classify_regime(adx_val, trend_val, vol_val)
                regimes.append(regime.value)
                confidences.append(conf)

        result['regime'] = regimes
        result['regime_confidence'] = confidences
        result['adx'] = adx_series
        result['trend_direction'] = trend_series
        result['volatility_percentile'] = vol_pct_series

        return result

    def get_recommended_strategies(self, regime: MarketRegime) -> List[str]:
        """Get recommended strategies for a regime"""
        return self.STRATEGY_MAP.get(regime, self.STRATEGY_MAP[MarketRegime.SIDEWAYS])

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate ADX using Wilder's smoothing (pandas EWM)
        ADX measures trend strength (0-100), direction agnostic
        """
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional Movement
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
            index=df.index
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
            index=df.index
        )

        # Wilder's smoothing (EWM with alpha = 1/period)
        alpha = 1.0 / period
        atr = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        plus_di_smooth = plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        minus_di_smooth = minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

        # Handle division by zero in ATR
        safe_atr = atr.replace(0, np.nan)
        plus_di = 100 * (plus_di_smooth / safe_atr)
        minus_di = 100 * (minus_di_smooth / safe_atr)

        # ADX
        di_sum = plus_di + minus_di
        safe_di_sum = di_sum.replace(0, np.nan)
        dx = (plus_di - minus_di).abs() / safe_di_sum * 100
        adx = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

        return adx

    def _calculate_trend_direction(self, df: pd.DataFrame, ma_period: int = 50) -> pd.Series:
        """
        Calculate trend direction using price position relative to MA and MA slope
        Returns: positive = uptrend, negative = downtrend
        """
        close = df['close'].astype(float)
        ma = close.rolling(window=ma_period).mean()

        # Normalized distance from MA (positive = above, negative = below)
        safe_ma = ma.replace(0, np.nan)
        distance = (close - ma) / safe_ma * 100

        # MA slope (rate of change over 5 periods)
        ma_slope = ma.pct_change(periods=5) * 100

        # Combined trend direction (weighted)
        trend = distance * 0.7 + ma_slope * 0.3

        return trend

    def _calculate_volatility_percentile(self, df: pd.DataFrame, window: int = 100) -> pd.Series:
        """
        Calculate current volatility as a percentile of recent history
        Returns: 0-100 percentile
        """
        close = df['close'].astype(float)
        returns = close.pct_change()

        # Rolling standard deviation of returns (20-period)
        current_vol = returns.rolling(window=20).std()

        # Percentile rank within the lookback window
        result = pd.Series(np.nan, index=df.index, dtype=float)

        for i in range(window, len(df)):
            window_data = current_vol.iloc[max(0, i - window):i + 1].dropna()
            if len(window_data) < 10:
                result.iloc[i] = 50.0
                continue
            current_val = current_vol.iloc[i]
            if pd.isna(current_val):
                result.iloc[i] = 50.0
                continue
            pct = (window_data < current_val).sum() / len(window_data) * 100
            result.iloc[i] = pct

        return result

    def _classify_regime(self, adx: float, trend_direction: float, vol_percentile: float) -> Tuple[MarketRegime, float]:
        """
        Classify market regime based on indicators

        Returns: (regime, confidence)
        """
        # Handle NaN
        if pd.isna(adx) or pd.isna(trend_direction) or pd.isna(vol_percentile):
            return MarketRegime.SIDEWAYS, 0.3

        # Rule 1: High volatility -> VOLATILE
        if vol_percentile > 75:
            confidence = min(0.5 + (vol_percentile - 75) / 50, 0.95)
            return MarketRegime.VOLATILE, confidence

        # Rule 2: Strong trend (ADX > 25) with direction
        if adx > 25:
            if trend_direction > 0:
                confidence = min(0.5 + (adx - 25) / 50, 0.95)
                return MarketRegime.BULLISH, confidence
            else:
                confidence = min(0.5 + (adx - 25) / 50, 0.95)
                return MarketRegime.BEARISH, confidence

        # Rule 3: Low trend strength -> SIDEWAYS
        confidence = min(0.5 + (25 - adx) / 50, 0.90)
        return MarketRegime.SIDEWAYS, confidence
