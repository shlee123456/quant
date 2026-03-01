"""
시그널 성과 추적기 - 일별 시장 시그널 기록 및 성과 측정

MarketAnalyzer + MarketIntelligence 결과를 DB에 기록하고,
과거 시그널의 실제 수익률을 비동기 측정하여 정확도를 계산합니다.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _yf_price_fetcher(symbol: str, date_str: str) -> Optional[float]:
    """yfinance로 특정 날짜의 종가 조회"""
    try:
        import yfinance as yf
        from datetime import datetime, timedelta

        dt = datetime.strptime(date_str, '%Y-%m-%d')
        start = dt.strftime('%Y-%m-%d')
        end = (dt + timedelta(days=7)).strftime('%Y-%m-%d')

        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end)
        if hist.empty:
            return None
        return float(hist['Close'].iloc[0])
    except Exception as e:
        logger.debug(f"yfinance 가격 조회 실패 ({symbol}, {date_str}): {e}")
        return None


class SignalTracker:
    """일별 시장 시그널 기록 및 성과 추적"""

    def __init__(self, db_path: str = None):
        from trading_bot.config import Config
        _cfg = Config()
        self.db_path = db_path or _cfg.get('database.path', 'data/paper_trading.db')

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def log_daily_signals(self, analysis_result: Dict) -> int:
        """MarketAnalyzer + MarketIntelligence 결과를 DB에 기록.

        Returns: 기록된 종목 수
        """
        stocks = analysis_result.get('stocks', {})
        if not stocks:
            return 0

        intelligence = analysis_result.get('intelligence', {})
        overall = intelligence.get('overall', {})
        layers = intelligence.get('layers', {})
        fear_greed = analysis_result.get('fear_greed_index', {})

        today = analysis_result.get('date', datetime.now().strftime('%Y-%m-%d'))

        # Fear & Greed 값 추출
        fg_value = None
        if fear_greed:
            current = fear_greed.get('current', {})
            if isinstance(current, dict):
                fg_value = current.get('value')

        # 뉴스 감성 점수 추출
        news_sentiment = None
        sentiment_layer = layers.get('sentiment', {})
        if sentiment_layer:
            metrics = sentiment_layer.get('metrics', {})
            ns = metrics.get('news_sentiment', {})
            if isinstance(ns, dict):
                news_sentiment = ns.get('score')
            elif isinstance(ns, (int, float)):
                news_sentiment = ns

        # layer_scores 구축
        layer_scores = {}
        for layer_name, layer_data in layers.items():
            if isinstance(layer_data, dict) and 'score' in layer_data:
                layer_scores[layer_name] = layer_data['score']

        overall_score = overall.get('score')
        overall_signal = overall.get('signal')

        conn = self._get_connection()
        count = 0
        try:
            cursor = conn.cursor()
            for symbol, stock_data in stocks.items():
                price_data = stock_data.get('price', {})
                market_price = price_data.get('last')
                if market_price is None:
                    continue

                indicators = stock_data.get('indicators', {})

                cursor.execute("""
                    INSERT INTO daily_market_signals
                        (date, symbol, overall_score, overall_signal, layer_scores,
                         indicators, market_price, fear_greed_value, news_sentiment_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date, symbol) DO UPDATE SET
                        overall_score = excluded.overall_score,
                        overall_signal = excluded.overall_signal,
                        layer_scores = excluded.layer_scores,
                        indicators = excluded.indicators,
                        market_price = excluded.market_price,
                        fear_greed_value = excluded.fear_greed_value,
                        news_sentiment_score = excluded.news_sentiment_score
                """, (
                    today, symbol, overall_score, overall_signal,
                    json.dumps(layer_scores) if layer_scores else None,
                    json.dumps(indicators) if indicators else None,
                    market_price, fg_value, news_sentiment,
                ))
                count += 1

            conn.commit()
        finally:
            conn.close()

        return count

    def update_pending_outcomes(self, price_fetcher: Callable = None) -> int:
        """과거 시그널 중 아직 측정하지 않은 건의 실제 수익률 보충.

        Returns: 업데이트 건수
        """
        if price_fetcher is None:
            price_fetcher = _yf_price_fetcher

        conn = self._get_connection()
        updated = 0
        try:
            cursor = conn.cursor()

            # signal_outcomes에 아직 행이 없는 시그널 조회
            cursor.execute("""
                SELECT s.signal_id, s.date, s.symbol, s.market_price, s.overall_signal
                FROM daily_market_signals s
                LEFT JOIN signal_outcomes o ON s.signal_id = o.signal_id
                WHERE o.signal_id IS NULL
                ORDER BY s.date ASC
            """)
            pending = cursor.fetchall()

            today = datetime.now().date()

            for row in pending:
                signal_id = row['signal_id']
                signal_date = datetime.strptime(row['date'], '%Y-%m-%d').date()
                symbol = row['symbol']
                market_price = row['market_price']
                overall_signal = row['overall_signal']

                if market_price is None or market_price <= 0:
                    continue

                days_elapsed = (today - signal_date).days

                return_1d = None
                return_5d = None
                return_20d = None
                max_drawdown_5d = None
                outcome_correct = None

                # 1일 수익률
                if days_elapsed >= 1:
                    target_date = signal_date + timedelta(days=1)
                    price = price_fetcher(symbol, target_date.strftime('%Y-%m-%d'))
                    if price is not None:
                        return_1d = (price - market_price) / market_price * 100

                # 5일 수익률
                if days_elapsed >= 5:
                    target_date = signal_date + timedelta(days=5)
                    price = price_fetcher(symbol, target_date.strftime('%Y-%m-%d'))
                    if price is not None:
                        return_5d = (price - market_price) / market_price * 100

                    # 5일 내 최대 낙폭 추정 (3일차 가격으로 근사)
                    mid_date = signal_date + timedelta(days=3)
                    mid_price = price_fetcher(symbol, mid_date.strftime('%Y-%m-%d'))
                    if mid_price is not None and price is not None:
                        min_price = min(mid_price, price)
                        max_drawdown_5d = (min_price - market_price) / market_price * 100
                        if max_drawdown_5d > 0:
                            max_drawdown_5d = 0.0

                # 20일 수익률
                if days_elapsed >= 20:
                    target_date = signal_date + timedelta(days=20)
                    price = price_fetcher(symbol, target_date.strftime('%Y-%m-%d'))
                    if price is not None:
                        return_20d = (price - market_price) / market_price * 100

                # 적중 여부 판정 (5일 수익률 기준)
                if return_5d is not None and overall_signal:
                    signal_lower = overall_signal.lower()
                    if signal_lower in ('bullish', 'strong_bullish'):
                        outcome_correct = 1 if return_5d > 0 else 0
                    elif signal_lower in ('bearish', 'strong_bearish'):
                        outcome_correct = 1 if return_5d < 0 else 0
                    else:
                        # neutral 시그널 — 5% 이내 변동이면 적중
                        outcome_correct = 1 if abs(return_5d) < 5 else 0

                # 최소 1개 이상 수익률이 계산된 경우에만 저장
                if any(v is not None for v in [return_1d, return_5d, return_20d]):
                    cursor.execute("""
                        INSERT OR REPLACE INTO signal_outcomes
                            (signal_id, return_1d, return_5d, return_20d,
                             max_drawdown_5d, outcome_correct, measured_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        signal_id, return_1d, return_5d, return_20d,
                        max_drawdown_5d, outcome_correct,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    ))
                    updated += 1

            conn.commit()
        finally:
            conn.close()

        return updated

    def calculate_accuracy_stats(self, date: str, lookback_days: int = 30) -> Dict:
        """특정 날짜 기준 최근 N일간 레이어별 정확도 계산."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            start_date = (
                datetime.strptime(date, '%Y-%m-%d') - timedelta(days=lookback_days)
            ).strftime('%Y-%m-%d')

            # 전체 정확도
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN o.outcome_correct = 1 THEN 1 ELSE 0 END) as correct,
                    AVG(CASE WHEN s.overall_signal IN ('bullish', 'strong_bullish')
                        THEN o.return_5d END) as avg_return_bullish,
                    AVG(CASE WHEN s.overall_signal IN ('bearish', 'strong_bearish')
                        THEN o.return_5d END) as avg_return_bearish
                FROM daily_market_signals s
                JOIN signal_outcomes o ON s.signal_id = o.signal_id
                WHERE s.date BETWEEN ? AND ?
                  AND o.outcome_correct IS NOT NULL
            """, (start_date, date))

            row = cursor.fetchone()
            total = row['total'] or 0
            correct = row['correct'] or 0

            overall_stats = {
                'total_signals': total,
                'correct_count': correct,
                'accuracy_pct': (correct / total * 100) if total > 0 else None,
                'avg_return_when_bullish': row['avg_return_bullish'],
                'avg_return_when_bearish': row['avg_return_bearish'],
            }

            # overall 통계 저장
            cursor.execute("""
                INSERT INTO signal_accuracy_stats
                    (date, layer_name, lookback_days, total_signals, correct_count,
                     accuracy_pct, avg_return_when_bullish, avg_return_when_bearish)
                VALUES (?, 'overall', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, layer_name, lookback_days) DO UPDATE SET
                    total_signals = excluded.total_signals,
                    correct_count = excluded.correct_count,
                    accuracy_pct = excluded.accuracy_pct,
                    avg_return_when_bullish = excluded.avg_return_when_bullish,
                    avg_return_when_bearish = excluded.avg_return_when_bearish,
                    calculated_at = datetime('now')
            """, (
                date, lookback_days, total, correct,
                overall_stats['accuracy_pct'],
                overall_stats['avg_return_when_bullish'],
                overall_stats['avg_return_when_bearish'],
            ))

            # 레이어별 정확도 계산
            layer_stats = {}
            cursor.execute("""
                SELECT s.signal_id, s.layer_scores, o.outcome_correct
                FROM daily_market_signals s
                JOIN signal_outcomes o ON s.signal_id = o.signal_id
                WHERE s.date BETWEEN ? AND ?
                  AND o.outcome_correct IS NOT NULL
                  AND s.layer_scores IS NOT NULL
            """, (start_date, date))

            layer_data: Dict[str, Dict[str, int]] = {}
            for sig_row in cursor.fetchall():
                try:
                    scores = json.loads(sig_row['layer_scores'])
                except (json.JSONDecodeError, TypeError):
                    continue

                is_correct = sig_row['outcome_correct']
                for layer_name, score in scores.items():
                    if layer_name not in layer_data:
                        layer_data[layer_name] = {'total': 0, 'correct': 0}
                    # 레이어 점수가 양수이고 전체 적중이면 적중 처리
                    layer_data[layer_name]['total'] += 1
                    if is_correct:
                        layer_data[layer_name]['correct'] += 1

            for layer_name, counts in layer_data.items():
                acc = (counts['correct'] / counts['total'] * 100) if counts['total'] > 0 else None
                layer_stats[layer_name] = {
                    'total_signals': counts['total'],
                    'correct_count': counts['correct'],
                    'accuracy_pct': acc,
                }

                cursor.execute("""
                    INSERT INTO signal_accuracy_stats
                        (date, layer_name, lookback_days, total_signals, correct_count, accuracy_pct)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date, layer_name, lookback_days) DO UPDATE SET
                        total_signals = excluded.total_signals,
                        correct_count = excluded.correct_count,
                        accuracy_pct = excluded.accuracy_pct,
                        calculated_at = datetime('now')
                """, (
                    date, layer_name, lookback_days,
                    counts['total'], counts['correct'], acc,
                ))

            conn.commit()

            return {
                'date': date,
                'lookback_days': lookback_days,
                'overall': overall_stats,
                'layers': layer_stats,
            }

        finally:
            conn.close()

    def get_recent_accuracy_summary(self, lookback_days: int = 30) -> Optional[Dict]:
        """RAG 컨텍스트용. signal_accuracy_stats에서 최신 데이터 반환."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 최신 날짜 조회
            cursor.execute("""
                SELECT MAX(date) as latest_date
                FROM signal_accuracy_stats
                WHERE lookback_days = ?
            """, (lookback_days,))
            row = cursor.fetchone()
            if not row or not row['latest_date']:
                # 데이터 없으면 계산 시도
                today = datetime.now().strftime('%Y-%m-%d')
                result = self.calculate_accuracy_stats(today, lookback_days)
                if result and result['overall']['total_signals'] > 0:
                    return result
                return None

            latest_date = row['latest_date']

            # 해당 날짜의 모든 레이어 통계 조회
            cursor.execute("""
                SELECT layer_name, total_signals, correct_count, accuracy_pct,
                       avg_return_when_bullish, avg_return_when_bearish
                FROM signal_accuracy_stats
                WHERE date = ? AND lookback_days = ?
            """, (latest_date, lookback_days))

            rows = cursor.fetchall()
            if not rows:
                return None

            overall = None
            layers = {}
            for r in rows:
                stats = {
                    'total_signals': r['total_signals'],
                    'correct_count': r['correct_count'],
                    'accuracy_pct': r['accuracy_pct'],
                    'avg_return_when_bullish': r['avg_return_when_bullish'],
                    'avg_return_when_bearish': r['avg_return_when_bearish'],
                }
                if r['layer_name'] == 'overall':
                    overall = stats
                else:
                    layers[r['layer_name']] = stats

            if not overall or overall['total_signals'] == 0:
                return None

            return {
                'date': latest_date,
                'lookback_days': lookback_days,
                'overall': overall,
                'layers': layers,
            }

        finally:
            conn.close()
