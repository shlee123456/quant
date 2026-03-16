"""
BaseStrategy - 모든 트레이딩 전략의 추상 기본 클래스

모든 전략은 이 클래스를 상속하여 공통 인터페이스를 구현합니다.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
import logging


REQUIRED_OHLCV_COLUMNS = {'open', 'high', 'low', 'close', 'volume'}

VALID_SIGNALS = {-1, 0, 1}


class BaseStrategy(ABC):
    """
    모든 트레이딩 전략의 추상 기본 클래스

    하위 클래스는 반드시 다음 메서드를 구현해야 합니다:
    - calculate_indicators(df): 지표 계산 및 시그널 생성
    - get_current_signal(df): 현재 시그널 반환
    - get_all_signals(df): 모든 시그널 이벤트 반환
    """

    def __init__(self, name: str):
        """
        전략 초기화

        Args:
            name: 전략 이름 (예: "RSI_14_30_70")
        """
        self.name = name
        self.supports_short: bool = False
        self.logger = logging.getLogger(f"trading_bot.strategies.{self.__class__.__name__}")

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        지표 계산 및 시그널 생성

        Args:
            df: OHLCV 데이터 (columns: open, high, low, close, volume)

        Returns:
            DataFrame with:
            - 원본 OHLCV 컬럼
            - 지표 컬럼 (전략별)
            - 'signal': 1 (BUY), -1 (SELL), 0 (HOLD)
            - 'position': 1 (long), 0 (flat)
        """
        pass

    @abstractmethod
    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """
        현재 시그널 반환

        Args:
            df: OHLCV 데이터

        Returns:
            Tuple of (signal, info_dict)
            signal: 1 (BUY), -1 (SELL), 0 (HOLD)
            info_dict: 시그널 관련 추가 정보
        """
        pass

    @abstractmethod
    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """
        모든 시그널 이벤트 반환

        Args:
            df: OHLCV 데이터

        Returns:
            List of signal dictionaries
        """
        pass

    @abstractmethod
    def get_entries_exits(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        VBT 호환 진입/청산 Boolean Series 반환

        entries=True인 시점에서 매수, exits=True인 시점에서 매도.
        교차(crossing) 시점만 True이며, 지속 구간은 False.
        NaN 행은 False로 처리.

        Args:
            df: OHLCV 데이터 (columns: open, high, low, close, volume)

        Returns:
            Tuple of (entries, exits)
            - entries: Boolean pd.Series (True = BUY 시점)
            - exits: Boolean pd.Series (True = SELL 시점)
        """
        pass

    def validate_signal(self, signal: int) -> bool:
        """
        시그널 값이 유효한지 검증

        Args:
            signal: 검증할 시그널 값

        Returns:
            True if signal is -1, 0, or 1
        """
        return signal in VALID_SIGNALS

    def validate_dataframe(self, df: pd.DataFrame) -> None:
        """
        DataFrame에 필수 OHLCV 컬럼이 존재하는지 검증

        Args:
            df: 검증할 DataFrame

        Raises:
            ValueError: 필수 컬럼이 누락된 경우
        """
        missing = REQUIRED_OHLCV_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(
                f"필수 OHLCV 컬럼 누락: {sorted(missing)}. "
                f"필요한 컬럼: {sorted(REQUIRED_OHLCV_COLUMNS)}"
            )

    def apply_position_tracking(self, data: pd.DataFrame, allow_short: bool = False) -> pd.DataFrame:
        """signal 컬럼에서 position 컬럼을 생성 (공통 로직).

        BUY(1) → position=1, SELL(-1) → position=0 (또는 -1 if allow_short), HOLD(0) → 이전 유지.

        Args:
            data: signal 컬럼이 포함된 DataFrame
            allow_short: True면 숏 포지션(음수) 허용, False면 0 이하로 클리핑
        """
        position = (
            data['signal']
            .replace(0, np.nan)
            .ffill()
            .fillna(0)
        )
        if not allow_short:
            position = position.clip(lower=0)
        data['position'] = position.astype(int)
        return data

    def get_params(self) -> Dict:
        """
        현재 전략 파라미터 반환

        하위 클래스에서 오버라이드하여 전략별 파라미터를 반환합니다.

        Returns:
            파라미터 딕셔너리
        """
        return {}

    def get_param_info(self) -> Dict:
        """
        파라미터 설명 반환

        하위 클래스에서 오버라이드하여 각 파라미터의 설명을 반환합니다.

        Returns:
            {파라미터명: 설명} 딕셔너리
        """
        return {}

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"

    def __repr__(self) -> str:
        params = self.get_params()
        if params:
            param_str = ", ".join(f"{k}={v}" for k, v in params.items())
            return f"{self.__class__.__name__}({param_str})"
        return f"{self.__class__.__name__}(name={self.name!r})"
