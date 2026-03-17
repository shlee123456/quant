"""
Signal processing pipeline for paper trading.

Extracted from PaperTrader to follow single-responsibility principle.
Handles regime detection, LLM signal filtering, context-based filtering,
and signal validation.
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
    context filtering, LLM filtering, and validation.

    Args:
        regime_detector: Optional RegimeDetector instance
        llm_client: Optional LLMClient instance
        enable_verification: Whether to validate signal values
        context_filter_config: Optional config for context-based signal filtering
    """

    def __init__(
        self,
        regime_detector=None,
        llm_client=None,
        enable_verification: bool = False,
        context_filter_config: Optional[Dict] = None,
    ):
        self.regime_detector = regime_detector
        self.llm_client = llm_client
        self.enable_verification = enable_verification
        self._signal_validator = SignalValidator()
        self._context_filter_config = context_filter_config or {}
        self._scorecard_cache: Optional[Dict] = None
        self._scorecard_cache_date: Optional[str] = None

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

        # 2.5 Context filter
        if signal != 0 and self._context_filter_config.get('enabled', False):
            fear_greed_value = self._context_filter_config.get('current_fear_greed')
            signal = self._context_filter(signal, symbol, regime_result, fear_greed_value)

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

    def _context_filter(
        self,
        signal: int,
        symbol: str,
        regime_result,
        fear_greed_value: Optional[float] = None,
    ) -> int:
        """적중률 기반 조건부 매매 필터.

        데이터 부족 시 필터링 안 함 (pass-through).

        필터 로직:
        1. generate_scorecard() 캐시 (일 1회 갱신)
        2. data_coverage.sufficient == False → pass-through
        3. 현재 F&G 구간의 적중률 < min_accuracy → 시그널 → 0
        4. 현재 종목의 적중률 < min_accuracy → 시그널 → 0
        5. 해당 구간/종목의 샘플 < min_sample_size → 해당 조건 필터 스킵

        Args:
            signal: Current signal (-1 or 1, never 0)
            symbol: Trading symbol
            regime_result: RegimeResult from detector (unused, reserved)
            fear_greed_value: Current Fear & Greed index value (0-100)

        Returns:
            Filtered signal (original or 0 if rejected)
        """
        try:
            min_accuracy = self._context_filter_config.get('min_accuracy', 35.0)
            min_sample_size = self._context_filter_config.get('min_sample_size', 5)

            # 1. Scorecard 캐시 (일 1회 갱신)
            today = datetime.now().strftime('%Y-%m-%d')
            if self._scorecard_cache_date != today or self._scorecard_cache is None:
                from .signal_tracker import SignalTracker
                tracker = SignalTracker()
                self._scorecard_cache = tracker.generate_scorecard(today)
                self._scorecard_cache_date = today
                logger.info(f"Context filter: 성적표 갱신 ({today})")

            scorecard = self._scorecard_cache

            # 2. 데이터 부족 → pass-through
            data_coverage = scorecard.get('data_coverage', {})
            if not data_coverage.get('sufficient', False):
                logger.debug("Context filter: 데이터 부족, 필터 스킵 (pass-through)")
                return signal

            # 3. F&G 구간 적중률 검사
            if fear_greed_value is not None:
                from .signal_tracker import SignalTracker
                fg_zone = SignalTracker._get_fear_greed_zone(fear_greed_value)
                if fg_zone:
                    fg_stats = scorecard.get('by_fear_greed_zone', {}).get(fg_zone, {})
                    fg_total = fg_stats.get('total', 0)
                    fg_accuracy = fg_stats.get('accuracy_pct')

                    if fg_total >= min_sample_size and fg_accuracy is not None:
                        if fg_accuracy < min_accuracy:
                            logger.info(
                                f"Context filter: F&G {fg_zone} 구간 적중률 "
                                f"{fg_accuracy:.1f}% < {min_accuracy}%, 시그널 거부 [{symbol}]"
                            )
                            return 0

            # 4. 종목별 적중률 검사
            symbol_stats = scorecard.get('by_symbol', {}).get(symbol, {})
            sym_total = symbol_stats.get('total', 0)
            sym_accuracy = symbol_stats.get('accuracy_pct')

            if sym_total >= min_sample_size and sym_accuracy is not None:
                if sym_accuracy < min_accuracy:
                    logger.info(
                        f"Context filter: {symbol} 적중률 "
                        f"{sym_accuracy:.1f}% < {min_accuracy}%, 시그널 거부"
                    )
                    return 0

        except Exception as e:
            logger.warning(f"Context filter 오류 (fail-open) [{symbol}]: {e}")

        return signal

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
