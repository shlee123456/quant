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

    def optimize(
        self,
        strategy_class: Type,
        df: pd.DataFrame,
        param_grid: Dict[str, List[Any]]
    ) -> Dict:
        """
        Optimize strategy parameters using grid search

        Args:
            strategy_class: Strategy class to optimize
            df: Historical OHLCV data
            param_grid: Dictionary of parameter names to lists of values
                       e.g., {'period': [10, 20, 30], 'threshold': [0.5, 1.0]}

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
            backtester = Backtester(
                strategy=strategy,
                initial_capital=self.initial_capital,
                position_size=self.position_size,
                commission=self.commission
            )

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
        df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compare multiple strategies on the same data

        Args:
            strategies: List of strategy instances to compare
            df: Historical OHLCV data

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
            backtester = Backtester(
                strategy=strategy,
                initial_capital=self.initial_capital,
                position_size=self.position_size,
                commission=self.commission
            )

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
