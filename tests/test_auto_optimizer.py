"""Tests for AutoOptimizer"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

from trading_bot.auto_optimizer import AutoOptimizer
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy
from trading_bot.strategies.stochastic_strategy import StochasticStrategy
from trading_bot.strategies.rsi_macd_combo_strategy import RSIMACDComboStrategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STRATEGY_CLASS_MAP = {
    'RSI Strategy': RSIStrategy,
    'MACD Strategy': MACDStrategy,
    'Bollinger Bands': BollingerBandsStrategy,
    'Stochastic': StochasticStrategy,
    'RSI+MACD Combo Strategy': RSIMACDComboStrategy,
}


@pytest.fixture
def temp_preset_file():
    temp_dir = tempfile.mkdtemp()
    preset_file = os.path.join(temp_dir, 'test_presets.json')
    yield preset_file
    if os.path.exists(preset_file):
        os.remove(preset_file)
    os.rmdir(temp_dir)


@pytest.fixture
def preset_manager(temp_preset_file):
    return StrategyPresetManager(presets_file=temp_preset_file)


@pytest.fixture
def optimizer():
    return StrategyOptimizer(initial_capital=10000.0)


@pytest.fixture
def auto_optimizer(optimizer, preset_manager):
    return AutoOptimizer(
        optimizer=optimizer,
        preset_manager=preset_manager,
        strategy_class_map=STRATEGY_CLASS_MAP,
        min_bars=50,  # 테스트에서는 낮은 값 사용
    )


def _make_ohlcv_df(n=600):
    """시뮬레이션 OHLCV DataFrame 생성."""
    np.random.seed(42)
    prices = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n)))
    return pd.DataFrame({
        'open': prices * (1 - np.random.uniform(0, 0.005, n)),
        'high': prices * (1 + np.random.uniform(0.005, 0.02, n)),
        'low': prices * (1 - np.random.uniform(0.005, 0.02, n)),
        'close': prices,
        'volume': np.random.randint(1000, 10000, n).astype(float),
    })


def _mock_broker(df=None):
    """OHLCV 데이터를 반환하는 mock 브로커."""
    broker = Mock()
    broker.fetch_ohlcv.return_value = df if df is not None else _make_ohlcv_df()
    return broker


# ---------------------------------------------------------------------------
# Tests: DEFAULT_PARAM_GRIDS
# ---------------------------------------------------------------------------

class TestDefaultParamGrids:
    def test_all_five_strategies_present(self):
        """5개 전략 모두 DEFAULT_PARAM_GRIDS에 포함."""
        grids = AutoOptimizer.DEFAULT_PARAM_GRIDS
        assert 'RSI Strategy' in grids
        assert 'MACD Strategy' in grids
        assert 'Bollinger Bands' in grids
        assert 'Stochastic' in grids
        assert 'RSI+MACD Combo Strategy' in grids

    def test_rsi_grid_keys(self):
        grid = AutoOptimizer.DEFAULT_PARAM_GRIDS['RSI Strategy']
        assert set(grid.keys()) == {'period', 'overbought', 'oversold'}

    def test_macd_grid_keys(self):
        grid = AutoOptimizer.DEFAULT_PARAM_GRIDS['MACD Strategy']
        assert set(grid.keys()) == {'fast_period', 'slow_period', 'signal_period'}

    def test_bollinger_grid_keys(self):
        grid = AutoOptimizer.DEFAULT_PARAM_GRIDS['Bollinger Bands']
        assert set(grid.keys()) == {'period', 'num_std'}

    def test_stochastic_grid_keys(self):
        grid = AutoOptimizer.DEFAULT_PARAM_GRIDS['Stochastic']
        assert set(grid.keys()) == {'k_period', 'd_period', 'overbought', 'oversold'}

    def test_combo_grid_keys(self):
        grid = AutoOptimizer.DEFAULT_PARAM_GRIDS['RSI+MACD Combo Strategy']
        expected = {'rsi_period', 'rsi_overbought', 'rsi_oversold',
                    'macd_fast', 'macd_slow', 'macd_signal'}
        assert set(grid.keys()) == expected


# ---------------------------------------------------------------------------
# Tests: _get_param_grid
# ---------------------------------------------------------------------------

class TestGetParamGrid:
    def test_known_strategy(self, auto_optimizer):
        grid = auto_optimizer._get_param_grid('RSI Strategy')
        assert grid is not None
        assert 'period' in grid

    def test_unknown_strategy(self, auto_optimizer):
        grid = auto_optimizer._get_param_grid('Unknown Strategy')
        assert grid is None


# ---------------------------------------------------------------------------
# Tests: _validate_results — safety guards
# ---------------------------------------------------------------------------

class TestValidateResults:
    def test_rejects_low_trades(self, auto_optimizer):
        """min_trades 미만 시 거부."""
        wf = {'oos_results': []}
        metrics = {'total_trades': 3, 'sharpe_ratio': 1.0, 'max_drawdown': -5.0}
        is_valid, reason = auto_optimizer._validate_results(wf, metrics)
        assert is_valid is False
        assert '거래 부족' in reason

    def test_rejects_low_sharpe(self, auto_optimizer):
        """min_sharpe 미만 시 거부."""
        wf = {'oos_results': []}
        metrics = {'total_trades': 20, 'sharpe_ratio': 0.1, 'max_drawdown': -5.0}
        is_valid, reason = auto_optimizer._validate_results(wf, metrics)
        assert is_valid is False
        assert 'Sharpe' in reason

    def test_rejects_excessive_drawdown(self, auto_optimizer):
        """max_drawdown 초과 시 거부."""
        wf = {'oos_results': []}
        metrics = {'total_trades': 20, 'sharpe_ratio': 1.0, 'max_drawdown': -30.0}
        is_valid, reason = auto_optimizer._validate_results(wf, metrics)
        assert is_valid is False
        assert '드로다운' in reason

    def test_accepts_valid_results(self, auto_optimizer):
        """모든 기준 통과 시 승인."""
        wf = {'oos_results': []}
        metrics = {'total_trades': 20, 'sharpe_ratio': 1.0, 'max_drawdown': -10.0}
        is_valid, reason = auto_optimizer._validate_results(wf, metrics)
        assert is_valid is True
        assert reason is None


# ---------------------------------------------------------------------------
# Tests: _calculate_improvement
# ---------------------------------------------------------------------------

class TestCalculateImprovement:
    def test_positive_improvement(self, auto_optimizer):
        old = {'sharpe_ratio': 1.0}
        new = {'sharpe_ratio': 1.5}
        improvement = auto_optimizer._calculate_improvement(old, new)
        assert abs(improvement - 50.0) < 0.01

    def test_negative_improvement(self, auto_optimizer):
        old = {'sharpe_ratio': 1.0}
        new = {'sharpe_ratio': 0.8}
        improvement = auto_optimizer._calculate_improvement(old, new)
        assert improvement < 0

    def test_old_sharpe_zero_new_positive(self, auto_optimizer):
        """기존 Sharpe 0 이하, 새 Sharpe 양수 -> 100%."""
        old = {'sharpe_ratio': 0.0}
        new = {'sharpe_ratio': 0.5}
        improvement = auto_optimizer._calculate_improvement(old, new)
        assert improvement == 100.0

    def test_old_sharpe_zero_new_zero(self, auto_optimizer):
        """둘 다 0 -> 개선 없음."""
        old = {'sharpe_ratio': 0.0}
        new = {'sharpe_ratio': 0.0}
        improvement = auto_optimizer._calculate_improvement(old, new)
        assert improvement == 0.0

    def test_old_sharpe_negative(self, auto_optimizer):
        old = {'sharpe_ratio': -0.5}
        new = {'sharpe_ratio': 0.5}
        improvement = auto_optimizer._calculate_improvement(old, new)
        assert improvement == 100.0


# ---------------------------------------------------------------------------
# Tests: improvement threshold
# ---------------------------------------------------------------------------

class TestImprovementThreshold:
    def test_below_threshold_skipped(self, auto_optimizer, preset_manager):
        """improvement < threshold -> 프리셋 미적용 (skipped)."""
        preset_manager.save_preset(
            name='test_preset',
            strategy='RSI Strategy',
            strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            symbols=['AAPL'],
        )

        # Mock walk_forward_optimize to return marginal improvement
        wf_result = {
            'oos_results': [{
                'window': 0,
                'oos_return': 5.0,
                'oos_full_result': {
                    'total_return': 5.0,
                    'sharpe_ratio': 0.51,  # only slightly better than old
                    'max_drawdown': -8.0,
                    'total_trades': 15,
                    'win_rate': 55.0,
                },
                'best_params': {'period': 21, 'overbought': 75, 'oversold': 25},
            }],
            'aggregate_oos_return': 5.0,
            'stability_ratio': 0.8,
            'parameter_stability': 0.9,
            'best_params_per_window': [{'period': 21, 'overbought': 75, 'oversold': 25}],
            'windows': [],
        }

        # Mock the old params to have similar sharpe
        with patch.object(auto_optimizer.optimizer, 'walk_forward_optimize', return_value=wf_result):
            with patch.object(auto_optimizer, '_backtest_with_params', return_value={
                'total_return': 4.5,
                'sharpe_ratio': 0.50,
                'max_drawdown': -9.0,
                'total_trades': 12,
                'win_rate': 52.0,
            }):
                broker = _mock_broker()
                summary = auto_optimizer.run(broker, ['test_preset'])

        result = summary['presets']['test_preset']
        assert result['status'] == 'skipped'
        assert result['reason'] == 'insufficient_improvement'


# ---------------------------------------------------------------------------
# Tests: walk_forward_optimize call
# ---------------------------------------------------------------------------

class TestWalkForwardCall:
    def test_calls_walk_forward_optimize(self, auto_optimizer, preset_manager):
        """walk_forward_optimize()가 올바른 인자로 호출되는지 확인."""
        preset_manager.save_preset(
            name='test_preset',
            strategy='RSI Strategy',
            strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            symbols=['AAPL'],
        )

        wf_result = {
            'oos_results': [{
                'window': 0,
                'oos_return': 15.0,
                'oos_full_result': {
                    'total_return': 15.0,
                    'sharpe_ratio': 1.5,
                    'max_drawdown': -8.0,
                    'total_trades': 20,
                    'win_rate': 60.0,
                },
                'best_params': {'period': 21, 'overbought': 75, 'oversold': 25},
            }],
            'aggregate_oos_return': 15.0,
            'stability_ratio': 0.8,
            'parameter_stability': 0.9,
            'best_params_per_window': [{'period': 21, 'overbought': 75, 'oversold': 25}],
            'windows': [],
        }

        with patch.object(auto_optimizer.optimizer, 'walk_forward_optimize', return_value=wf_result) as mock_wfo:
            with patch.object(auto_optimizer, '_backtest_with_params', return_value={
                'sharpe_ratio': 0.3, 'total_return': 2.0, 'max_drawdown': -15.0,
                'total_trades': 10, 'win_rate': 45.0,
            }):
                broker = _mock_broker()
                auto_optimizer.run(broker, ['test_preset'])

        mock_wfo.assert_called_once()
        call_kwargs = mock_wfo.call_args
        assert call_kwargs[1]['metric'] == 'sharpe_ratio'
        assert call_kwargs[1]['use_vbt'] is True
        assert call_kwargs[1]['strategy_class'] is RSIStrategy


# ---------------------------------------------------------------------------
# Tests: preset update
# ---------------------------------------------------------------------------

class TestPresetUpdate:
    def test_preset_updated_on_sufficient_improvement(self, auto_optimizer, preset_manager):
        """충분한 개선 시 프리셋 업데이트."""
        preset_manager.save_preset(
            name='test_preset',
            strategy='RSI Strategy',
            strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            symbols=['AAPL'],
            initial_capital=10000.0,
        )

        new_params = {'period': 21, 'overbought': 75, 'oversold': 25}
        wf_result = {
            'oos_results': [{
                'window': 0,
                'oos_return': 20.0,
                'oos_full_result': {
                    'total_return': 20.0,
                    'sharpe_ratio': 2.0,
                    'max_drawdown': -5.0,
                    'total_trades': 25,
                    'win_rate': 65.0,
                },
                'best_params': new_params,
            }],
            'aggregate_oos_return': 20.0,
            'stability_ratio': 0.9,
            'parameter_stability': 0.95,
            'best_params_per_window': [new_params],
            'windows': [],
        }

        with patch.object(auto_optimizer.optimizer, 'walk_forward_optimize', return_value=wf_result):
            with patch.object(auto_optimizer, '_backtest_with_params', return_value={
                'sharpe_ratio': 0.5, 'total_return': 3.0, 'max_drawdown': -12.0,
                'total_trades': 10, 'win_rate': 50.0,
            }):
                broker = _mock_broker()
                summary = auto_optimizer.run(broker, ['test_preset'])

        result = summary['presets']['test_preset']
        assert result['status'] == 'updated'
        assert result['new_params'] == new_params

        # 프리셋이 실제로 업데이트되었는지 확인
        updated = preset_manager.load_preset('test_preset')
        assert updated['strategy_params'] == new_params


# ---------------------------------------------------------------------------
# Tests: failure modes
# ---------------------------------------------------------------------------

class TestFailureModes:
    def test_preset_not_found(self, auto_optimizer):
        broker = _mock_broker()
        summary = auto_optimizer.run(broker, ['nonexistent'])
        assert summary['presets']['nonexistent']['status'] == 'failed'
        assert summary['presets']['nonexistent']['reason'] == 'preset_not_found'

    def test_strategy_class_not_found(self, auto_optimizer, preset_manager):
        preset_manager.save_preset(
            name='unknown_strategy',
            strategy='Unknown Strategy',
            strategy_params={},
            symbols=['AAPL'],
        )
        broker = _mock_broker()
        summary = auto_optimizer.run(broker, ['unknown_strategy'])
        assert summary['presets']['unknown_strategy']['status'] == 'failed'
        assert summary['presets']['unknown_strategy']['reason'] == 'strategy_class_not_found'

    def test_no_symbols(self, auto_optimizer, preset_manager):
        preset_manager.save_preset(
            name='no_symbols',
            strategy='RSI Strategy',
            strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            symbols=[],
        )
        broker = _mock_broker()
        summary = auto_optimizer.run(broker, ['no_symbols'])
        assert summary['presets']['no_symbols']['status'] == 'failed'
        assert summary['presets']['no_symbols']['reason'] == 'no_symbols'

    def test_insufficient_data(self, auto_optimizer, preset_manager):
        preset_manager.save_preset(
            name='short_data',
            strategy='RSI Strategy',
            strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            symbols=['AAPL'],
        )
        # Return very short DataFrame
        broker = _mock_broker(_make_ohlcv_df(n=10))
        summary = auto_optimizer.run(broker, ['short_data'])
        assert summary['presets']['short_data']['status'] == 'failed'
        assert summary['presets']['short_data']['reason'] == 'insufficient_data'

    def test_no_param_grid(self, preset_manager, optimizer):
        """param_grid가 없는 전략명."""
        auto = AutoOptimizer(
            optimizer=optimizer,
            preset_manager=preset_manager,
            strategy_class_map={'Custom Strategy': RSIStrategy},
            min_bars=50,
        )
        preset_manager.save_preset(
            name='custom',
            strategy='Custom Strategy',
            strategy_params={'period': 14},
            symbols=['AAPL'],
        )
        broker = _mock_broker()
        summary = auto.run(broker, ['custom'])
        assert summary['presets']['custom']['status'] == 'failed'
        assert summary['presets']['custom']['reason'] == 'no_param_grid'


# ---------------------------------------------------------------------------
# Tests: summary counts
# ---------------------------------------------------------------------------

class TestSummaryCounts:
    def test_summary_counts(self, auto_optimizer, preset_manager):
        """요약의 updated/skipped/failed 카운트가 정확."""
        # 1 failed (not found), 1 failed (no symbols)
        preset_manager.save_preset(
            name='no_sym',
            strategy='RSI Strategy',
            strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            symbols=[],
        )
        broker = _mock_broker()
        summary = auto_optimizer.run(broker, ['not_found', 'no_sym'])

        assert summary['total_presets'] == 2
        assert summary['failed'] == 2
        assert summary['updated'] == 0
        assert summary['skipped'] == 0


# ---------------------------------------------------------------------------
# Tests: _select_best_params
# ---------------------------------------------------------------------------

class TestSelectBestParams:
    def test_selects_last_window(self, auto_optimizer):
        wf = {
            'best_params_per_window': [
                {'period': 7, 'overbought': 65, 'oversold': 35},
                {'period': 14, 'overbought': 70, 'oversold': 30},
                {'period': 21, 'overbought': 75, 'oversold': 25},
            ],
        }
        best = auto_optimizer._select_best_params(wf)
        assert best == {'period': 21, 'overbought': 75, 'oversold': 25}

    def test_empty_params_list(self, auto_optimizer):
        wf = {'best_params_per_window': []}
        best = auto_optimizer._select_best_params(wf)
        assert best == {}


# ---------------------------------------------------------------------------
# Tests: _aggregate_oos_metrics
# ---------------------------------------------------------------------------

class TestAggregateOosMetrics:
    def test_aggregation(self, auto_optimizer):
        wf = {
            'oos_results': [
                {
                    'oos_full_result': {
                        'total_return': 10.0,
                        'sharpe_ratio': 1.0,
                        'max_drawdown': -5.0,
                        'total_trades': 20,
                        'win_rate': 60.0,
                    }
                },
                {
                    'oos_full_result': {
                        'total_return': 20.0,
                        'sharpe_ratio': 2.0,
                        'max_drawdown': -10.0,
                        'total_trades': 30,
                        'win_rate': 70.0,
                    }
                },
            ]
        }
        metrics = auto_optimizer._aggregate_oos_metrics(wf)

        assert abs(metrics['total_return'] - 15.0) < 0.01
        assert abs(metrics['sharpe_ratio'] - 1.5) < 0.01
        assert metrics['max_drawdown'] == -10.0  # min, not mean
        assert metrics['total_trades'] == 25  # mean
        assert abs(metrics['win_rate'] - 65.0) < 0.01
