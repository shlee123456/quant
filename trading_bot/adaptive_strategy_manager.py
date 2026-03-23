"""
Adaptive Strategy Manager - 레짐 기반 전략 자동 전환 + 파라미터 적응 통합 관리자

시장 레짐에 따라 최적의 전략을 자동 선택하고,
변동성 기반으로 파라미터를 동적 조정합니다.

Features:
- 레짐 감지 결과에 따른 전략 자동 전환
- 쿨다운 기반 잦은 전환 방지
- 최소 신뢰도 필터
- ParameterAdapter 통합 (선택적)
- 전환 이력 추적
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type

import pandas as pd

from trading_bot.regime_detector import RegimeDetector, RegimeResult
from trading_bot.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class AdaptiveStrategyManager:
    """레짐 기반 전략 자동 전환 + 파라미터 적응 통합 관리자"""

    def __init__(
        self,
        strategy_class_map: Dict[str, Type],
        regime_detector: RegimeDetector,
        initial_strategy: Optional[BaseStrategy] = None,
        regime_strategy_map: Optional[Dict[str, List[str]]] = None,
        default_params: Optional[Dict[str, Dict[str, Any]]] = None,
        min_confidence: float = 0.6,
        cooldown_bars: int = 5,
        parameter_adapter: Optional[Any] = None,
        enabled: bool = True,
    ):
        """
        Args:
            strategy_class_map: 전략 표시명 -> 전략 클래스 매핑 (예: 'RSI Strategy' -> RSIStrategy)
            regime_detector: 레짐 감지기 인스턴스
            initial_strategy: 초기 전략 인스턴스 (None이면 첫 evaluate() 전까지 None)
            regime_strategy_map: 커스텀 레짐 -> 전략명 매핑 (None이면 RegimeDetector.STRATEGY_MAP 사용)
            default_params: 전략명 -> 기본 파라미터 매핑 (예: {'RSI Strategy': {'period': 14}})
            min_confidence: 전환을 위한 최소 레짐 신뢰도 (0.0~1.0)
            cooldown_bars: 전환 후 재전환 방지 최소 iteration 수
            parameter_adapter: ParameterAdapter 인스턴스 (None이면 파라미터 적응 비활성)
            enabled: False면 evaluate()가 현재 전략을 그대로 반환
        """
        self._strategy_class_map = strategy_class_map
        self._regime_detector = regime_detector
        self._current_strategy = initial_strategy
        self._current_strategy_key: Optional[str] = None
        self._regime_strategy_map = regime_strategy_map
        self._default_params = default_params or {}
        self._min_confidence = min_confidence
        self._cooldown_bars = cooldown_bars
        self._parameter_adapter = parameter_adapter
        self._enabled = enabled

        self._bars_since_switch: int = cooldown_bars  # 초기값: 쿨다운 충족 상태
        self._last_regime_result: Optional[RegimeResult] = None
        self._switch_history: List[Dict] = []

        # initial_strategy가 주어진 경우, strategy_class_map에서 키를 역추적
        if initial_strategy is not None:
            self._current_strategy_key = self._find_strategy_key(initial_strategy)

    def _find_strategy_key(self, strategy: BaseStrategy) -> Optional[str]:
        """전략 인스턴스의 클래스를 strategy_class_map에서 찾아 키 반환"""
        strategy_type = type(strategy)
        for key, cls in self._strategy_class_map.items():
            if cls is not None and cls is strategy_type:
                return key
        return None

    def _get_regime_strategy_map(self) -> Dict:
        """레짐별 추천 전략 매핑 반환 (커스텀 또는 기본값)"""
        if self._regime_strategy_map:
            return self._regime_strategy_map
        return RegimeDetector.STRATEGY_MAP

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[BaseStrategy], Optional[RegimeResult], bool]:
        """
        df로 레짐 감지 후 전략 전환 판단.

        Args:
            df: OHLCV DataFrame

        Returns:
            (strategy, regime_result, did_switch)
            - strategy: 현재 또는 새로 전환된 전략 인스턴스
            - regime_result: 레짐 감지 결과 (SignalPipeline 이중 감지 방지용)
            - did_switch: 전략이 전환되었는지 여부
        """
        if not self._enabled:
            return self._current_strategy, None, False

        # 1. 레짐 감지
        regime_result = self._regime_detector.detect(df)
        self._last_regime_result = regime_result

        # 2. 신뢰도 필터
        if regime_result.confidence < self._min_confidence:
            logger.debug(
                f"레짐 신뢰도 부족: {regime_result.confidence:.2f} < {self._min_confidence:.2f}, 전환 안 함"
            )
            return self._current_strategy, regime_result, False

        # 3. 쿨다운 체크
        if self._bars_since_switch < self._cooldown_bars:
            logger.debug(
                f"쿨다운 중: {self._bars_since_switch}/{self._cooldown_bars} bars, 전환 안 함"
            )
            return self._current_strategy, regime_result, False

        # 4. 추천 전략 확인
        strategy_map = self._get_regime_strategy_map()
        recommended = strategy_map.get(regime_result.regime, [])
        if not recommended:
            return self._current_strategy, regime_result, False

        # 5. 현재 전략과 비교 (첫 번째 추천 전략과 비교)
        target_key = None
        for rec_name in recommended:
            if rec_name in self._strategy_class_map and self._strategy_class_map[rec_name] is not None:
                target_key = rec_name
                break

        if target_key is None:
            logger.warning(f"추천 전략 {recommended}이 strategy_class_map에 없음")
            return self._current_strategy, regime_result, False

        # 현재 전략과 동일하면 전환 불필요
        if target_key == self._current_strategy_key:
            # 파라미터 적응만 수행 (전략 전환 없이)
            if self._parameter_adapter and self._current_strategy:
                self._apply_parameter_adaptation(regime_result)
            return self._current_strategy, regime_result, False

        # 6. 전략 전환
        old_key = self._current_strategy_key
        old_strategy = self._current_strategy
        params = self._default_params.get(target_key, {})

        try:
            strategy_cls = self._strategy_class_map[target_key]
            new_strategy = strategy_cls(**params)
        except Exception as e:
            logger.error(f"전략 생성 실패 [{target_key}]: {e}")
            return self._current_strategy, regime_result, False

        # 7. 파라미터 적응 (전환과 동시 적용)
        if self._parameter_adapter:
            adapted = self._parameter_adapter.adapt(regime_result)
            if adapted.get('strategy_params_changed', False):
                try:
                    adapted_params = adapted['strategy_params']
                    new_strategy = type(new_strategy)(**adapted_params)
                    logger.info(f"파라미터 적응 적용: {adapted.get('adjustments', [])}")
                except Exception as e:
                    logger.warning(f"파라미터 적응 실패, 기본 파라미터 사용: {e}")

        self._current_strategy = new_strategy
        self._current_strategy_key = target_key
        self._bars_since_switch = 0

        # 8. 이력 기록
        switch_record = {
            'timestamp': datetime.now().isoformat(),
            'from_strategy': old_key,
            'to_strategy': target_key,
            'regime': regime_result.regime.value,
            'confidence': regime_result.confidence,
            'volatility_percentile': regime_result.volatility_percentile,
        }
        self._switch_history.append(switch_record)

        logger.info(
            f"전략 전환: {old_key} -> {target_key} "
            f"(레짐: {regime_result.regime.value}, 신뢰도: {regime_result.confidence:.2f})"
        )

        return self._current_strategy, regime_result, True

    def _apply_parameter_adaptation(self, regime_result: RegimeResult) -> None:
        """현재 전략에 파라미터 적응 적용 (전략 전환 없이)"""
        if not self._parameter_adapter or not self._current_strategy:
            return

        adapted = self._parameter_adapter.adapt(regime_result)
        if not adapted.get('strategy_params_changed', False):
            return

        try:
            adapted_params = adapted['strategy_params']
            new_strategy = type(self._current_strategy)(**adapted_params)
            self._current_strategy = new_strategy
            logger.info(f"파라미터 적응 적용 (전환 없음): {adapted.get('adjustments', [])}")
        except Exception as e:
            logger.warning(f"파라미터 적응 실패: {e}")

    def tick(self) -> None:
        """iteration마다 호출 -- 쿨다운 카운터 진행"""
        self._bars_since_switch += 1

    @property
    def current_strategy(self) -> Optional[BaseStrategy]:
        """현재 활성 전략 인스턴스"""
        return self._current_strategy

    @property
    def current_strategy_key(self) -> Optional[str]:
        """현재 활성 전략의 STRATEGY_CLASS_MAP 키"""
        return self._current_strategy_key

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def get_switch_history(self) -> List[Dict]:
        """전략 전환 이력 반환"""
        return list(self._switch_history)

    def get_last_regime_result(self) -> Optional[RegimeResult]:
        """마지막 레짐 감지 결과 반환"""
        return self._last_regime_result
