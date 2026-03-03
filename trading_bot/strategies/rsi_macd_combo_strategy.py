"""
RSI + MACD Combo Trading Strategy

원리: RSI 과매도 구간에서 MACD 골든크로스 확인 후 진입
시그널:
  - BUY: RSI < oversold AND MACD 골든크로스
  - SELL: RSI > overbought OR MACD 데드크로스
"""
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from ..logging_config import get_strategy_logger
from .base_strategy import BaseStrategy

logger = get_strategy_logger()


class RSIMACDComboStrategy(BaseStrategy):
    """
    RSI + MACD 복합 전략

    RSI의 과매도/과매수 구간을 필터로 사용하고,
    MACD의 골든크로스/데드크로스로 진입/청산 타이밍 결정

    Parameters:
        rsi_period (int): RSI 계산 기간 (기본 14)
        rsi_oversold (float): RSI 과매도 임계값 (기본 35)
        rsi_overbought (float): RSI 과매수 임계값 (기본 70)
        macd_fast (int): MACD 빠른 EMA 기간 (기본 12)
        macd_slow (int): MACD 느린 EMA 기간 (기본 26)
        macd_signal (int): MACD 시그널 라인 기간 (기본 9)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 35,
        rsi_overbought: float = 70,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        super().__init__(name=f"RSI_MACD_Combo_{rsi_period}_{rsi_oversold}_{rsi_overbought}")

        logger.debug(
            f"Initialized {self.name} - "
            f"RSI: {rsi_oversold}/{rsi_overbought}, "
            f"MACD: {macd_fast}/{macd_slow}/{macd_signal}"
        )

    def _calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """RSI 계산"""
        delta = prices.diff()
        gains = delta.copy()
        losses = delta.copy()
        gains[gains < 0] = 0
        losses[losses > 0] = 0
        losses = abs(losses)

        avg_gains = gains.ewm(span=self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
        avg_losses = losses.ewm(span=self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()

        # avg_losses==0 & avg_gains>0 → RSI=100, both==0 → RSI=NaN
        rs = avg_gains / avg_losses.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        fill = pd.Series(np.where(avg_gains > 0, 100.0, np.nan), index=rsi.index)
        rsi = rsi.fillna(fill)

        return rsi

    def _calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """EMA 계산"""
        return prices.ewm(span=period, adjust=False).mean()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        지표 계산 및 시그널 생성

        Args:
            df: OHLCV 데이터

        Returns:
            DataFrame with indicators and signals
        """
        if df.empty:
            return df.copy()

        self.validate_dataframe(df)

        data = df.copy()

        # 1. RSI 계산
        data['rsi'] = self._calculate_rsi(data['close'])

        # 2. MACD 계산
        fast_ema = self._calculate_ema(data['close'], self.macd_fast)
        slow_ema = self._calculate_ema(data['close'], self.macd_slow)
        data['macd_line'] = fast_ema - slow_ema
        data['signal_line'] = self._calculate_ema(data['macd_line'], self.macd_signal)
        data['macd_histogram'] = data['macd_line'] - data['signal_line']

        # 3. 시그널 생성
        data['signal'] = 0

        # BUY 조건: RSI < oversold AND MACD 골든크로스
        buy_condition = (
            (data['rsi'] < self.rsi_oversold) &
            (data['macd_line'] > data['signal_line']) &
            (data['macd_line'].shift(1) <= data['signal_line'].shift(1))
        )
        data.loc[buy_condition, 'signal'] = 1

        # SELL 조건: RSI > overbought OR MACD 데드크로스
        sell_condition_rsi = (data['rsi'] > self.rsi_overbought)
        sell_condition_macd = (
            (data['macd_line'] < data['signal_line']) &
            (data['macd_line'].shift(1) >= data['signal_line'].shift(1))
        )
        data.loc[sell_condition_rsi | sell_condition_macd, 'signal'] = -1

        # 4. 포지션 추적
        data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0).clip(lower=0).astype(int)

        return data

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """
        현재 시그널 반환

        Args:
            df: OHLCV 데이터

        Returns:
            Tuple of (signal, info_dict)
        """
        data = self.calculate_indicators(df)

        if data.empty:
            return 0, {}

        last_row = data.iloc[-1]

        info = {
            'timestamp': last_row.name,
            'close': last_row['close'],
            'rsi': last_row['rsi'],
            'macd_line': last_row['macd_line'],
            'signal_line': last_row['signal_line'],
            'macd_histogram': last_row['macd_histogram'],
            'signal': int(last_row['signal']),
            'position': int(last_row['position']),
            'rsi_oversold': self.rsi_oversold,
            'rsi_overbought': self.rsi_overbought
        }

        return int(last_row['signal']), info

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """
        모든 시그널 이벤트 반환

        Args:
            df: OHLCV 데이터

        Returns:
            List of signal dictionaries
        """
        data = self.calculate_indicators(df)

        signals_df = data[data['signal'] != 0].copy()

        signals = []
        for idx, row in signals_df.iterrows():
            signals.append({
                'timestamp': idx,
                'signal': 'BUY' if row['signal'] == 1 else 'SELL',
                'price': row['close'],
                'rsi': row['rsi'],
                'macd_line': row['macd_line'],
                'signal_line': row['signal_line'],
                'macd_histogram': row['macd_histogram']
            })

        return signals

    def get_entries_exits(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        VBT 호환 진입/청산 Boolean Series 반환

        - entries: RSI < oversold AND MACD 골든크로스
        - exits: RSI > overbought OR MACD 데드크로스
        """
        if df.empty:
            return pd.Series(dtype=bool), pd.Series(dtype=bool)

        self.validate_dataframe(df)

        rsi = self._calculate_rsi(df['close'])
        fast_ema = self._calculate_ema(df['close'], self.macd_fast)
        slow_ema = self._calculate_ema(df['close'], self.macd_slow)
        macd_line = fast_ema - slow_ema
        signal_line = self._calculate_ema(macd_line, self.macd_signal)

        macd_golden_cross = (
            (macd_line > signal_line) &
            (macd_line.shift(1) <= signal_line.shift(1))
        )

        entries = (
            (rsi < self.rsi_oversold) &
            macd_golden_cross
        ).fillna(False).astype(bool)

        sell_rsi = (
            (rsi > self.rsi_overbought) &
            (rsi.shift(1) <= self.rsi_overbought)
        )
        sell_macd = (
            (macd_line < signal_line) &
            (macd_line.shift(1) >= signal_line.shift(1))
        )

        exits = (sell_rsi | sell_macd).fillna(False).astype(bool)

        return entries, exits

    def get_params(self) -> Dict:
        return {
            'rsi_period': self.rsi_period,
            'rsi_oversold': self.rsi_oversold,
            'rsi_overbought': self.rsi_overbought,
            'macd_fast': self.macd_fast,
            'macd_slow': self.macd_slow,
            'macd_signal': self.macd_signal,
        }

    def get_param_info(self) -> Dict:
        return {
            'rsi_period': 'RSI 계산 기간',
            'rsi_oversold': 'RSI 과매도 임계값',
            'rsi_overbought': 'RSI 과매수 임계값',
            'macd_fast': 'MACD 빠른 EMA 기간',
            'macd_slow': 'MACD 느린 EMA 기간',
            'macd_signal': 'MACD 시그널 라인 기간',
        }

    def __str__(self) -> str:
        return (
            f"RSI+MACD Combo Strategy "
            f"(RSI: {self.rsi_period}/{self.rsi_oversold}/{self.rsi_overbought}, "
            f"MACD: {self.macd_fast}/{self.macd_slow}/{self.macd_signal})"
        )
