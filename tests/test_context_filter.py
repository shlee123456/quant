"""SignalPipeline context filter 단위 테스트"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from trading_bot.signal_pipeline import SignalPipeline
from trading_bot.signal_tracker import SignalTracker as _RealSignalTracker


def _make_scorecard(
    sufficient=True,
    overall_accuracy=50.0,
    fg_zones=None,
    by_symbol=None,
):
    """테스트용 성적표 생성 헬퍼.

    Args:
        sufficient: data_coverage.sufficient 값
        overall_accuracy: 전체 적중률
        fg_zones: F&G 구간별 통계 (dict)
        by_symbol: 종목별 통계 (dict)
    """
    empty_bucket = {'total': 0, 'correct': 0, 'accuracy_pct': None, 'avg_return_5d': None}

    default_fg = {
        '0-25': dict(empty_bucket),
        '25-50': dict(empty_bucket),
        '50-75': dict(empty_bucket),
        '75-100': dict(empty_bucket),
    }
    if fg_zones:
        default_fg.update(fg_zones)

    return {
        'date': '2026-03-17',
        'lookback_days': 30,
        'data_coverage': {
            'total_signals': 100 if sufficient else 5,
            'with_outcomes': 50 if sufficient else 3,
            'coverage_pct': 50.0 if sufficient else 30.0,
            'sufficient': sufficient,
        },
        'overall_accuracy_pct': overall_accuracy,
        'by_fear_greed_zone': default_fg,
        'by_signal_type': {
            'strong_bullish': dict(empty_bucket),
            'bullish': dict(empty_bucket),
            'neutral': dict(empty_bucket),
            'bearish': dict(empty_bucket),
            'strong_bearish': dict(empty_bucket),
        },
        'by_symbol': by_symbol or {},
        'best_conditions': None,
        'worst_conditions': None,
    }


def _make_mock_tracker(scorecard):
    """SignalTracker mock 생성. _get_fear_greed_zone은 실제 구현 사용."""
    mock = MagicMock()
    mock.return_value.generate_scorecard.return_value = scorecard
    # 실제 static method를 유지 (F&G 구간 분류가 올바르게 동작하도록)
    mock._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone
    return mock


class TestContextFilterDisabled:
    """기본 비활성 상태 테스트"""

    def test_filter_disabled_by_default(self):
        """context_filter_config 없으면 기본 비활성"""
        pipeline = SignalPipeline()
        assert pipeline._context_filter_config.get('enabled', False) is False

    def test_filter_passes_signal_when_disabled(self):
        """비활성 상태에서 process()가 시그널을 그대로 통과"""
        pipeline = SignalPipeline()

        signal, regime = pipeline.process(
            signal=1,
            symbol='AAPL',
            df=MagicMock(),
            info={'close': 150.0},
            timestamp=datetime.now(),
            positions={'AAPL': 0},
            capital=10000.0,
            initial_capital=10000.0,
            strategy_name='RSI',
        )

        assert signal == 1

    def test_filter_disabled_explicitly(self):
        """enabled=False 명시 시 필터 스킵"""
        config = {'enabled': False, 'min_accuracy': 35.0, 'min_sample_size': 5}
        pipeline = SignalPipeline(context_filter_config=config)

        signal, regime = pipeline.process(
            signal=-1,
            symbol='AAPL',
            df=MagicMock(),
            info={'close': 150.0},
            timestamp=datetime.now(),
            positions={'AAPL': 10.0},
            capital=5000.0,
            initial_capital=10000.0,
            strategy_name='RSI',
        )

        assert signal == -1


class TestContextFilterEnabled:
    """활성 상태 테스트"""

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_rejects_low_accuracy_fg_zone(self, MockTracker):
        """F&G 구간 적중률 < min_accuracy → 시그널 거부"""
        scorecard = _make_scorecard(
            sufficient=True,
            fg_zones={
                '0-25': {'total': 10, 'correct': 2, 'accuracy_pct': 20.0, 'avg_return_5d': -1.5},
            },
        )
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
            'current_fear_greed': 15.0,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='AAPL', regime_result=None, fear_greed_value=15.0
        )
        assert result == 0

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_rejects_low_accuracy_symbol(self, MockTracker):
        """종목 적중률 < min_accuracy → 시그널 거부"""
        scorecard = _make_scorecard(
            sufficient=True,
            by_symbol={
                'TSLA': {'total': 8, 'correct': 1, 'accuracy_pct': 12.5, 'avg_return_5d': -3.0},
            },
        )
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='TSLA', regime_result=None, fear_greed_value=None
        )
        assert result == 0

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_passes_high_accuracy(self, MockTracker):
        """적중률 >= min_accuracy → 시그널 통과"""
        scorecard = _make_scorecard(
            sufficient=True,
            fg_zones={
                '50-75': {'total': 10, 'correct': 7, 'accuracy_pct': 70.0, 'avg_return_5d': 2.5},
            },
            by_symbol={
                'AAPL': {'total': 10, 'correct': 6, 'accuracy_pct': 60.0, 'avg_return_5d': 1.8},
            },
        )
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
            'current_fear_greed': 60.0,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='AAPL', regime_result=None, fear_greed_value=60.0
        )
        assert result == 1

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_skips_insufficient_samples(self, MockTracker):
        """샘플 < min_sample_size → 해당 조건 필터 스킵 (통과)"""
        scorecard = _make_scorecard(
            sufficient=True,
            fg_zones={
                '75-100': {'total': 2, 'correct': 0, 'accuracy_pct': 0.0, 'avg_return_5d': -5.0},
            },
            by_symbol={
                'NVDA': {'total': 3, 'correct': 0, 'accuracy_pct': 0.0, 'avg_return_5d': -4.0},
            },
        )
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
            'current_fear_greed': 80.0,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='NVDA', regime_result=None, fear_greed_value=80.0
        )
        # F&G 구간 total=2 < 5, 종목 total=3 < 5 → 두 조건 모두 스킵, 시그널 통과
        assert result == 1

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_skips_insufficient_data_coverage(self, MockTracker):
        """data_coverage.sufficient == False → pass-through"""
        scorecard = _make_scorecard(sufficient=False)
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
            'current_fear_greed': 10.0,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='AAPL', regime_result=None, fear_greed_value=10.0
        )
        assert result == 1

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_cache_same_day(self, MockTracker):
        """같은 날짜 내 두 번 호출 → generate_scorecard 1회만 호출"""
        scorecard = _make_scorecard(sufficient=False)
        mock_instance = MagicMock()
        mock_instance.generate_scorecard.return_value = scorecard
        MockTracker.return_value = mock_instance
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {'enabled': True, 'min_accuracy': 35.0, 'min_sample_size': 5}
        pipeline = SignalPipeline(context_filter_config=config)

        # 첫 번째 호출
        pipeline._context_filter(signal=1, symbol='AAPL', regime_result=None)
        # 두 번째 호출 (같은 날)
        pipeline._context_filter(signal=-1, symbol='MSFT', regime_result=None)

        # generate_scorecard는 1회만 호출
        assert mock_instance.generate_scorecard.call_count == 1

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_cache_refresh_new_day(self, MockTracker):
        """날짜 변경 시 캐시 갱신 → generate_scorecard 재호출"""
        scorecard = _make_scorecard(sufficient=False)
        mock_instance = MagicMock()
        mock_instance.generate_scorecard.return_value = scorecard
        MockTracker.return_value = mock_instance
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {'enabled': True, 'min_accuracy': 35.0, 'min_sample_size': 5}
        pipeline = SignalPipeline(context_filter_config=config)

        # 첫 번째 호출
        pipeline._context_filter(signal=1, symbol='AAPL', regime_result=None)
        assert mock_instance.generate_scorecard.call_count == 1

        # 날짜를 강제로 변경하여 캐시 무효화
        pipeline._scorecard_cache_date = '2026-03-16'

        # 두 번째 호출 (다른 날)
        pipeline._context_filter(signal=1, symbol='AAPL', regime_result=None)
        assert mock_instance.generate_scorecard.call_count == 2

    def test_hold_signal_not_filtered(self):
        """signal == 0 (HOLD)은 context filter에 진입하지 않음"""
        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        # process()에서 signal==0이면 context filter 진입 안 함
        signal, regime = pipeline.process(
            signal=0,
            symbol='AAPL',
            df=MagicMock(),
            info={'close': 150.0},
            timestamp=datetime.now(),
            positions={'AAPL': 0},
            capital=10000.0,
            initial_capital=10000.0,
            strategy_name='RSI',
        )

        assert signal == 0

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_sell_signal_rejected(self, MockTracker):
        """SELL 시그널도 필터링됨 (signal == -1)"""
        scorecard = _make_scorecard(
            sufficient=True,
            by_symbol={
                'AAPL': {'total': 10, 'correct': 2, 'accuracy_pct': 20.0, 'avg_return_5d': -2.0},
            },
        )
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=-1, symbol='AAPL', regime_result=None, fear_greed_value=None
        )
        assert result == 0

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_error_fails_open(self, MockTracker):
        """SignalTracker 에러 시 fail-open (시그널 통과)"""
        MockTracker.side_effect = Exception("DB connection failed")

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='AAPL', regime_result=None, fear_greed_value=20.0
        )
        # 에러 발생 → fail-open → 원본 시그널 통과
        assert result == 1

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_fg_zone_rejects_but_symbol_passes(self, MockTracker):
        """F&G 구간에서 거부되면 종목 체크까지 도달하지 않음"""
        scorecard = _make_scorecard(
            sufficient=True,
            fg_zones={
                '0-25': {'total': 10, 'correct': 1, 'accuracy_pct': 10.0, 'avg_return_5d': -3.0},
            },
            by_symbol={
                'AAPL': {'total': 10, 'correct': 8, 'accuracy_pct': 80.0, 'avg_return_5d': 2.0},
            },
        )
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
            'current_fear_greed': 15.0,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='AAPL', regime_result=None, fear_greed_value=15.0
        )
        # F&G 0-25 구간 적중률 10% < 35% → 거부 (종목은 80%지만 도달하지 않음)
        assert result == 0

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_filter_no_fg_value_skips_fg_check(self, MockTracker):
        """fear_greed_value가 None이면 F&G 구간 검사 스킵"""
        scorecard = _make_scorecard(
            sufficient=True,
            fg_zones={
                '0-25': {'total': 10, 'correct': 1, 'accuracy_pct': 10.0, 'avg_return_5d': -3.0},
            },
            by_symbol={
                'AAPL': {'total': 10, 'correct': 8, 'accuracy_pct': 80.0, 'avg_return_5d': 2.0},
            },
        )
        MockTracker.return_value.generate_scorecard.return_value = scorecard
        MockTracker._get_fear_greed_zone = _RealSignalTracker._get_fear_greed_zone

        config = {
            'enabled': True,
            'min_accuracy': 35.0,
            'min_sample_size': 5,
        }
        pipeline = SignalPipeline(context_filter_config=config)

        result = pipeline._context_filter(
            signal=1, symbol='AAPL', regime_result=None, fear_greed_value=None
        )
        # F&G 값 없음 → F&G 체크 스킵, 종목 적중률 80% >= 35% → 통과
        assert result == 1
