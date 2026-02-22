"""
MACD (Moving Average Convergence Divergence) Trading Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from .base_strategy import BaseStrategy


class MACDStrategy(BaseStrategy):
    """
    MACD Trading Strategy

    Generates BUY signal when MACD line crosses above signal line (golden cross)
    Generates SELL signal when MACD line crosses below signal line (dead cross)
    """

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        """
        Initialize MACD strategy

        Args:
            fast_period: Period for fast EMA (default 12)
            slow_period: Period for slow EMA (default 26)
            signal_period: Period for signal line EMA (default 9)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        super().__init__(name=f"MACD_{fast_period}_{slow_period}_{signal_period}")

    def _calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """
        Calculate Exponential Moving Average

        Args:
            prices: Series of prices
            period: EMA period

        Returns:
            Series of EMA values
        """
        return prices.ewm(span=period, adjust=False).mean()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate MACD indicators and generate signals

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with indicators and signals
        """
        # Handle empty DataFrame
        if df.empty:
            return df.copy()

        self.validate_dataframe(df)

        # Make a copy to avoid modifying original
        data = df.copy()

        # Calculate MACD components
        # MACD Line = 12-day EMA - 26-day EMA
        fast_ema = self._calculate_ema(data['close'], self.fast_period)
        slow_ema = self._calculate_ema(data['close'], self.slow_period)
        data['macd_line'] = fast_ema - slow_ema

        # Signal Line = 9-day EMA of MACD Line
        data['signal_line'] = self._calculate_ema(data['macd_line'], self.signal_period)

        # MACD Histogram = MACD Line - Signal Line
        data['macd_histogram'] = data['macd_line'] - data['signal_line']

        # Generate signals
        # 1 = BUY, -1 = SELL, 0 = HOLD
        data['signal'] = 0

        # Buy signal: MACD line crosses above signal line (golden cross)
        data.loc[
            (data['macd_line'] > data['signal_line']) &
            (data['macd_line'].shift(1) <= data['signal_line'].shift(1)),
            'signal'
        ] = 1

        # Sell signal: MACD line crosses below signal line (dead cross)
        data.loc[
            (data['macd_line'] < data['signal_line']) &
            (data['macd_line'].shift(1) >= data['signal_line'].shift(1)),
            'signal'
        ] = -1

        # Position tracking (1 = long, 0 = flat)
        # Buy signal (1) -> position = 1
        # Sell signal (-1) -> position = 0
        # Hold (0) -> maintain previous position
        data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0).clip(lower=0).astype(int)

        return data

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """
        Get the most recent signal

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Tuple of (signal, info_dict)
            signal: 1 (BUY), -1 (SELL), 0 (HOLD)
            info_dict: Additional information about the signal
        """
        data = self.calculate_indicators(df)

        if data.empty:
            return 0, {}

        last_row = data.iloc[-1]

        info = {
            'timestamp': last_row.name,
            'close': last_row['close'],
            'macd_line': last_row['macd_line'],
            'signal_line': last_row['signal_line'],
            'macd_histogram': last_row['macd_histogram'],
            'signal': int(last_row['signal']),
            'position': int(last_row['position'])
        }

        return int(last_row['signal']), info

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """
        Get all trading signals from historical data

        Args:
            df: DataFrame with OHLCV data

        Returns:
            List of signal dictionaries
        """
        data = self.calculate_indicators(df)

        # Filter only actual signals (not holds)
        signals_df = data[data['signal'] != 0].copy()

        signals = []
        for idx, row in signals_df.iterrows():
            signals.append({
                'timestamp': idx,
                'signal': 'BUY' if row['signal'] == 1 else 'SELL',
                'price': row['close'],
                'macd_line': row['macd_line'],
                'signal_line': row['signal_line'],
                'macd_histogram': row['macd_histogram']
            })

        return signals

    def get_entries_exits(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        VBT 호환 진입/청산 Boolean Series 반환

        - entries: MACD 골든크로스 (MACD Line이 Signal Line을 상향 돌파)
        - exits: MACD 데드크로스 (MACD Line이 Signal Line을 하향 돌파)
        """
        if df.empty:
            return pd.Series(dtype=bool), pd.Series(dtype=bool)

        self.validate_dataframe(df)

        fast_ema = self._calculate_ema(df['close'], self.fast_period)
        slow_ema = self._calculate_ema(df['close'], self.slow_period)
        macd_line = fast_ema - slow_ema
        signal_line = self._calculate_ema(macd_line, self.signal_period)

        entries = (
            (macd_line > signal_line) &
            (macd_line.shift(1) <= signal_line.shift(1))
        ).fillna(False).astype(bool)

        exits = (
            (macd_line < signal_line) &
            (macd_line.shift(1) >= signal_line.shift(1))
        ).fillna(False).astype(bool)

        return entries, exits

    def get_params(self) -> Dict:
        return {
            'fast_period': self.fast_period,
            'slow_period': self.slow_period,
            'signal_period': self.signal_period,
        }

    def get_param_info(self) -> Dict:
        return {
            'fast_period': '빠른 EMA 기간',
            'slow_period': '느린 EMA 기간',
            'signal_period': '시그널 라인 EMA 기간',
        }

    def __str__(self) -> str:
        return f"MACD Strategy (Fast: {self.fast_period}, Slow: {self.slow_period}, Signal: {self.signal_period})"
