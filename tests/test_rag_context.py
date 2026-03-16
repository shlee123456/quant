"""
RAG 컨텍스트 및 Reflection 통합 테스트
"""

import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestBuildHistoricalPerformanceBlock:
    """_build_historical_performance_block() 테스트"""

    def test_returns_empty_when_disabled(self):
        """SIGNAL_TRACKING_ENABLED=false이면 빈 문자열"""
        with patch.dict(os.environ, {'SIGNAL_TRACKING_ENABLED': 'false'}):
            from trading_bot.parallel_prompt_builder import _build_historical_performance_block
            result = _build_historical_performance_block()
            assert result == ''

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_returns_empty_when_no_data(self, mock_tracker_cls):
        """데이터 없으면 빈 문자열"""
        mock_tracker = MagicMock()
        mock_tracker.get_recent_accuracy_summary.return_value = None
        mock_tracker_cls.return_value = mock_tracker

        with patch.dict(os.environ, {'SIGNAL_TRACKING_ENABLED': 'true'}):
            from trading_bot.parallel_prompt_builder import _build_historical_performance_block
            result = _build_historical_performance_block()
            assert result == ''

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_returns_block_with_valid_data(self, mock_tracker_cls):
        """유효 데이터로 RAG 블록 생성"""
        mock_tracker = MagicMock()
        mock_tracker.get_recent_accuracy_summary.return_value = {
            'date': '2026-02-28',
            'lookback_days': 30,
            'overall': {
                'total_signals': 100,
                'correct_count': 65,
                'accuracy_pct': 65.0,
                'avg_return_when_bullish': 1.5,
                'avg_return_when_bearish': -0.8,
            },
            'layers': {
                'macro_regime': {'total_signals': 100, 'correct_count': 72, 'accuracy_pct': 72.0},
                'sentiment': {'total_signals': 100, 'correct_count': 48, 'accuracy_pct': 48.0},
                'enhanced_technicals': {'total_signals': 100, 'correct_count': 60, 'accuracy_pct': 60.0},
            },
        }
        mock_tracker_cls.return_value = mock_tracker

        with patch.dict(os.environ, {'SIGNAL_TRACKING_ENABLED': 'true'}):
            from trading_bot.parallel_prompt_builder import _build_historical_performance_block
            result = _build_historical_performance_block()

            assert '과거 시그널 성과' in result
            assert '65.0%' in result
            assert '65/100건' in result
            assert 'Bullish' in result
            assert '+1.5%' in result
            assert 'Bearish' in result
            assert '-0.8%' in result
            assert 'macro_regime' in result
            assert 'sentiment' in result

    @patch('trading_bot.signal_tracker.SignalTracker')
    def test_returns_empty_when_zero_signals(self, mock_tracker_cls):
        """시그널이 0건이면 빈 문자열"""
        mock_tracker = MagicMock()
        mock_tracker.get_recent_accuracy_summary.return_value = {
            'date': '2026-02-28',
            'lookback_days': 30,
            'overall': {
                'total_signals': 0,
                'correct_count': 0,
                'accuracy_pct': None,
                'avg_return_when_bullish': None,
                'avg_return_when_bearish': None,
            },
            'layers': {},
        }
        mock_tracker_cls.return_value = mock_tracker

        with patch.dict(os.environ, {'SIGNAL_TRACKING_ENABLED': 'true'}):
            from trading_bot.parallel_prompt_builder import _build_historical_performance_block
            result = _build_historical_performance_block()
            assert result == ''

    def test_handles_exception_gracefully(self):
        """SignalTracker 예외 시 빈 문자열"""
        with patch.dict(os.environ, {'SIGNAL_TRACKING_ENABLED': 'true'}):
            with patch('trading_bot.signal_tracker.SignalTracker', side_effect=Exception("DB error")):
                from trading_bot.parallel_prompt_builder import _build_historical_performance_block
                result = _build_historical_performance_block()
                assert result == ''


class TestWorkerBReflection:
    """build_worker_b_prompt() Reflection 컨텍스트 테스트"""

    def test_worker_b_without_reflection(self):
        """worker_a_context 없이 기본 프롬프트"""
        from trading_bot.parallel_prompt_builder import build_worker_b_prompt

        market_data = {
            'stocks': {
                'AAPL': {
                    'price': {'last': 185.0, 'change_1d': 1.0, 'change_5d': 2.0, 'change_20d': 5.0},
                    'indicators': {'rsi': {'value': 55}, 'macd': {'signal': 'bullish'}, 'bollinger': {'signal': 'neutral'}, 'adx': {'value': 30}},
                    'regime': {'state': 'BULLISH', 'confidence': 0.8},
                    'patterns': {'support_levels': [180, 175]},
                },
            },
        }
        news_data = {'market_news': [], 'stock_news': {}}
        fear_greed_data = {'current': {'value': 50}}

        result = build_worker_b_prompt(market_data, news_data, fear_greed_data, '2026-03-01')
        prompt = result[0] if isinstance(result, tuple) else result
        assert 'Worker-A 분석 결과' not in prompt

    def test_worker_b_with_reflection(self):
        """worker_a_context 포함 시 교차 검증 블록 존재"""
        from trading_bot.parallel_prompt_builder import build_worker_b_prompt

        market_data = {
            'stocks': {
                'AAPL': {
                    'price': {'last': 185.0, 'change_1d': 1.0, 'change_5d': 2.0, 'change_20d': 5.0},
                    'indicators': {'rsi': {'value': 55}, 'macd': {'signal': 'bullish'}, 'bollinger': {'signal': 'neutral'}, 'adx': {'value': 30}},
                    'regime': {'state': 'BULLISH', 'confidence': 0.8},
                    'patterns': {'support_levels': [180, 175]},
                },
            },
        }
        news_data = {'market_news': [], 'stock_news': {}}
        fear_greed_data = {'current': {'value': 50}}

        result = build_worker_b_prompt(
            market_data, news_data, fear_greed_data, '2026-03-01',
            worker_a_context="시장 분석 결과: AAPL 강세 전환 예상",
        )
        prompt = result[0] if isinstance(result, tuple) else result
        assert 'Worker-A 분석 결과' in prompt or 'Worker-A' in prompt
        assert '교차 검증' in prompt or 'AAPL 강세 전환' in prompt
        assert 'AAPL 강세 전환' in prompt


class TestWorkerARagBlock:
    """build_worker_a_prompt() RAG 블록 테스트"""

    @patch('trading_bot.prompts.prompt_data._build_historical_performance_block')
    def test_worker_a_includes_rag(self, mock_rag):
        """Worker A에 RAG 블록 포함"""
        mock_rag.return_value = "\n## 과거 시그널 성과 (최근 30일)\n- 전체 정확도: 65%"

        from trading_bot.parallel_prompt_builder import build_worker_a_prompt

        market_data = {
            'market_summary': {'total_stocks': 1, 'bullish_count': 1, 'bearish_count': 0, 'sideways_count': 0, 'avg_rsi': 55, 'market_sentiment': 'Neutral', 'notable_events': []},
            'stocks': {
                'AAPL': {
                    'price': {'last': 185.0, 'change': 1.0, 'change_1d': 1.0, 'change_5d': 2.0, 'change_20d': 5.0},
                    'indicators': {'rsi': {'value': 55}, 'macd': {'signal': 'bullish'}},
                    'regime': {'state': 'BULLISH'},
                },
            },
        }

        prompt = build_worker_a_prompt(market_data, '2026-03-01')
        assert '과거 시그널 성과' in prompt
