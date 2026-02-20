"""
Moving Average Crossover Trading Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from trading_bot.strategies.base_strategy import BaseStrategy


class MovingAverageCrossover(BaseStrategy):
    """
    Moving Average Crossover Strategy

    Generates BUY signal when fast MA crosses above slow MA
    Generates SELL signal when fast MA crosses below slow MA
    """

    def __init__(self, fast_period: int = 10, slow_period: int = 30):
        """
        Initialize strategy

        Args:
            fast_period: Period for fast moving average
            slow_period: Period for slow moving average
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        super().__init__(name=f"MA_Crossover_{fast_period}_{slow_period}")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate moving averages and generate signals

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

        # Calculate moving averages
        data['fast_ma'] = data['close'].rolling(window=self.fast_period).mean()
        data['slow_ma'] = data['close'].rolling(window=self.slow_period).mean()

        # Generate signals
        # 1 = BUY, -1 = SELL, 0 = HOLD
        data['signal'] = 0

        # Buy signal: fast MA crosses above slow MA
        data.loc[
            (data['fast_ma'] > data['slow_ma']) &
            (data['fast_ma'].shift(1) <= data['slow_ma'].shift(1)),
            'signal'
        ] = 1

        # Sell signal: fast MA crosses below slow MA
        data.loc[
            (data['fast_ma'] < data['slow_ma']) &
            (data['fast_ma'].shift(1) >= data['slow_ma'].shift(1)),
            'signal'
        ] = -1

        # Position tracking (1 = long, 0 = no position, -1 = short for future)
        data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0)

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
            'fast_ma': last_row['fast_ma'],
            'slow_ma': last_row['slow_ma'],
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
                'fast_ma': row['fast_ma'],
                'slow_ma': row['slow_ma']
            })

        return signals

    def get_entries_exits(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        VBT 호환 진입/청산 Boolean Series 반환

        - entries: Fast MA가 Slow MA를 상향 돌파
        - exits: Fast MA가 Slow MA를 하향 돌파
        """
        if df.empty:
            return pd.Series(dtype=bool), pd.Series(dtype=bool)

        self.validate_dataframe(df)

        fast_ma = df['close'].rolling(window=self.fast_period).mean()
        slow_ma = df['close'].rolling(window=self.slow_period).mean()

        entries = (
            (fast_ma > slow_ma) &
            (fast_ma.shift(1) <= slow_ma.shift(1))
        ).fillna(False).astype(bool)

        exits = (
            (fast_ma < slow_ma) &
            (fast_ma.shift(1) >= slow_ma.shift(1))
        ).fillna(False).astype(bool)

        return entries, exits

    def get_params(self) -> Dict:
        return {
            'fast_period': self.fast_period,
            'slow_period': self.slow_period,
        }

    def get_param_info(self) -> Dict:
        return {
            'fast_period': '빠른 이동평균 기간',
            'slow_period': '느린 이동평균 기간',
        }

    def __str__(self) -> str:
        return f"Moving Average Crossover Strategy (Fast: {self.fast_period}, Slow: {self.slow_period})"
