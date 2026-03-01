"""
SignalTracker 단위 테스트
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def db_path(tmp_path):
    """테스트용 임시 DB 경로"""
    return str(tmp_path / "test_signal.db")


@pytest.fixture
def tracker(db_path):
    """테스트용 SignalTracker"""
    from trading_bot.signal_tracker import SignalTracker

    # DB 테이블 초기화 (TradingDatabase가 생성하는 테이블 포함)
    from trading_bot.database import TradingDatabase
    TradingDatabase(db_path=db_path)

    return SignalTracker(db_path=db_path)


@pytest.fixture
def sample_analysis_result():
    """샘플 분석 결과"""
    return {
        'date': '2026-02-28',
        'stocks': {
            'AAPL': {
                'price': {'last': 185.50, 'change': 1.2},
                'indicators': {
                    'rsi': {'value': 55, 'signal': 'neutral'},
                    'macd': {'signal': 'bullish'},
                },
            },
            'MSFT': {
                'price': {'last': 420.30, 'change': -0.5},
                'indicators': {
                    'rsi': {'value': 62, 'signal': 'neutral'},
                    'macd': {'signal': 'bearish'},
                },
            },
        },
        'intelligence': {
            'overall': {
                'score': 15.5,
                'signal': 'bullish',
                'interpretation': 'Moderate bullish',
            },
            'layers': {
                'macro_regime': {'score': 20, 'metrics': {}},
                'sentiment': {
                    'score': -5,
                    'metrics': {
                        'news_sentiment': {'score': -10},
                    },
                },
                'enhanced_technicals': {'score': 25, 'metrics': {}},
            },
        },
        'fear_greed_index': {
            'current': {'value': 42, 'text': 'Fear'},
        },
    }


class TestSignalTrackerLogSignals:
    """log_daily_signals 테스트"""

    def test_log_signals_basic(self, tracker, sample_analysis_result):
        """기본 시그널 기록"""
        count = tracker.log_daily_signals(sample_analysis_result)
        assert count == 2  # AAPL, MSFT

    def test_log_signals_upsert(self, tracker, sample_analysis_result):
        """동일 날짜/종목 UPSERT"""
        tracker.log_daily_signals(sample_analysis_result)
        # 같은 데이터 다시 기록 (UPDATE)
        sample_analysis_result['intelligence']['overall']['score'] = 25.0
        count = tracker.log_daily_signals(sample_analysis_result)
        assert count == 2

        # DB에서 확인 — 최신 값으로 업데이트되어야 함
        conn = tracker._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT overall_score FROM daily_market_signals WHERE symbol='AAPL'")
        row = cursor.fetchone()
        assert row['overall_score'] == 25.0
        conn.close()

    def test_log_signals_empty_stocks(self, tracker):
        """빈 stocks 데이터"""
        count = tracker.log_daily_signals({'stocks': {}})
        assert count == 0

    def test_log_signals_no_intelligence(self, tracker):
        """intelligence 데이터 없이 기록"""
        result = {
            'date': '2026-02-28',
            'stocks': {
                'AAPL': {'price': {'last': 185.0}, 'indicators': {}},
            },
        }
        count = tracker.log_daily_signals(result)
        assert count == 1

    def test_log_signals_no_price(self, tracker):
        """가격 없는 종목은 건너뜀"""
        result = {
            'date': '2026-02-28',
            'stocks': {
                'AAPL': {'price': {}, 'indicators': {}},
            },
        }
        count = tracker.log_daily_signals(result)
        assert count == 0

    def test_log_signals_db_contents(self, tracker, sample_analysis_result):
        """DB에 올바른 데이터가 저장되는지 확인"""
        tracker.log_daily_signals(sample_analysis_result)

        conn = tracker._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_market_signals ORDER BY symbol")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2
        aapl = rows[0]
        assert aapl['symbol'] == 'AAPL'
        assert aapl['market_price'] == 185.50
        assert aapl['overall_score'] == 15.5
        assert aapl['overall_signal'] == 'bullish'
        assert aapl['fear_greed_value'] == 42
        assert aapl['news_sentiment_score'] == -10

        layer_scores = json.loads(aapl['layer_scores'])
        assert 'macro_regime' in layer_scores
        assert layer_scores['macro_regime'] == 20


class TestSignalTrackerOutcomes:
    """update_pending_outcomes 테스트"""

    def test_update_outcomes_basic(self, tracker, sample_analysis_result):
        """기본 수익률 측정"""
        # 과거 시그널 기록 (7일 전)
        past_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        sample_analysis_result['date'] = past_date
        tracker.log_daily_signals(sample_analysis_result)

        # mock price_fetcher: 항상 +2% 상승
        def mock_fetcher(symbol, date_str):
            base = 185.50 if symbol == 'AAPL' else 420.30
            return base * 1.02

        updated = tracker.update_pending_outcomes(price_fetcher=mock_fetcher)
        assert updated == 2  # AAPL, MSFT

        # DB 확인
        conn = tracker._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.* FROM signal_outcomes o
            JOIN daily_market_signals s ON o.signal_id = s.signal_id
            WHERE s.symbol = 'AAPL'
        """)
        outcome = cursor.fetchone()
        conn.close()

        assert outcome is not None
        assert outcome['return_1d'] is not None
        assert outcome['return_5d'] is not None
        # bullish signal + positive return → correct
        assert outcome['outcome_correct'] == 1

    def test_update_outcomes_no_pending(self, tracker):
        """대기 시그널 없을 때"""
        updated = tracker.update_pending_outcomes(price_fetcher=lambda s, d: None)
        assert updated == 0

    def test_update_outcomes_price_fetcher_fails(self, tracker, sample_analysis_result):
        """price_fetcher가 None 반환 시"""
        past_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        sample_analysis_result['date'] = past_date
        tracker.log_daily_signals(sample_analysis_result)

        updated = tracker.update_pending_outcomes(price_fetcher=lambda s, d: None)
        assert updated == 0

    def test_update_outcomes_bearish_correct(self, tracker):
        """약세 시그널 적중"""
        past_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        result = {
            'date': past_date,
            'stocks': {'AAPL': {'price': {'last': 185.0}, 'indicators': {}}},
            'intelligence': {
                'overall': {'score': -20, 'signal': 'bearish'},
                'layers': {},
            },
        }
        tracker.log_daily_signals(result)

        # 가격 하락 시나리오
        def mock_fetcher(symbol, date_str):
            return 180.0  # -2.7%

        updated = tracker.update_pending_outcomes(price_fetcher=mock_fetcher)
        assert updated == 1

        conn = tracker._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT outcome_correct FROM signal_outcomes")
        row = cursor.fetchone()
        conn.close()
        assert row['outcome_correct'] == 1  # bearish + 하락 = 적중

    def test_update_outcomes_recent_signal_no_measurement(self, tracker, sample_analysis_result):
        """오늘 기록된 시그널은 1일 수익률도 측정 불가"""
        today = datetime.now().strftime('%Y-%m-%d')
        sample_analysis_result['date'] = today
        tracker.log_daily_signals(sample_analysis_result)

        def mock_fetcher(symbol, date_str):
            return 190.0

        updated = tracker.update_pending_outcomes(price_fetcher=mock_fetcher)
        # 오늘 시그널은 days_elapsed=0이므로 어떤 수익률도 측정 불가
        assert updated == 0


