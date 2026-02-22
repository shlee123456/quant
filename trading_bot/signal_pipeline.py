"""
Signal processing pipeline for paper trading.

Extracted from PaperTrader to follow single-responsibility principle.
Handles regime detection, LLM signal filtering, and signal validation.
"""

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from .signal_validator import SignalValidator


logger = logging.getLogger(__name__)


class SignalPipeline:
    """
    Processes raw strategy signals through regime detection,
    LLM filtering, and validation.

    Args:
        regime_detector: Optional RegimeDetector instance
        llm_client: Optional LLMClient instance
        enable_verification: Whether to validate signal values
    """

    def __init__(
        self,
        regime_detector=None,
        llm_client=None,
        enable_verification: bool = False,
    ):
        self.regime_detector = regime_detector
        self.llm_client = llm_client
        self.enable_verification = enable_verification
        self._signal_validator = SignalValidator()

    def process(
        self,
        signal: int,
        symbol: str,
        df,
        info: Dict[str, Any],
        timestamp: datetime,
        positions: Dict[str, float],
        capital: float,
        initial_capital: float,
        strategy_name: str,
        db=None,
        session_id: Optional[str] = None,
    ) -> Tuple[int, Optional[Any]]:
        """
        Run the signal through the full pipeline.

        Steps:
        1. Validate signal value
        2. Detect market regime (if regime_detector configured)
        3. Filter via LLM (if llm_client configured and signal != 0)

        Args:
            signal: Raw signal from strategy (-1, 0, 1)
            symbol: Trading symbol
            df: OHLCV DataFrame used for regime detection
            info: Indicator info dict from strategy
            timestamp: Current timestamp
            positions: Current positions dict
            capital: Current available capital
            initial_capital: Initial capital for ratio calculation
            strategy_name: Name of the strategy
            db: Optional TradingDatabase for logging
            session_id: Optional session ID for logging

        Returns:
            Tuple of (filtered_signal, regime_result_or_None)
        """
        # 1. Validate signal
        if self.enable_verification:
            if not self._signal_validator.validate_signal_value(signal):
                logger.warning(f"유효하지 않은 시그널 값 [{symbol}]: {signal}")

        # 2. Regime detection
        regime_result = self._detect_regime(symbol, df, timestamp, db, session_id)

        # 3. LLM signal filter
        signal = self._filter_signal_with_llm(
            signal=signal,
            symbol=symbol,
            strategy_name=strategy_name,
            info=info,
            regime_result=regime_result,
            timestamp=timestamp,
            positions=positions,
            capital=capital,
            initial_capital=initial_capital,
            db=db,
            session_id=session_id,
        )

        return signal, regime_result

    def _detect_regime(self, symbol: str, df, timestamp: datetime,
                       db=None, session_id: Optional[str] = None):
        """
        Detect market regime if detector is configured.

        Returns:
            RegimeResult or None
        """
        if not self.regime_detector:
            return None

        try:
            regime_result = self.regime_detector.detect(df)
            if db and session_id:
                regime_dict = asdict(regime_result)
                regime_dict['symbol'] = symbol
                regime_dict['timestamp'] = timestamp
                regime_dict['regime'] = regime_result.regime.value
                db.log_regime(session_id, regime_dict)
            return regime_result
        except Exception as e:
            logger.warning(f"레짐 감지 실패 [{symbol}]: {e}")
            return None

    def _filter_signal_with_llm(
        self,
        signal: int,
        symbol: str,
        strategy_name: str,
        info: Dict[str, Any],
        regime_result,
        timestamp: datetime,
        positions: Dict[str, float],
        capital: float,
        initial_capital: float,
        db=None,
        session_id: Optional[str] = None,
    ) -> int:
        """
        Filter signal through LLM if configured.

        Returns:
            Filtered signal (may be set to 0 if LLM rejects/holds)
        """
        if not self.llm_client or signal == 0:
            return signal

        try:
            regime_info = asdict(regime_result) if regime_result else {}
            if regime_result:
                regime_info['regime'] = regime_result.regime.value

            decision = self.llm_client.filter_signal({
                'signal': signal,
                'symbol': symbol,
                'strategy': strategy_name,
                'indicators': info,
                'regime': regime_info,
                'position_info': {
                    'current_positions': sum(1 for v in positions.values() if v > 0),
                    'capital_pct_used': 1.0 - (capital / initial_capital) if initial_capital > 0 else 0,
                }
            })

            if decision:
                # DB logging
                if db and session_id:
                    db.log_llm_decision(session_id, {
                        'symbol': symbol,
                        'timestamp': timestamp,
                        'decision_type': 'signal_filter',
                        'request_context': {'signal': signal, 'regime': regime_info},
                        'response': {
                            'action': decision.action,
                            'confidence': decision.confidence,
                            'reasoning': decision.reasoning,
                        },
                        'latency_ms': getattr(decision, '_latency_ms', None),
                        'model_name': (
                            self.llm_client.config.signal_model_name
                            if hasattr(self.llm_client, 'config') else None
                        ),
                    })

                if decision.action == 'reject':
                    logger.info(f"LLM 시그널 거부 [{symbol}]: {decision.reasoning}")
                    return 0
                elif decision.action == 'hold':
                    logger.info(f"LLM 시그널 보류 [{symbol}]: {decision.reasoning}")
                    return 0
                # 'execute' -> keep original signal

        except Exception as e:
            logger.warning(f"LLM 시그널 필터 실패 (fail-open) [{symbol}]: {e}")

        return signal
