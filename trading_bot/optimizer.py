"""
Strategy optimizer and comparison tool
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Type
from itertools import product
from .backtester import Backtester


class StrategyOptimizer:
    """
    Optimize strategy parameters and compare multiple strategies
    """

    def __init__(self, initial_capital: float = 10000.0, position_size: float = 0.95, commission: float = 0.001):
        """
        Initialize optimizer

        Args:
            initial_capital: Starting capital for backtests
            position_size: Fraction of capital to use per trade
            commission: Trading commission/fee
        """
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission = commission
        self.results = []

    def _create_backtester(self, strategy, use_vbt: bool = False):
        """
        백테스터 인스턴스 생성

        Args:
            strategy: 전략 객체
            use_vbt: True이면 VBTBacktester, False이면 레거시 Backtester 사용
        """
        if use_vbt:
            from .vbt_backtester import VBTBacktester
            return VBTBacktester(
                strategy=strategy,
                initial_capital=self.initial_capital,
                position_size=self.position_size,
                commission=self.commission,
            )
        return Backtester(
            strategy=strategy,
            initial_capital=self.initial_capital,
            position_size=self.position_size,
            commission=self.commission,
        )

    def optimize(
        self,
        strategy_class: Type,
        df: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        use_vbt: bool = False,
    ) -> Dict:
        """
        Optimize strategy parameters using grid search

        Args:
            strategy_class: Strategy class to optimize
            df: Historical OHLCV data
            param_grid: Dictionary of parameter names to lists of values
                       e.g., {'period': [10, 20, 30], 'threshold': [0.5, 1.0]}
            use_vbt: True이면 VBTBacktester 사용 (전략에 get_entries_exits 필요)

        Returns:
            Dictionary with best parameters and results
        """
        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        param_combinations = list(product(*param_values))

        print(f"\nOptimizing {strategy_class.__name__}")
        print(f"Testing {len(param_combinations)} parameter combinations...\n")

        results = []

        for i, params in enumerate(param_combinations, 1):
            # Create parameter dictionary
            param_dict = dict(zip(param_names, params))

            # Create strategy instance with these parameters
            strategy = strategy_class(**param_dict)

            # Run backtest
            backtester = self._create_backtester(strategy, use_vbt=use_vbt)

            backtest_results = backtester.run(df)

            # Store results
            result = {
                'params': param_dict,
                'strategy_name': strategy.name,
                **backtest_results
            }
            results.append(result)

            # Print progress
            if i % 10 == 0 or i == len(param_combinations):
                print(f"Progress: {i}/{len(param_combinations)} combinations tested")

        # Sort by total return (descending)
        results.sort(key=lambda x: x['total_return'], reverse=True)

        # Store results
        self.results = results

        # Get best result
        best_result = results[0]

        print("\n" + "="*60)
        print("OPTIMIZATION RESULTS")
        print("="*60)
        print(f"Best Parameters: {best_result['params']}")
        print(f"Total Return: {best_result['total_return']:.2f}%")
        print(f"Sharpe Ratio: {best_result['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: {best_result['max_drawdown']:.2f}%")
        print(f"Win Rate: {best_result['win_rate']:.2f}%")
        print("="*60 + "\n")

        return best_result

    def compare_strategies(
        self,
        strategies: List[Any],
        df: pd.DataFrame,
        use_vbt: bool = False,
    ) -> pd.DataFrame:
        """
        Compare multiple strategies on the same data

        Args:
            strategies: List of strategy instances to compare
            df: Historical OHLCV data
            use_vbt: True이면 VBTBacktester 사용 (전략에 get_entries_exits 필요)

        Returns:
            DataFrame with comparison results
        """
        # Handle empty strategy list
        if not strategies:
            return pd.DataFrame()

        print(f"\nComparing {len(strategies)} strategies...\n")

        comparison_results = []

        for strategy in strategies:
            # Run backtest
            backtester = self._create_backtester(strategy, use_vbt=use_vbt)

            results = backtester.run(df)

            # Store results
            comparison_results.append({
                'strategy': strategy.name,
                'total_return': results['total_return'],
                'sharpe_ratio': results['sharpe_ratio'],
                'max_drawdown': results['max_drawdown'],
                'win_rate': results['win_rate'],
                'total_trades': results['total_trades'],
                'final_capital': results['final_capital']
            })

        # Create comparison DataFrame
        comparison_df = pd.DataFrame(comparison_results)
        comparison_df = comparison_df.sort_values('total_return', ascending=False)

        # Print comparison
        self._print_comparison(comparison_df)

        return comparison_df

    def _print_comparison(self, comparison_df: pd.DataFrame):
        """Print strategy comparison table"""
        print("\n" + "="*80)
        print("STRATEGY COMPARISON")
        print("="*80)
        print(f"{'Strategy':<30} {'Return %':<12} {'Sharpe':<10} {'Max DD %':<12} {'Win Rate %':<12}")
        print("-"*80)

        for _, row in comparison_df.iterrows():
            print(f"{row['strategy']:<30} {row['total_return']:>10.2f}  "
                  f"{row['sharpe_ratio']:>8.2f}  {row['max_drawdown']:>10.2f}  "
                  f"{row['win_rate']:>10.2f}")

        print("="*80 + "\n")

    def get_optimization_results(self) -> pd.DataFrame:
        """
        Get all optimization results as DataFrame

        Returns:
            DataFrame with all tested parameter combinations and results
        """
        if not self.results:
            return pd.DataFrame()

        # Flatten parameter dictionaries
        flattened_results = []
        for result in self.results:
            flat_result = {**result['params'], **{k: v for k, v in result.items() if k != 'params'}}
            flattened_results.append(flat_result)

        return pd.DataFrame(flattened_results)

    def plot_optimization_surface(
        self,
        param1: str,
        param2: str,
        metric: str = 'total_return'
    ):
        """
        Plot 2D optimization surface for two parameters

        Args:
            param1: First parameter name
            param2: Second parameter name
            metric: Metric to plot (default: 'total_return')

        Note:
            Requires matplotlib. This method will raise ImportError if matplotlib is not installed.
        """
        try:
            import matplotlib.pyplot as plt
            from mpl_toolkits.mplot3d import Axes3D
        except ImportError:
            print("Matplotlib is required for plotting. Install it with: pip install matplotlib")
            return

        if not self.results:
            print("No optimization results available. Run optimize() first.")
            return

        # Extract data
        data = []
        for result in self.results:
            if param1 in result['params'] and param2 in result['params']:
                data.append({
                    param1: result['params'][param1],
                    param2: result['params'][param2],
                    metric: result[metric]
                })

        df = pd.DataFrame(data)

        # Create 3D plot
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111, projection='3d')

        ax.scatter(df[param1], df[param2], df[metric], c=df[metric], cmap='viridis', s=100)

        ax.set_xlabel(param1)
        ax.set_ylabel(param2)
        ax.set_zlabel(metric)
        ax.set_title(f'Optimization Surface: {metric}')

        plt.colorbar(ax.scatter(df[param1], df[param2], df[metric], c=df[metric], cmap='viridis'),
                     ax=ax, label=metric)

        plt.tight_layout()
        plt.show()

    def get_top_n_strategies(self, n: int = 5, metric: str = 'total_return') -> List[Dict]:
        """
        Get top N strategies based on a metric

        Args:
            n: Number of top strategies to return
            metric: Metric to rank by (default: 'total_return')

        Returns:
            List of top N strategy results
        """
        if not self.results:
            return []

        sorted_results = sorted(self.results, key=lambda x: x[metric], reverse=True)
        return sorted_results[:n]

    def optimize_by_regime(
        self,
        strategy_classes: List[Type],
        df: pd.DataFrame,
        param_grids: List[Dict[str, List[Any]]],
        regime_detector=None,
        use_vbt: bool = False,
    ) -> Dict[str, Dict]:
        """
        레짐별 최적 전략/파라미터 탐색

        Args:
            strategy_classes: 전략 클래스 리스트
            df: OHLCV 데이터
            param_grids: 전략별 파라미터 그리드 리스트 (strategy_classes와 동일 순서)
            regime_detector: RegimeDetector 인스턴스
            use_vbt: VBTBacktester 사용 여부

        Returns:
            Dict[regime_name -> {'strategy_class', 'best_params', 'results'}]
        """
        if regime_detector is None:
            from .regime_detector import RegimeDetector
            regime_detector = RegimeDetector()

        # 전체 바에 레짐 라벨링
        labeled_df = regime_detector.detect_series(df)

        regime_results = {}

        for regime_name in ['BULLISH', 'BEARISH', 'SIDEWAYS', 'VOLATILE']:
            regime_mask = labeled_df['regime'] == regime_name
            regime_df = df[regime_mask].copy()

            if len(regime_df) < 50:
                print(f"\n[{regime_name}] 데이터 부족 ({len(regime_df)}행) - 건너뜀")
                continue

            print(f"\n{'='*60}")
            print(f"[{regime_name}] 레짐 데이터: {len(regime_df)}행")
            print(f"{'='*60}")

            best_for_regime = None
            best_return = float('-inf')

            for strategy_class, param_grid in zip(strategy_classes, param_grids):
                try:
                    result = self.optimize(strategy_class, regime_df, param_grid, use_vbt=use_vbt)
                    if result['total_return'] > best_return:
                        best_return = result['total_return']
                        best_for_regime = {
                            'strategy_class': strategy_class,
                            'strategy_name': strategy_class.__name__,
                            'best_params': result['params'],
                            'results': result,
                        }
                except Exception as e:
                    print(f"  {strategy_class.__name__} 최적화 실패: {e}")

            if best_for_regime:
                regime_results[regime_name] = best_for_regime
                print(f"\n[{regime_name}] 최적 전략: {best_for_regime['strategy_name']}")
                print(f"  파라미터: {best_for_regime['best_params']}")
                print(f"  수익률: {best_return:.2f}%")

        return regime_results

    def walk_forward_optimize(
        self,
        strategy_class: Type,
        df: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        n_splits: int = 5,
        train_ratio: float = 0.7,
        mode: str = 'anchored',
        metric: str = 'total_return',
        use_vbt: bool = True,
    ) -> Dict:
        """
        Walk-Forward Optimization: IS 구간에서 최적화 후 OOS 구간에서 검증

        데이터를 n_splits개 윈도우로 나누어 순차적으로 학습/검증하여
        과적합을 방지하고 전략의 실전 성능을 추정합니다.

        Args:
            strategy_class: 최적화할 전략 클래스
            df: OHLCV 데이터
            param_grid: 파라미터 그리드 (예: {'period': [7, 14, 21]})
            n_splits: 윈도우 분할 수
            train_ratio: 학습 데이터 비율 (0.0~1.0)
            mode: 'anchored' (시작 고정, 확장) 또는 'rolling' (고정 크기 슬라이딩)
            metric: 최적화 기준 지표 (기본: 'total_return')
            use_vbt: VBTBacktester 사용 여부

        Returns:
            Dict with:
                - oos_results: 윈도우별 OOS 결과 리스트
                - aggregate_oos_return: OOS 평균 수익률
                - stability_ratio: mean(OOS) / mean(IS) (IS <= 0이면 None)
                - is_oos_gap: mean(IS - OOS)
                - parameter_stability: 파라미터 안정성 (0~1)
                - best_params_per_window: 윈도우별 최적 파라미터
                - windows: (train_start, train_end, test_start, test_end) 리스트
        """
        total_len = len(df)

        # 데이터 부족 시 빈 결과 반환
        if total_len < n_splits * 2:
            print(f"[Walk-Forward] 데이터 부족: {total_len}행 (최소 {n_splits * 2}행 필요)")
            return {
                'oos_results': [],
                'aggregate_oos_return': 0.0,
                'stability_ratio': None,
                'is_oos_gap': 0.0,
                'parameter_stability': 0.0,
                'best_params_per_window': [],
                'windows': [],
            }

        # 윈도우 경계 계산
        if mode == 'rolling':
            window_size = total_len // n_splits
            boundaries = [(i * window_size, (i + 1) * window_size) for i in range(n_splits)]
            # 마지막 윈도우는 나머지 데이터 포함
            boundaries[-1] = (boundaries[-1][0], total_len)
        else:
            # anchored: 균등 분할 지점 계산
            step = total_len // (n_splits + 1)
            boundaries = []
            for i in range(n_splits):
                end_idx = step * (i + 2)
                if i == n_splits - 1:
                    end_idx = total_len
                boundaries.append((0, end_idx))

        oos_results = []
        is_returns = []
        best_params_per_window = []
        windows = []

        for i in range(n_splits):
            if mode == 'rolling':
                window_start, window_end = boundaries[i]
                split_point = window_start + int((window_end - window_start) * train_ratio)
                train_start = window_start
                train_end = split_point
                test_start = split_point
                test_end = window_end
            else:
                # anchored: 항상 처음부터 시작, 확장
                _, window_end = boundaries[i]
                split_point = int(window_end * train_ratio)
                train_start = 0
                train_end = split_point
                test_start = split_point
                test_end = window_end

            train_df = df.iloc[train_start:train_end].copy()
            test_df = df.iloc[test_start:test_end].copy()

            # 학습/검증 데이터 최소 크기 확인
            if len(train_df) < 30 or len(test_df) < 10:
                print(f"[Walk-Forward] 윈도우 {i+1}/{n_splits}: 데이터 부족 (train={len(train_df)}, test={len(test_df)}) - 건너뜀")
                continue

            print(f"\n[Walk-Forward] 윈도우 {i+1}/{n_splits}: "
                  f"Train[{train_start}:{train_end}]({len(train_df)}행) → "
                  f"Test[{test_start}:{test_end}]({len(test_df)}행)")

            # IS 최적화 (self.results 오염 방지)
            saved_results = self.results
            try:
                is_best = self.optimize(strategy_class, train_df, param_grid, use_vbt=use_vbt)
            except Exception as e:
                print(f"  IS 최적화 실패: {e}")
                self.results = saved_results
                continue
            self.results = saved_results

            is_return = is_best[metric]
            best_params = is_best['params']

            # OOS 평가
            try:
                strategy = strategy_class(**best_params)
                backtester = self._create_backtester(strategy, use_vbt=use_vbt)
                oos_result = backtester.run(test_df)
            except Exception as e:
                print(f"  OOS 평가 실패: {e}")
                continue

            oos_return = oos_result[metric]

            oos_results.append({
                'window': i,
                'is_return': is_return,
                'oos_return': oos_return,
                'best_params': best_params,
                'oos_full_result': oos_result,
            })
            is_returns.append(is_return)
            best_params_per_window.append(best_params)

            train_start_ts = df.index[train_start] if hasattr(df.index, '__getitem__') else train_start
            train_end_ts = df.index[train_end - 1] if hasattr(df.index, '__getitem__') else train_end
            test_start_ts = df.index[test_start] if hasattr(df.index, '__getitem__') else test_start
            test_end_ts = df.index[test_end - 1] if hasattr(df.index, '__getitem__') else test_end
            windows.append((train_start_ts, train_end_ts, test_start_ts, test_end_ts))

            print(f"  IS {metric}: {is_return:.2f}% → OOS {metric}: {oos_return:.2f}%")
            print(f"  최적 파라미터: {best_params}")

        # 집계
        if not oos_results:
            return {
                'oos_results': [],
                'aggregate_oos_return': 0.0,
                'stability_ratio': None,
                'is_oos_gap': 0.0,
                'parameter_stability': 0.0,
                'best_params_per_window': [],
                'windows': [],
            }

        oos_returns = [r['oos_return'] for r in oos_results]
        mean_oos = np.mean(oos_returns)
        mean_is = np.mean(is_returns)

        # stability_ratio: mean(OOS) / mean(IS)
        stability_ratio = None
        if mean_is > 0:
            stability_ratio = mean_oos / mean_is

        # is_oos_gap: mean(IS - OOS)
        is_oos_gap = mean_is - mean_oos

        # parameter_stability: 1 - mean((n_unique - 1) / (n_splits - 1)) per param
        parameter_stability = self._calculate_parameter_stability(
            best_params_per_window, n_splits
        )

        # 결과 출력
        print(f"\n{'='*60}")
        print("WALK-FORWARD OPTIMIZATION 결과")
        print(f"{'='*60}")
        print(f"모드: {mode} | 윈도우: {len(oos_results)}/{n_splits}")
        print(f"평균 OOS 수익률: {mean_oos:.2f}%")
        print(f"평균 IS 수익률: {mean_is:.2f}%")
        print(f"IS-OOS 갭: {is_oos_gap:.2f}%")
        if stability_ratio is not None:
            print(f"안정성 비율 (OOS/IS): {stability_ratio:.2f}")
        else:
            print(f"안정성 비율 (OOS/IS): N/A (IS ≤ 0)")
        print(f"파라미터 안정성: {parameter_stability:.2f}")
        print(f"{'='*60}\n")

        return {
            'oos_results': oos_results,
            'aggregate_oos_return': mean_oos,
            'stability_ratio': stability_ratio,
            'is_oos_gap': is_oos_gap,
            'parameter_stability': parameter_stability,
            'best_params_per_window': best_params_per_window,
            'windows': windows,
        }

    def _calculate_parameter_stability(
        self,
        best_params_per_window: List[Dict],
        n_splits: int,
    ) -> float:
        """
        파라미터 안정성 계산

        각 파라미터별로 윈도우 간 고유 값 수를 기반으로 안정성 측정.
        1.0 = 모든 윈도우에서 동일 파라미터, 0.0 = 모든 윈도우에서 다른 파라미터

        Args:
            best_params_per_window: 윈도우별 최적 파라미터 리스트
            n_splits: 전체 윈도우 수

        Returns:
            0.0 ~ 1.0 사이의 안정성 점수
        """
        if len(best_params_per_window) <= 1:
            return 1.0

        actual_windows = len(best_params_per_window)
        if actual_windows <= 1:
            return 1.0

        param_names = best_params_per_window[0].keys()
        instabilities = []

        for param in param_names:
            values = [p[param] for p in best_params_per_window]
            n_unique = len(set(values))
            instability = (n_unique - 1) / (actual_windows - 1)
            instabilities.append(instability)

        if not instabilities:
            return 1.0

        return 1.0 - np.mean(instabilities)

    def walk_forward_regime_optimize(
        self,
        strategy_classes: List[Type],
        df: pd.DataFrame,
        param_grids: List[Dict[str, List[Any]]],
        n_splits: int = 5,
        train_ratio: float = 0.7,
        mode: str = 'anchored',
        regime_detector=None,
        use_vbt: bool = True,
    ) -> Dict:
        """
        Walk-Forward + Regime-Aware Optimization

        각 윈도우를 레짐별로 분리하여 최적화한 뒤 OOS에서 검증합니다.

        Args:
            strategy_classes: 전략 클래스 리스트
            df: OHLCV 데이터
            param_grids: 전략별 파라미터 그리드 리스트
            n_splits: 윈도우 분할 수
            train_ratio: 학습 데이터 비율
            mode: 'anchored' 또는 'rolling'
            regime_detector: RegimeDetector 인스턴스 (None이면 자동 생성)
            use_vbt: VBTBacktester 사용 여부

        Returns:
            Dict with:
                - windows: 윈도우별 레짐 최적화 결과 리스트
                - aggregate_oos_return: OOS 평균 수익률
                - n_windows: 실제 처리된 윈도우 수
        """
        if regime_detector is None:
            from .regime_detector import RegimeDetector
            regime_detector = RegimeDetector()

        total_len = len(df)

        if total_len < n_splits * 2:
            print(f"[WF-Regime] 데이터 부족: {total_len}행")
            return {
                'windows': [],
                'aggregate_oos_return': 0.0,
                'n_windows': 0,
            }

        # 윈도우 경계 계산 (walk_forward_optimize과 동일 로직)
        if mode == 'rolling':
            window_size = total_len // n_splits
            boundaries = [(i * window_size, (i + 1) * window_size) for i in range(n_splits)]
            boundaries[-1] = (boundaries[-1][0], total_len)
        else:
            step = total_len // (n_splits + 1)
            boundaries = []
            for i in range(n_splits):
                end_idx = step * (i + 2)
                if i == n_splits - 1:
                    end_idx = total_len
                boundaries.append((0, end_idx))

        window_results = []
        all_oos_returns = []

        for i in range(n_splits):
            if mode == 'rolling':
                window_start, window_end = boundaries[i]
                split_point = window_start + int((window_end - window_start) * train_ratio)
                train_start = window_start
                train_end = split_point
                test_start = split_point
                test_end = window_end
            else:
                _, window_end = boundaries[i]
                split_point = int(window_end * train_ratio)
                train_start = 0
                train_end = split_point
                test_start = split_point
                test_end = window_end

            train_df = df.iloc[train_start:train_end].copy()
            test_df = df.iloc[test_start:test_end].copy()

            if len(train_df) < 50 or len(test_df) < 10:
                print(f"[WF-Regime] 윈도우 {i+1}/{n_splits}: 데이터 부족 - 건너뜀")
                continue

            print(f"\n[WF-Regime] 윈도우 {i+1}/{n_splits}: "
                  f"Train({len(train_df)}행) → Test({len(test_df)}행)")

            # IS 레짐별 최적화
            saved_results = self.results
            try:
                regime_result = self.optimize_by_regime(
                    strategy_classes, train_df, param_grids,
                    regime_detector=regime_detector, use_vbt=use_vbt,
                )
            except Exception as e:
                print(f"  레짐 최적화 실패: {e}")
                self.results = saved_results
                continue
            self.results = saved_results

            # OOS 평가: 테스트 데이터에 기본 전략 적용 (첫 번째 레짐 결과 사용)
            oos_return = None
            if regime_result:
                # 가장 데이터가 많은 레짐의 최적 전략으로 OOS 평가
                best_regime = next(iter(regime_result.values()))
                try:
                    strategy = best_regime['strategy_class'](**best_regime['best_params'])
                    backtester = self._create_backtester(strategy, use_vbt=use_vbt)
                    oos_result = backtester.run(test_df)
                    oos_return = oos_result['total_return']
                    all_oos_returns.append(oos_return)
                except Exception as e:
                    print(f"  OOS 평가 실패: {e}")

            window_results.append({
                'window': i,
                'regime_results': regime_result,
                'oos_return': oos_return,
            })

        aggregate_oos_return = float(np.mean(all_oos_returns)) if all_oos_returns else 0.0

        print(f"\n{'='*60}")
        print("WALK-FORWARD REGIME OPTIMIZATION 결과")
        print(f"{'='*60}")
        print(f"처리된 윈도우: {len(window_results)}/{n_splits}")
        print(f"평균 OOS 수익률: {aggregate_oos_return:.2f}%")
        print(f"{'='*60}\n")

        return {
            'windows': window_results,
            'aggregate_oos_return': aggregate_oos_return,
            'n_windows': len(window_results),
        }

    def analyze_parameter_sensitivity(self, param_name: str, metric: str = 'total_return') -> pd.DataFrame:
        """
        Analyze how a single parameter affects performance

        Args:
            param_name: Parameter to analyze
            metric: Performance metric to analyze

        Returns:
            DataFrame with parameter values and corresponding metric values
        """
        if not self.results:
            return pd.DataFrame()

        # Extract data for the parameter
        data = []
        for result in self.results:
            if param_name in result['params']:
                data.append({
                    param_name: result['params'][param_name],
                    metric: result[metric]
                })

        df = pd.DataFrame(data)

        # Group by parameter value and calculate statistics
        sensitivity = df.groupby(param_name)[metric].agg(['mean', 'std', 'min', 'max', 'count'])
        sensitivity = sensitivity.sort_values('mean', ascending=False)

        print(f"\n{param_name} Sensitivity Analysis ({metric}):")
        print(sensitivity)

        return sensitivity
