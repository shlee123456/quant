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


class TestSignalTrackerScorecard:
    """generate_scorecard() 테스트"""

    def _setup_diverse_signals(self, tracker, n_signals=20):
        """다양한 조건의 시그널 + 수익률 데이터 생성.

        - 여러 종목 (AAPL, MSFT, NVDA)
        - 여러 시그널 타입 (bullish, bearish, neutral, strong_bullish)
        - 여러 F&G 값 (15, 35, 55, 80)
        - 일부는 outcome_correct=1, 일부는 0
        """
        conn = tracker._get_connection()
        cursor = conn.cursor()

        # 시그널 데이터 정의 (symbol, signal, fg_value, correct, return_5d)
        test_data = [
            # AAPL - bullish, F&G=15 (0-25 구간)
            ('AAPL', 'bullish', 15.0, 1, 2.5),
            ('AAPL', 'bullish', 18.0, 1, 3.0),
            ('AAPL', 'bullish', 20.0, 0, -1.5),
            ('AAPL', 'bullish', 22.0, 1, 1.8),
            # MSFT - bearish, F&G=35 (25-50 구간)
            ('MSFT', 'bearish', 35.0, 1, -2.0),
            ('MSFT', 'bearish', 38.0, 0, 1.5),
            ('MSFT', 'bearish', 40.0, 1, -3.0),
            ('MSFT', 'bearish', 42.0, 0, 0.5),
            # NVDA - neutral, F&G=55 (50-75 구간)
            ('NVDA', 'neutral', 55.0, 1, 0.5),
            ('NVDA', 'neutral', 60.0, 0, 6.0),
            ('NVDA', 'neutral', 65.0, 1, -1.0),
            ('NVDA', 'neutral', 70.0, 1, 0.3),
            # AAPL - strong_bullish, F&G=80 (75-100 구간)
            ('AAPL', 'strong_bullish', 80.0, 1, 5.0),
            ('AAPL', 'strong_bullish', 85.0, 0, -2.0),
            ('AAPL', 'strong_bullish', 90.0, 1, 4.0),
            # MSFT - neutral, F&G=55 (50-75 구간)
            ('MSFT', 'neutral', 55.0, 0, 7.0),
            ('MSFT', 'neutral', 58.0, 1, 0.2),
            # NVDA - bullish, F&G=35 (25-50 구간)
            ('NVDA', 'bullish', 35.0, 1, 3.5),
            ('NVDA', 'bullish', 45.0, 0, -0.5),
            ('NVDA', 'bullish', 48.0, 1, 2.0),
        ]

        for i, (symbol, signal, fg_val, correct, ret_5d) in enumerate(test_data):
            date = (datetime.now() - timedelta(days=25 - i)).strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO daily_market_signals
                    (date, symbol, overall_score, overall_signal, layer_scores,
                     indicators, market_price, fear_greed_value)
                VALUES (?, ?, 10.0, ?, '{}', '{}', 100.0, ?)
            """, (date, symbol, signal, fg_val))

            signal_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO signal_outcomes
                    (signal_id, return_1d, return_5d, return_20d,
                     outcome_correct, measured_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (signal_id, ret_5d * 0.3, ret_5d, ret_5d * 2, correct))

        conn.commit()
        conn.close()

    def test_generate_scorecard_basic(self, tracker):
        """기본 성적표 구조 및 전체 정확도 검증"""
        self._setup_diverse_signals(tracker)

        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today, lookback_days=60)

        # 구조 확인
        assert 'date' in scorecard
        assert 'lookback_days' in scorecard
        assert 'data_coverage' in scorecard
        assert 'overall_accuracy_pct' in scorecard
        assert 'by_fear_greed_zone' in scorecard
        assert 'by_signal_type' in scorecard
        assert 'by_symbol' in scorecard
        assert 'best_conditions' in scorecard
        assert 'worst_conditions' in scorecard

        # data_coverage
        dc = scorecard['data_coverage']
        assert dc['total_signals'] == 20
        assert dc['with_outcomes'] == 20
        assert dc['coverage_pct'] == 100.0
        assert dc['sufficient'] is True

        # overall_accuracy: 20개 중 13개 correct
        assert scorecard['overall_accuracy_pct'] is not None
        assert abs(scorecard['overall_accuracy_pct'] - 65.0) < 0.1

    def test_generate_scorecard_by_fear_greed_zone(self, tracker):
        """F&G 구간별 적중률 검증"""
        self._setup_diverse_signals(tracker)

        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today, lookback_days=60)

        fg = scorecard['by_fear_greed_zone']

        # 4개 구간 존재
        assert '0-25' in fg
        assert '25-50' in fg
        assert '50-75' in fg
        assert '75-100' in fg

        # 0-25 구간: 4건 (AAPL bullish, fg=15,18,20,22), 3 correct
        zone_0_25 = fg['0-25']
        assert zone_0_25['total'] == 4
        assert zone_0_25['correct'] == 3
        assert abs(zone_0_25['accuracy_pct'] - 75.0) < 0.1
        assert zone_0_25['avg_return_5d'] is not None

        # 75-100 구간: 3건 (AAPL strong_bullish, fg=80,85,90), 2 correct
        zone_75_100 = fg['75-100']
        assert zone_75_100['total'] == 3
        assert zone_75_100['correct'] == 2

    def test_generate_scorecard_by_signal_type(self, tracker):
        """시그널 타입별 적중률 검증"""
        self._setup_diverse_signals(tracker)

        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today, lookback_days=60)

        st = scorecard['by_signal_type']

        # 5개 타입 존재
        assert 'strong_bullish' in st
        assert 'bullish' in st
        assert 'neutral' in st
        assert 'bearish' in st
        assert 'strong_bearish' in st

        # bullish: AAPL 4건 + NVDA 3건 = 7건, 5 correct
        assert st['bullish']['total'] == 7
        assert st['bullish']['correct'] == 5

        # bearish: MSFT 4건, 2 correct
        assert st['bearish']['total'] == 4
        assert st['bearish']['correct'] == 2
        assert abs(st['bearish']['accuracy_pct'] - 50.0) < 0.1

        # neutral: NVDA 4건 + MSFT 2건 = 6건, 4 correct
        assert st['neutral']['total'] == 6
        assert st['neutral']['correct'] == 4

        # strong_bullish: AAPL 3건, 2 correct
        assert st['strong_bullish']['total'] == 3
        assert st['strong_bullish']['correct'] == 2

        # strong_bearish: 0건
        assert st['strong_bearish']['total'] == 0

    def test_generate_scorecard_by_symbol(self, tracker):
        """종목별 적중률 검증"""
        self._setup_diverse_signals(tracker)

        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today, lookback_days=60)

        by_sym = scorecard['by_symbol']

        # 3개 종목
        assert 'AAPL' in by_sym
        assert 'MSFT' in by_sym
        assert 'NVDA' in by_sym

        # AAPL: 7건 (bullish 4 + strong_bullish 3), 5 correct
        assert by_sym['AAPL']['total'] == 7
        assert by_sym['AAPL']['correct'] == 5

        # MSFT: 6건 (bearish 4 + neutral 2), 3 correct
        assert by_sym['MSFT']['total'] == 6
        assert by_sym['MSFT']['correct'] == 3
        assert abs(by_sym['MSFT']['accuracy_pct'] - 50.0) < 0.1

        # NVDA: 7건 (neutral 4 + bullish 3), 5 correct
        assert by_sym['NVDA']['total'] == 7
        assert by_sym['NVDA']['correct'] == 5

        # avg_return_5d 존재
        assert by_sym['AAPL']['avg_return_5d'] is not None

    def test_generate_scorecard_no_data(self, tracker):
        """데이터 없을 때 빈 성적표 반환"""
        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today)

        assert scorecard['data_coverage']['total_signals'] == 0
        assert scorecard['data_coverage']['with_outcomes'] == 0
        assert scorecard['data_coverage']['sufficient'] is False
        assert scorecard['overall_accuracy_pct'] is None
        assert scorecard['best_conditions'] is None
        assert scorecard['worst_conditions'] is None

        # F&G 구간은 빈 상태
        for zone in ['0-25', '25-50', '50-75', '75-100']:
            assert scorecard['by_fear_greed_zone'][zone]['total'] == 0

        # 시그널 타입도 빈 상태
        for sig in ['strong_bullish', 'bullish', 'neutral', 'bearish', 'strong_bearish']:
            assert scorecard['by_signal_type'][sig]['total'] == 0

        # 종목별은 빈 딕셔너리
        assert scorecard['by_symbol'] == {}

    def test_generate_scorecard_insufficient_data(self, tracker):
        """데이터 부족 시 sufficient=False"""
        conn = tracker._get_connection()
        cursor = conn.cursor()

        # 5건만 생성 (< 10건)
        for i in range(5):
            date = (datetime.now() - timedelta(days=10 - i)).strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO daily_market_signals
                    (date, symbol, overall_score, overall_signal,
                     indicators, market_price, fear_greed_value)
                VALUES (?, 'AAPL', 10.0, 'bullish', '{}', 100.0, 30.0)
            """, (date,))
            signal_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO signal_outcomes
                    (signal_id, return_5d, outcome_correct, measured_at)
                VALUES (?, 2.0, 1, datetime('now'))
            """, (signal_id,))

        conn.commit()
        conn.close()

        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today, lookback_days=30)

        assert scorecard['data_coverage']['with_outcomes'] == 5
        assert scorecard['data_coverage']['sufficient'] is False
        assert scorecard['overall_accuracy_pct'] == 100.0  # 5/5 correct

    def test_generate_scorecard_best_worst_conditions(self, tracker):
        """best/worst conditions 텍스트 검증"""
        self._setup_diverse_signals(tracker)

        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today, lookback_days=60)

        # best/worst 존재
        assert scorecard['best_conditions'] is not None
        assert scorecard['worst_conditions'] is not None

        # 텍스트에 적중률 포함
        assert '적중률' in scorecard['best_conditions']
        assert '적중률' in scorecard['worst_conditions']

        # best의 적중률 >= worst의 적중률
        # best/worst에서 숫자 추출
        import re
        best_pct = float(re.search(r'(\d+\.\d+)%', scorecard['best_conditions']).group(1))
        worst_pct = float(re.search(r'(\d+\.\d+)%', scorecard['worst_conditions']).group(1))
        assert best_pct >= worst_pct

    def test_generate_scorecard_null_fear_greed(self, tracker):
        """fear_greed_value가 NULL인 행은 F&G 구간 분류에서 제외"""
        conn = tracker._get_connection()
        cursor = conn.cursor()

        # F&G가 NULL인 시그널 15건 생성
        for i in range(15):
            date = (datetime.now() - timedelta(days=20 - i)).strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO daily_market_signals
                    (date, symbol, overall_score, overall_signal,
                     indicators, market_price, fear_greed_value)
                VALUES (?, 'AAPL', 10.0, 'bullish', '{}', 100.0, NULL)
            """, (date,))
            signal_id = cursor.lastrowid
            correct = 1 if i % 2 == 0 else 0
            cursor.execute("""
                INSERT INTO signal_outcomes
                    (signal_id, return_5d, outcome_correct, measured_at)
                VALUES (?, 2.0, ?, datetime('now'))
            """, (signal_id, correct))

        conn.commit()
        conn.close()

        today = datetime.now().strftime('%Y-%m-%d')
        scorecard = tracker.generate_scorecard(today, lookback_days=30)

        # 전체 15건
        assert scorecard['data_coverage']['with_outcomes'] == 15
        assert scorecard['data_coverage']['sufficient'] is True

        # F&G 구간에는 0건 (모두 NULL이므로)
        for zone in ['0-25', '25-50', '50-75', '75-100']:
            assert scorecard['by_fear_greed_zone'][zone]['total'] == 0

        # overall_accuracy는 정상
        assert scorecard['overall_accuracy_pct'] is not None

        # by_signal_type에는 bullish 15건
        assert scorecard['by_signal_type']['bullish']['total'] == 15

        # by_symbol에는 AAPL 15건
        assert scorecard['by_symbol']['AAPL']['total'] == 15
