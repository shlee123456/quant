"""
Auto Optimizer - 주기적 전략 자동 최적화

walk_forward_optimize()를 사용하여 최근 데이터에 대해 전략 파라미터를 최적화하고,
개선이 임계값 이상일 경우 프리셋을 자동 업데이트합니다.

Usage:
    from trading_bot.auto_optimizer import AutoOptimizer
    from trading_bot.optimizer import StrategyOptimizer
    from trading_bot.strategy_presets import StrategyPresetManager

    optimizer = StrategyOptimizer()
    preset_manager = StrategyPresetManager()
    auto = AutoOptimizer(
        optimizer=optimizer,
        preset_manager=preset_manager,
        strategy_class_map=STRATEGY_CLASS_MAP,
    )
    summary = auto.run(broker, target_presets=["프리셋A", "프리셋B"])
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Type, Any, Tuple

import pandas as pd

from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategy_presets import StrategyPresetManager

logger = logging.getLogger(__name__)


class AutoOptimizer:
    """주기적으로 최근 데이터로 전략 최적화 후 프리셋 자동 업데이트"""

    DEFAULT_PARAM_GRIDS = {
        'RSI Strategy': {
            'period': [7, 14, 21],
            'overbought': [65, 70, 75, 80],
            'oversold': [20, 25, 30, 35],
        },
        'MACD Strategy': {
            'fast_period': [8, 12, 16],
            'slow_period': [21, 26, 30],
            'signal_period': [6, 9, 12],
        },
        'Bollinger Bands': {
            'period': [10, 20, 30],
            'num_std': [1.5, 2.0, 2.5, 3.0],
        },
        'Stochastic': {
            'k_period': [5, 14, 21],
            'd_period': [3, 5, 7],
            'overbought': [70, 80],
            'oversold': [20, 30],
        },
        'RSI+MACD Combo Strategy': {
            'rsi_period': [10, 14, 20],
            'rsi_overbought': [65, 70, 75],
            'rsi_oversold': [25, 30, 35],
            'macd_fast': [8, 12],
            'macd_slow': [21, 26],
            'macd_signal': [7, 9],
        },
    }

    def __init__(
        self,
        optimizer: StrategyOptimizer,
        preset_manager: StrategyPresetManager,
        strategy_class_map: Dict[str, Type],
        lookback_days: int = 90,
        min_bars: int = 500,
        min_trades: int = 10,
        min_sharpe: float = 0.3,
        max_drawdown_limit: float = -25.0,
        improvement_threshold_pct: float = 5.0,
    ):
        """
        AutoOptimizer 초기화.

        Args:
            optimizer: StrategyOptimizer 인스턴스
            preset_manager: StrategyPresetManager 인스턴스
            strategy_class_map: 전략명 -> 전략 클래스 매핑 (예: {'RSI Strategy': RSIStrategy})
            lookback_days: 최적화에 사용할 과거 데이터 일수
            min_bars: 최소 필요 데이터 바 수
            min_trades: 최소 필요 거래 횟수
            min_sharpe: 최소 Sharpe Ratio 임계값
            max_drawdown_limit: 최대 허용 드로다운 (음수, 예: -25.0)
            improvement_threshold_pct: 프리셋 업데이트를 위한 최소 개선율 (%)
        """
        self.optimizer = optimizer
        self.preset_manager = preset_manager
        self.strategy_class_map = strategy_class_map
        self.lookback_days = lookback_days
        self.min_bars = min_bars
        self.min_trades = min_trades
        self.min_sharpe = min_sharpe
        self.max_drawdown_limit = max_drawdown_limit
        self.improvement_threshold_pct = improvement_threshold_pct

    def run(self, broker: Any, target_presets: List[str]) -> Dict:
        """
        대상 프리셋들에 대해 자동 최적화를 실행합니다.

        1. 프리셋 목록 순회
        2. 각 프리셋의 심볼에 대해 최근 lookback_days 데이터 fetch
        3. walk_forward_optimize() 실행 (과적합 방지)
        4. 결과 검증 (min_trades, min_sharpe, max_drawdown_limit)
        5. 현재 대비 improvement_threshold_pct 이상 개선 시에만 적용
        6. save_preset()으로 업데이트 (load -> 수정 -> save 패턴)

        Args:
            broker: BaseBroker 인스턴스 (fetch_ohlcv 메서드 필요)
            target_presets: 최적화할 프리셋 이름 리스트

        Returns:
            프리셋별 최적화 결과 요약 딕셔너리
        """
        summary = {
            'timestamp': datetime.now().isoformat(),
            'presets': {},
            'total_presets': len(target_presets),
            'updated': 0,
            'skipped': 0,
            'failed': 0,
        }

        for preset_name in target_presets:
            result = self._optimize_preset(broker, preset_name)
            summary['presets'][preset_name] = result

            if result['status'] == 'updated':
                summary['updated'] += 1
            elif result['status'] == 'skipped':
                summary['skipped'] += 1
            else:
                summary['failed'] += 1

        logger.info(
            f"자동 최적화 완료: {summary['updated']}개 업데이트, "
            f"{summary['skipped']}개 건너뜀, {summary['failed']}개 실패"
        )
        return summary

    def _optimize_preset(self, broker: Any, preset_name: str) -> Dict:
        """단일 프리셋에 대해 최적화를 실행합니다."""
        try:
            # 1. 프리셋 로드
            preset = self.preset_manager.load_preset(preset_name)
            if preset is None:
                logger.warning(f"프리셋 '{preset_name}' 찾을 수 없음")
                return {'status': 'failed', 'reason': 'preset_not_found'}

            strategy_name = preset['strategy']

            # 2. 전략 클래스 확인
            strategy_class = self.strategy_class_map.get(strategy_name)
            if strategy_class is None:
                logger.warning(f"전략 클래스 매핑 없음: '{strategy_name}'")
                return {'status': 'failed', 'reason': 'strategy_class_not_found'}

            # 3. 파라미터 그리드 확인
            param_grid = self._get_param_grid(strategy_name)
            if param_grid is None:
                logger.warning(f"파라미터 그리드 없음: '{strategy_name}'")
                return {'status': 'failed', 'reason': 'no_param_grid'}

            # 4. 데이터 수집
            symbols = preset.get('symbols', [])
            if not symbols:
                logger.warning(f"프리셋 '{preset_name}'에 심볼 없음")
                return {'status': 'failed', 'reason': 'no_symbols'}

            df = self._fetch_data(broker, symbols)
            if df is None or len(df) < self.min_bars:
                bars = len(df) if df is not None else 0
                logger.warning(
                    f"데이터 부족: {bars}바 (최소 {self.min_bars}바 필요)"
                )
                return {'status': 'failed', 'reason': 'insufficient_data', 'bars': bars}

            # 5. Walk-Forward 최적화
            logger.info(
                f"[{preset_name}] walk_forward_optimize 시작 "
                f"(전략: {strategy_name}, 데이터: {len(df)}바)"
            )
            wf_result = self.optimizer.walk_forward_optimize(
                strategy_class=strategy_class,
                df=df,
                param_grid=param_grid,
                metric='sharpe_ratio',
                use_vbt=True,
            )

            # 6. 결과 검증
            if not wf_result['oos_results']:
                logger.warning(f"[{preset_name}] OOS 결과 없음")
                return {'status': 'failed', 'reason': 'no_oos_results'}

            # OOS 결과에서 대표 메트릭 추출
            backtest_metrics = self._aggregate_oos_metrics(wf_result)

            is_valid, reject_reason = self._validate_results(wf_result, backtest_metrics)
            if not is_valid:
                logger.info(f"[{preset_name}] 검증 실패: {reject_reason}")
                return {
                    'status': 'skipped',
                    'reason': f'validation_failed: {reject_reason}',
                    'metrics': backtest_metrics,
                }

            # 7. 현재 파라미터 대비 개선율 계산
            old_params = preset.get('strategy_params', {})
            new_params = self._select_best_params(wf_result)

            # 현재 파라미터로 백테스트하여 비교 기준 마련
            old_metrics = self._backtest_with_params(
                strategy_class, df, old_params
            )
            improvement = self._calculate_improvement(old_metrics, backtest_metrics)

            if improvement < self.improvement_threshold_pct:
                logger.info(
                    f"[{preset_name}] 개선 부족: {improvement:.1f}% "
                    f"(임계값: {self.improvement_threshold_pct}%)"
                )
                return {
                    'status': 'skipped',
                    'reason': 'insufficient_improvement',
                    'improvement_pct': improvement,
                    'old_params': old_params,
                    'new_params': new_params,
                    'old_metrics': old_metrics,
                    'new_metrics': backtest_metrics,
                }

            # 8. 프리셋 업데이트 (load -> 수정 -> save 패턴)
            self._update_preset(preset_name, preset, new_params)

            logger.info(
                f"[{preset_name}] 프리셋 업데이트 완료: "
                f"개선율 {improvement:.1f}%, 새 파라미터: {new_params}"
            )
            return {
                'status': 'updated',
                'improvement_pct': improvement,
                'old_params': old_params,
                'new_params': new_params,
                'old_metrics': old_metrics,
                'new_metrics': backtest_metrics,
                'wf_stability_ratio': wf_result.get('stability_ratio'),
                'wf_parameter_stability': wf_result.get('parameter_stability'),
            }

        except Exception as e:
            logger.error(f"[{preset_name}] 최적화 중 오류: {e}", exc_info=True)
            return {'status': 'failed', 'reason': f'exception: {str(e)}'}

    def _get_param_grid(self, strategy_name: str) -> Optional[Dict[str, List]]:
        """전략명에 해당하는 파라미터 그리드를 반환합니다."""
        return self.DEFAULT_PARAM_GRIDS.get(strategy_name)

    def _fetch_data(
        self, broker: Any, symbols: List[str]
    ) -> Optional[pd.DataFrame]:
        """
        대상 심볼들의 OHLCV 데이터를 수집합니다.

        첫 번째 심볼의 데이터를 대표 데이터로 사용합니다.
        실패 시 다음 심볼을 시도합니다.
        """
        since_ms = int(
            (datetime.now() - timedelta(days=self.lookback_days)).timestamp() * 1000
        )
        limit = max(self.min_bars, self.lookback_days * 2)

        for symbol in symbols:
            try:
                df = broker.fetch_ohlcv(
                    symbol=symbol,
                    timeframe='1d',
                    since=since_ms,
                    limit=limit,
                )
                if df is not None and len(df) >= self.min_bars:
                    logger.info(f"데이터 수집 완료: {symbol} ({len(df)}바)")
                    return df
                logger.debug(
                    f"{symbol} 데이터 부족: {len(df) if df is not None else 0}바"
                )
            except Exception as e:
                logger.warning(f"{symbol} 데이터 수집 실패: {e}")
                continue

        return None

    def _aggregate_oos_metrics(self, wf_result: Dict) -> Dict:
        """Walk-Forward OOS 결과에서 대표 메트릭을 집계합니다."""
        oos_results = wf_result['oos_results']

        total_returns = []
        sharpe_ratios = []
        max_drawdowns = []
        total_trades_list = []
        win_rates = []

        for r in oos_results:
            full = r.get('oos_full_result', {})
            total_returns.append(full.get('total_return', 0.0))
            sharpe_ratios.append(full.get('sharpe_ratio', 0.0))
            max_drawdowns.append(full.get('max_drawdown', 0.0))
            total_trades_list.append(full.get('total_trades', 0))
            win_rates.append(full.get('win_rate', 0.0))

        import numpy as np
        return {
            'total_return': float(np.mean(total_returns)) if total_returns else 0.0,
            'sharpe_ratio': float(np.mean(sharpe_ratios)) if sharpe_ratios else 0.0,
            'max_drawdown': float(np.min(max_drawdowns)) if max_drawdowns else 0.0,
            'total_trades': int(np.mean(total_trades_list)) if total_trades_list else 0,
            'win_rate': float(np.mean(win_rates)) if win_rates else 0.0,
        }

    def _validate_results(
        self, wf_result: Dict, backtest_metrics: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        최적화 결과를 안전 기준으로 검증합니다.

        Args:
            wf_result: walk_forward_optimize() 반환값
            backtest_metrics: OOS 집계 메트릭

        Returns:
            (통과 여부, 실패 사유)
        """
        # 최소 거래 횟수
        if backtest_metrics.get('total_trades', 0) < self.min_trades:
            return False, (
                f"거래 부족: {backtest_metrics.get('total_trades', 0)} "
                f"< {self.min_trades}"
            )

        # 최소 Sharpe Ratio
        if backtest_metrics.get('sharpe_ratio', 0.0) < self.min_sharpe:
            return False, (
                f"Sharpe 부족: {backtest_metrics.get('sharpe_ratio', 0.0):.2f} "
                f"< {self.min_sharpe}"
            )

        # 최대 드로다운
        if backtest_metrics.get('max_drawdown', 0.0) < self.max_drawdown_limit:
            return False, (
                f"드로다운 초과: {backtest_metrics.get('max_drawdown', 0.0):.1f}% "
                f"< {self.max_drawdown_limit}%"
            )

        return True, None

    def _select_best_params(self, wf_result: Dict) -> Dict:
        """
        Walk-Forward 결과에서 최적 파라미터를 선택합니다.

        마지막 윈도우의 최적 파라미터를 사용합니다 (가장 최근 데이터 반영).
        """
        best_params_list = wf_result.get('best_params_per_window', [])
        if best_params_list:
            return best_params_list[-1]
        return {}

    def _backtest_with_params(
        self, strategy_class: Type, df: pd.DataFrame, params: Dict
    ) -> Dict:
        """주어진 파라미터로 백테스트를 실행하여 메트릭을 반환합니다."""
        try:
            strategy = strategy_class(**params)
            backtester = self.optimizer._create_backtester(strategy, use_vbt=True)
            result = backtester.run(df)
            return {
                'total_return': result.get('total_return', 0.0),
                'sharpe_ratio': result.get('sharpe_ratio', 0.0),
                'max_drawdown': result.get('max_drawdown', 0.0),
                'total_trades': result.get('total_trades', 0),
                'win_rate': result.get('win_rate', 0.0),
            }
        except Exception as e:
            logger.warning(f"기존 파라미터 백테스트 실패: {e}")
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'total_trades': 0,
                'win_rate': 0.0,
            }

    def _calculate_improvement(
        self, old_metrics: Dict, new_metrics: Dict
    ) -> float:
        """
        기존 대비 개선율을 계산합니다.

        Sharpe Ratio 기준으로 비교합니다.
        기존 Sharpe가 0 이하이면 새 Sharpe가 양수인 경우 큰 개선으로 판단합니다.

        Returns:
            개선율 (%) — 양수면 개선, 음수면 악화
        """
        old_sharpe = old_metrics.get('sharpe_ratio', 0.0)
        new_sharpe = new_metrics.get('sharpe_ratio', 0.0)

        if old_sharpe <= 0:
            # 기존이 0 이하 → 새 Sharpe가 양수면 큰 개선
            if new_sharpe > 0:
                return 100.0
            return 0.0

        return ((new_sharpe - old_sharpe) / abs(old_sharpe)) * 100.0

    def _update_preset(
        self, preset_name: str, preset: Dict, new_params: Dict
    ) -> None:
        """
        프리셋을 새 파라미터로 업데이트합니다.

        save_preset()은 모든 필드를 요구하므로, 기존 프리셋을 로드한 뒤
        strategy_params만 교체하고 전체를 다시 저장합니다.
        """
        self.preset_manager.save_preset(
            name=preset_name,
            strategy=preset.get('strategy', ''),
            strategy_params=new_params,
            initial_capital=preset.get('initial_capital', 10000.0),
            position_size=preset.get('position_size', 0.95),
            symbols=preset.get('symbols', []),
            stop_loss_pct=preset.get('stop_loss_pct', 0.05),
            take_profit_pct=preset.get('take_profit_pct', 0.10),
            enable_stop_loss=preset.get('enable_stop_loss', True),
            enable_take_profit=preset.get('enable_take_profit', True),
            description=preset.get('description', ''),
            limit_orders=preset.get('limit_orders', []),
        )