class TestSignalTrackerAccuracy:
    """calculate_accuracy_stats + get_recent_accuracy_summary 테스트"""

    def _setup_signals_with_outcomes(self, tracker, n_days=5, correct_ratio=0.6):
        """n일치 시그널 + 수익률 데이터 생성"""
        conn = tracker._get_connection()
        cursor = conn.cursor()

        for i in range(n_days):
            date = (datetime.now() - timedelta(days=30 - i)).strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO daily_market_signals
                    (date, symbol, overall_score, overall_signal, layer_scores,
                     indicators, market_price)
                VALUES (?, 'AAPL', 15.0, 'bullish', ?, '{}', 185.0)
            """, (date, json.dumps({'macro_regime': 20, 'sentiment': -5})))

            signal_id = cursor.lastrowid
            is_correct = 1 if i < int(n_days * correct_ratio) else 0
            ret = 2.0 if is_correct else -2.0
            cursor.execute("""
                INSERT INTO signal_outcomes
                    (signal_id, return_1d, return_5d, return_20d, outcome_correct, measured_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (signal_id, ret * 0.3, ret, ret * 2, is_correct))

        conn.commit()
        conn.close()

    def test_calculate_accuracy_stats(self, tracker):
        """정확도 통계 계산"""
        self._setup_signals_with_outcomes(tracker, n_days=10, correct_ratio=0.7)

        today = datetime.now().strftime('%Y-%m-%d')
        stats = tracker.calculate_accuracy_stats(today, lookback_days=60)

        assert stats['overall']['total_signals'] == 10
        assert stats['overall']['correct_count'] == 7
        assert abs(stats['overall']['accuracy_pct'] - 70.0) < 0.1

        # 레이어 통계도 있어야 함
        assert 'macro_regime' in stats['layers']

    def test_calculate_accuracy_no_data(self, tracker):
        """데이터 없을 때"""
        today = datetime.now().strftime('%Y-%m-%d')
        stats = tracker.calculate_accuracy_stats(today)
        assert stats['overall']['total_signals'] == 0

    def test_get_recent_accuracy_summary(self, tracker):
        """최신 정확도 요약"""
        self._setup_signals_with_outcomes(tracker, n_days=10, correct_ratio=0.6)

        today = datetime.now().strftime('%Y-%m-%d')
        tracker.calculate_accuracy_stats(today, lookback_days=60)

        summary = tracker.get_recent_accuracy_summary(lookback_days=60)
        assert summary is not None
        assert summary['overall']['total_signals'] == 10

    def test_get_recent_accuracy_no_stats(self, tracker):
        """통계 없을 때 None 반환"""
        summary = tracker.get_recent_accuracy_summary()
        assert summary is None


class TestYfPriceFetcher:
    """_yf_price_fetcher 테스트"""

    @patch('yfinance.Ticker')
    def test_yf_price_fetcher_success(self, mock_ticker_cls):
        from trading_bot.signal_tracker import _yf_price_fetcher
        import pandas as pd

        mock_hist = pd.DataFrame({'Close': [185.50]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        mock_ticker_cls.return_value = mock_ticker

        price = _yf_price_fetcher('AAPL', '2026-02-20')
        assert price == 185.50

    @patch('yfinance.Ticker')
    def test_yf_price_fetcher_empty(self, mock_ticker_cls):
        from trading_bot.signal_tracker import _yf_price_fetcher
        import pandas as pd

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        price = _yf_price_fetcher('INVALID', '2026-02-20')
        assert price is None

    @patch('yfinance.Ticker')
    def test_yf_price_fetcher_exception(self, mock_ticker_cls):
        from trading_bot.signal_tracker import _yf_price_fetcher

        mock_ticker_cls.side_effect = Exception("API error")

        price = _yf_price_fetcher('AAPL', '2026-02-20')
        assert price is None
