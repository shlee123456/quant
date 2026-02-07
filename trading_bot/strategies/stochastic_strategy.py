"""
Stochastic Oscillator Trading Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


class StochasticStrategy:
    """
    Stochastic Oscillator Trading Strategy

    The Stochastic Oscillator compares a particular closing price to a range of prices
    over a certain period. It consists of two lines:
    - %K line: The main line showing the current position relative to the high-low range
    - %D line: A moving average of %K (signal line)

    Generates BUY signal when %K crosses above %D while in oversold zone
    Generates SELL signal when %K crosses below %D while in overbought zone
    """

    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
        overbought: float = 80,
        oversold: float = 20
    ):
        """
        Initialize Stochastic Oscillator strategy

        Args:
            k_period: Period for %K calculation (default 14)
            d_period: Period for %D (SMA of %K) calculation (default 3)
            overbought: Level considered overbought (default 80)
            oversold: Level considered oversold (default 20)
        """
        self.k_period = k_period
        self.d_period = d_period
        self.overbought = overbought
        self.oversold = oversold
        self.name = f"Stochastic_{k_period}_{d_period}_{oversold}_{overbought}"

    def _calculate_stochastic(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Stochastic Oscillator %K and %D lines

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with stochastic_k and stochastic_d columns
        """
        data = df.copy()

        # Calculate highest high and lowest low over the period
        data['lowest_low'] = data['low'].rolling(window=self.k_period).min()
        data['highest_high'] = data['high'].rolling(window=self.k_period).max()

        # Calculate %K: (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
        data['stochastic_k'] = (
            (data['close'] - data['lowest_low']) /
            (data['highest_high'] - data['lowest_low']) * 100
        )

        # Calculate %D: SMA of %K
        data['stochastic_d'] = data['stochastic_k'].rolling(window=self.d_period).mean()

        return data

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Stochastic Oscillator and generate signals

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with indicators and signals
        """
        # Make a copy to avoid modifying original
        data = df.copy()

        if data.empty:
            return data

        # Calculate Stochastic Oscillator
        data = self._calculate_stochastic(data)

        # Generate signals
        # 1 = BUY, -1 = SELL, 0 = HOLD
        data['signal'] = 0

        # Buy signal: %K crosses above %D while in oversold zone
        data.loc[
            (data['stochastic_k'] > data['stochastic_d']) &
            (data['stochastic_k'].shift(1) <= data['stochastic_d'].shift(1)) &
            (data['stochastic_k'] < self.oversold),
            'signal'
        ] = 1

        # Sell signal: %K crosses below %D while in overbought zone
        data.loc[
            (data['stochastic_k'] < data['stochastic_d']) &
            (data['stochastic_k'].shift(1) >= data['stochastic_d'].shift(1)) &
            (data['stochastic_k'] > self.overbought),
            'signal'
        ] = -1

        # Position tracking (1 = long, 0 = no position)
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
            'stochastic_k': last_row['stochastic_k'],
            'stochastic_d': last_row['stochastic_d'],
            'signal': int(last_row['signal']),
            'position': int(last_row['position']),
            'overbought_level': self.overbought,
            'oversold_level': self.oversold
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
                'stochastic_k': row['stochastic_k'],
                'stochastic_d': row['stochastic_d']
            })

        return signals

    def __str__(self) -> str:
        return f"Stochastic Strategy (K: {self.k_period}, D: {self.d_period}, OB: {self.overbought}, OS: {self.oversold})"
