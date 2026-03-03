"""
Bollinger Bands Trading Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from .base_strategy import BaseStrategy


class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands Trading Strategy

    Generates BUY signal when price crosses below the lower band (oversold)
    Generates SELL signal when price crosses above the upper band (overbought)

    Bollinger Bands consist of:
    - Middle Band: SMA of closing prices
    - Upper Band: Middle Band + (num_std * standard deviation)
    - Lower Band: Middle Band - (num_std * standard deviation)
    """

    def __init__(self, period: int = 20, num_std: float = 2.0):
        """
        Initialize Bollinger Bands strategy

        Args:
            period: Period for SMA and standard deviation calculation (default 20)
            num_std: Number of standard deviations for band width (default 2.0)
        """
        self.period = period
        self.num_std = num_std
        super().__init__(name=f"BollingerBands_{period}_{num_std}")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Bollinger Bands and generate signals

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with indicators and signals
        """
        # Make a copy to avoid modifying original
        data = df.copy()

        if data.empty:
            return data

        self.validate_dataframe(df)

        # Calculate middle band (SMA)
        data['bb_middle'] = data['close'].rolling(window=self.period).mean()

        # Calculate standard deviation
        data['bb_std'] = data['close'].rolling(window=self.period).std()

        # Calculate upper and lower bands
        data['bb_upper'] = data['bb_middle'] + (self.num_std * data['bb_std'])
        data['bb_lower'] = data['bb_middle'] - (self.num_std * data['bb_std'])

        # Calculate %B indicator: (price - lower) / (upper - lower)
        band_width = (data['bb_upper'] - data['bb_lower']).replace(0, np.nan)
        data['bb_percent_b'] = (data['close'] - data['bb_lower']) / band_width

        # Generate signals
        # 1 = BUY, -1 = SELL, 0 = HOLD
        data['signal'] = 0

        # Buy signal: price crosses below the lower band (oversold)
        data.loc[
            (data['close'] < data['bb_lower']) &
            (data['close'].shift(1) >= data['bb_lower'].shift(1)),
            'signal'
        ] = 1

        # Sell signal: price crosses above the upper band (overbought)
        data.loc[
            (data['close'] > data['bb_upper']) &
            (data['close'].shift(1) <= data['bb_upper'].shift(1)),
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
            'bb_upper': last_row['bb_upper'],
            'bb_middle': last_row['bb_middle'],
            'bb_lower': last_row['bb_lower'],
            'bb_percent_b': last_row['bb_percent_b'],
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
                'bb_upper': row['bb_upper'],
                'bb_middle': row['bb_middle'],
                'bb_lower': row['bb_lower'],
                'bb_percent_b': row['bb_percent_b']
            })

        return signals

    def get_entries_exits(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        VBT 호환 진입/청산 Boolean Series 반환

        - entries: 가격이 Lower Band 아래로 교차하는 시점
        - exits: 가격이 Upper Band 위로 교차하는 시점
        """
        if df.empty:
            return pd.Series(dtype=bool), pd.Series(dtype=bool)

        self.validate_dataframe(df)

        close = df['close']
        bb_middle = close.rolling(window=self.period).mean()
        bb_std = close.rolling(window=self.period).std()
        bb_upper = bb_middle + (self.num_std * bb_std)
        bb_lower = bb_middle - (self.num_std * bb_std)

        entries = (
            (close < bb_lower) &
            (close.shift(1) >= bb_lower.shift(1))
        ).fillna(False).astype(bool)

        exits = (
            (close > bb_upper) &
            (close.shift(1) <= bb_upper.shift(1))
        ).fillna(False).astype(bool)

        return entries, exits

    def get_params(self) -> Dict:
        return {
            'period': self.period,
            'num_std': self.num_std,
        }

    def get_param_info(self) -> Dict:
        return {
            'period': 'SMA 및 표준편차 계산 기간',
            'num_std': '밴드 폭 표준편차 배수',
        }

    def __str__(self) -> str:
        return f"Bollinger Bands Strategy (Period: {self.period}, Std: {self.num_std})"
