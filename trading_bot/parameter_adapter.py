"""
Parameter Adapter - 변동성 기반 동적 파라미터 조정

레짐 감지 결과의 volatility_percentile을 기반으로
전략 파라미터와 리스크 파라미터를 동적으로 조정합니다.

조정 규칙 (선형 보간):
| volatility_percentile | RSI overbought | RSI oversold | SL   | TP   |
|-----------------------|----------------|--------------|------|------|
| 0 (극저)              | 65             | 35           | 2%   | 4%   |
| 50 (보통)             | 기본값         | 기본값       | 기본 | 기본 |
| 100 (극고)            | 85             | 15           | 8%   | 15%  |
"""

import logging
import math
from typing import Any, Dict, List, Tuple

from trading_bot.regime_detector import RegimeResult

logger = logging.getLogger(__name__)

# RSI 관련 파라미터 키 (overbought/oversold)
_RSI_OVERBOUGHT_KEYS = {'overbought', 'rsi_overbought'}
_RSI_OVERSOLD_KEYS = {'oversold', 'rsi_oversold'}


class ParameterAdapter:
    """변동성 기반 동적 파라미터 조정"""

    def __init__(
        self,
        base_strategy_params: Dict[str, Any],
        base_stop_loss_pct: float = 0.05,
        base_take_profit_pct: float = 0.10,
        rsi_overbought_range: Tuple[float, float] = (65.0, 85.0),
        rsi_oversold_range: Tuple[float, float] = (15.0, 35.0),
        stop_loss_range: Tuple[float, float] = (0.02, 0.08),
        take_profit_range: Tuple[float, float] = (0.04, 0.15),
        enabled: bool = True,
    ):
        """
        Args:
            base_strategy_params: 기본 전략 파라미터 (예: {'period': 14, 'overbought': 70, 'oversold': 30})
            base_stop_loss_pct: 기본 손절 비율 (예: 0.05 = 5%)
            base_take_profit_pct: 기본 익절 비율 (예: 0.10 = 10%)
            rsi_overbought_range: (극저변동성 값, 극고변동성 값) RSI 과매수 범위
            rsi_oversold_range: (극고변동성 값, 극저변동성 값) RSI 과매도 범위 -- 주의: low=15, high=35
            stop_loss_range: (극저변동성 값, 극고변동성 값) 손절 범위
            take_profit_range: (극저변동성 값, 극고변동성 값) 익절 범위
            enabled: False면 adapt()가 기본 파라미터를 그대로 반환
        """
        self._base_strategy_params = dict(base_strategy_params)
        self._base_stop_loss_pct = base_stop_loss_pct
        self._base_take_profit_pct = base_take_profit_pct
        self._rsi_overbought_range = rsi_overbought_range
        self._rsi_oversold_range = rsi_oversold_range
        self._stop_loss_range = stop_loss_range
        self._take_profit_range = take_profit_range
        self._enabled = enabled

    def adapt(self, regime_result: RegimeResult) -> Dict:
        """
        volatility_percentile 기반 파라미터 조정.

        Args:
            regime_result: 레짐 감지 결과

        Returns:
            {
                'strategy_params': {...},           # 조정된 전략 파라미터
                'strategy_params_changed': bool,    # 전략 파라미터 변경 여부
                'stop_loss_pct': float,             # 조정된 손절 비율
                'take_profit_pct': float,           # 조정된 익절 비율
                'adjustments': [str, ...],          # 변경 내역 설명 리스트
            }
        """
        adjustments: List[str] = []
        strategy_params = dict(self._base_strategy_params)
        strategy_params_changed = False

        vol_pct = regime_result.volatility_percentile

        # NaN 또는 비활성화 시 기본 파라미터 그대로 반환
        if not self._enabled or vol_pct is None or (isinstance(vol_pct, float) and math.isnan(vol_pct)):
            return {
                'strategy_params': strategy_params,
                'strategy_params_changed': False,
                'stop_loss_pct': self._base_stop_loss_pct,
                'take_profit_pct': self._base_take_profit_pct,
                'adjustments': [],
            }

        # 1. RSI 관련 파라미터 조정
        for key in list(strategy_params.keys()):
            if key in _RSI_OVERBOUGHT_KEYS:
                base_val = self._base_strategy_params[key]
                new_val = self._interpolate(
                    vol_pct, base_val,
                    self._rsi_overbought_range[0],  # low vol -> tight (65)
                    self._rsi_overbought_range[1],   # high vol -> wide (85)
                )
                if new_val != base_val:
                    strategy_params[key] = round(new_val, 1)
                    strategy_params_changed = True
                    adjustments.append(f"{key}: {base_val} -> {strategy_params[key]}")

            elif key in _RSI_OVERSOLD_KEYS:
                base_val = self._base_strategy_params[key]
                # 과매도: 저변동성 -> 넓게(35), 고변동성 -> 좁게(15)
                new_val = self._interpolate(
                    vol_pct, base_val,
                    self._rsi_oversold_range[1],  # low vol -> wide (35)
                    self._rsi_oversold_range[0],   # high vol -> tight (15)
                )
                if new_val != base_val:
                    strategy_params[key] = round(new_val, 1)
                    strategy_params_changed = True
                    adjustments.append(f"{key}: {base_val} -> {strategy_params[key]}")

        # 2. 리스크 파라미터 조정
        stop_loss_pct = self._interpolate(
            vol_pct, self._base_stop_loss_pct,
            self._stop_loss_range[0],  # low vol -> tight SL
            self._stop_loss_range[1],  # high vol -> wide SL
        )
        take_profit_pct = self._interpolate(
            vol_pct, self._base_take_profit_pct,
            self._take_profit_range[0],  # low vol -> tight TP
            self._take_profit_range[1],  # high vol -> wide TP
        )

        if stop_loss_pct != self._base_stop_loss_pct:
            adjustments.append(f"stop_loss: {self._base_stop_loss_pct:.3f} -> {stop_loss_pct:.3f}")
        if take_profit_pct != self._base_take_profit_pct:
            adjustments.append(f"take_profit: {self._base_take_profit_pct:.3f} -> {take_profit_pct:.3f}")

        return {
            'strategy_params': strategy_params,
            'strategy_params_changed': strategy_params_changed,
            'stop_loss_pct': stop_loss_pct,
            'take_profit_pct': take_profit_pct,
            'adjustments': adjustments,
        }

    def _interpolate(self, vol_pct: float, base: float, low: float, high: float) -> float:
        """
        변동성 백분위 기반 선형 보간.

        vol_pct 0~25  -> low에서 base로 보간
        vol_pct 25~75 -> base 유지
        vol_pct 75~100 -> base에서 high로 보간

        결과는 [min(low,high), max(low,high)] 범위로 클램핑.

        Args:
            vol_pct: 변동성 백분위 (0~100)
            base: 기본값 (vol 25~75에서 사용)
            low: 극저변동성(0) 값
            high: 극고변동성(100) 값

        Returns:
            보간된 값
        """
        # 범위 클램핑
        vol_pct = max(0.0, min(100.0, vol_pct))

        if vol_pct <= 25.0:
            # 0~25: low -> base
            t = vol_pct / 25.0
            result = low + (base - low) * t
        elif vol_pct <= 75.0:
            # 25~75: base 유지
            result = base
        else:
            # 75~100: base -> high
            t = (vol_pct - 75.0) / 25.0
            result = base + (high - base) * t

        # 클램핑 (low과 high 사이)
        lower_bound = min(low, high)
        upper_bound = max(low, high)
        return max(lower_bound, min(upper_bound, result))

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def base_strategy_params(self) -> Dict[str, Any]:
        return dict(self._base_strategy_params)

    @property
    def base_stop_loss_pct(self) -> float:
        return self._base_stop_loss_pct

    @property
    def base_take_profit_pct(self) -> float:
        return self._base_take_profit_pct
