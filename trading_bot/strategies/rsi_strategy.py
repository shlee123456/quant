"""
RSI (Relative Strength Index) Trading Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from ..logging_config import get_strategy_logger
from .base_strategy import BaseStrategy

logger = get_strategy_logger()


class RSIStrategy(BaseStrategy):
    """
    RSI Trading Strategy

    Generates BUY signal when RSI crosses below oversold threshold (default 30)
    Generates SELL signal when RSI crosses above overbought threshold (default 70)
    """

    def __init__(self, period: int = 14, overbought: float = 70, oversold: float = 30):
        """
        Initialize RSI strategy

        Args:
            period: Period for RSI calculation (default 14)
            overbought: RSI level considered overbought (default 70)
            oversold: RSI level considered oversold (default 30)
        """
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
        super().__init__(name=f"RSI_{period}_{oversold}_{overbought}")

        logger.debug(f"Initialized {self.name} - Overbought: {overbought}, Oversold: {oversold}")

    def _calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """
        Calculate RSI indicator

        Args:
            prices: Series of closing prices

        Returns:
            Series of RSI values
        """
        # Calculate price changes
        delta = prices.diff()

        # Separate gains and losses
        gains = delta.copy()
        losses = delta.copy()
        gains[gains < 0] = 0
        losses[losses > 0] = 0
        losses = abs(losses)

        # Calculate average gains and losses using exponential moving average
        avg_gains = gains.ewm(span=self.period, min_periods=self.period, adjust=False).mean()
        avg_losses = losses.ewm(span=self.period, min_periods=self.period, adjust=False).mean()

        # Calculate RS and RSI
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate RSI and generate signals

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

        # Calculate RSI
        data['rsi'] = self._calculate_rsi(data['close'])

        # Generate signals
        # 1 = BUY, -1 = SELL, 0 = HOLD
        data['signal'] = 0

        # Buy signal: RSI crosses below oversold level (indicating oversold condition)
        data.loc[
            (data['rsi'] < self.oversold) &
            (data['rsi'].shift(1) >= self.oversold),
            'signal'
        ] = 1

        # Sell signal: RSI crosses above overbought level (indicating overbought condition)
        data.loc[
            (data['rsi'] > self.overbought) &
            (data['rsi'].shift(1) <= self.overbought),
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
            'rsi': last_row['rsi'],
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
                'rsi': row['rsi']
            })

        return signals

    def get_entries_exits(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        VBT 호환 진입/청산 Boolean Series 반환

        - entries: RSI가 oversold 아래로 교차하는 시점
        - exits: RSI가 overbought 위로 교차하는 시점
        """
        if df.empty:
            return pd.Series(dtype=bool), pd.Series(dtype=bool)

        self.validate_dataframe(df)

        rsi = self._calculate_rsi(df['close'])

        entries = (
            (rsi < self.oversold) &
            (rsi.shift(1) >= self.oversold)
        ).fillna(False).astype(bool)

        exits = (
            (rsi > self.overbought) &
            (rsi.shift(1) <= self.overbought)
        ).fillna(False).astype(bool)

        return entries, exits

    def get_params(self) -> Dict:
        return {
            'period': self.period,
            'overbought': self.overbought,
            'oversold': self.oversold,
        }

    def get_param_info(self) -> Dict:
        return {
            'period': 'RSI 계산 기간',
            'overbought': '과매수 임계값',
            'oversold': '과매도 임계값',
        }

    def __str__(self) -> str:
        return f"RSI Strategy (Period: {self.period}, Overbought: {self.overbought}, Oversold: {self.oversold})"
