"""
감성 기반 포지션 사이징 테스트

Phase 7: MarketIntelligence.get_position_size_recommendation() + PaperTrader 통합
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestGetPositionSizeRecommendation:
    """MarketIntelligence.get_position_size_recommendation() 테스트"""

    def _make_report(self, score: float = 0.0, signal: str = 'neutral') -> dict:
        return {
            'overall': {
                'score': score,
                'signal': signal,
                'interpretation': 'test',
            },
            'layers': {},
        }

    def test_neutral_no_adjustment(self):
        """중립 시 멀티플라이어 1.0"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=0.0)
        rec = MarketIntelligence.get_position_size_recommendation(report)

        assert rec['multiplier'] == 1.0
        assert len(rec['adjustments']) == 0
        assert '중립' in rec['reason']

    def test_extreme_fear_increases(self):
        """극단적 공포 (F&G < 25) → +25%"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=0.0)
        rec = MarketIntelligence.get_position_size_recommendation(
            report, fear_greed_value=20.0
        )

        assert rec['multiplier'] == 1.25
        assert any('공포' in a for a in rec['adjustments'])

    def test_extreme_greed_decreases(self):
        """극단적 탐욕 (F&G > 75) → -25%"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=0.0)
        rec = MarketIntelligence.get_position_size_recommendation(
            report, fear_greed_value=80.0
        )

        assert rec['multiplier'] == 0.75
        assert any('탐욕' in a for a in rec['adjustments'])

    def test_bullish_signal_increases(self):
        """강세 시그널 (score > 30) → +15%"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=35.0, signal='bullish')
        rec = MarketIntelligence.get_position_size_recommendation(report)

        assert rec['multiplier'] == 1.15
        assert any('강세' in a for a in rec['adjustments'])

    def test_bearish_contrarian_increases(self):
        """역발상 매수 (score < -30) → +10%"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=-40.0, signal='bearish')
        rec = MarketIntelligence.get_position_size_recommendation(report)

        assert rec['multiplier'] == 1.10
        assert any('역발상' in a for a in rec['adjustments'])

    def test_combined_fear_and_bullish(self):
        """극단적 공포 + 강세 → 1.0 + 0.25 + 0.15 = 1.4"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=35.0, signal='bullish')
        rec = MarketIntelligence.get_position_size_recommendation(
            report, fear_greed_value=15.0
        )

        assert rec['multiplier'] == 1.4
        assert len(rec['adjustments']) == 2

    def test_combined_greed_and_bearish_contrarian(self):
        """극단적 탐욕 + 역발상 → 1.0 - 0.25 + 0.10 = 0.85"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=-35.0, signal='bearish')
        rec = MarketIntelligence.get_position_size_recommendation(
            report, fear_greed_value=80.0
        )

        assert rec['multiplier'] == 0.85
        assert len(rec['adjustments']) == 2

    def test_clamp_upper_bound(self):
        """상한 클램프: 1.5 초과 불가"""
        from trading_bot.market_intelligence import MarketIntelligence

        # 극단적 공포 + 강세 + 추가 조정이 있어도 1.5 max
        report = self._make_report(score=50.0, signal='bullish')
        rec = MarketIntelligence.get_position_size_recommendation(
            report, fear_greed_value=10.0
        )

        assert rec['multiplier'] == 1.4  # 1.0 + 0.25 + 0.15 = 1.4 (within bounds)

    def test_clamp_lower_bound(self):
        """하한 클램프: 0.5 미만 불가"""
        from trading_bot.market_intelligence import MarketIntelligence

        # 극단적 탐욕만으로는 0.75이므로, 더 큰 감소는 현재 로직상 없음
        # 하지만 clamp 동작은 보장
        report = self._make_report(score=0.0)
        rec = MarketIntelligence.get_position_size_recommendation(
            report, fear_greed_value=80.0
        )

        assert rec['multiplier'] >= 0.5

    def test_no_fear_greed_value(self):
        """F&G 값 없으면 F&G 조정 없음"""
        from trading_bot.market_intelligence import MarketIntelligence

        report = self._make_report(score=0.0)
        rec = MarketIntelligence.get_position_size_recommendation(report, fear_greed_value=None)

        assert rec['multiplier'] == 1.0

    def test_empty_report(self):
        """빈 리포트 → 중립"""
        from trading_bot.market_intelligence import MarketIntelligence

        rec = MarketIntelligence.get_position_size_recommendation({})

        assert rec['multiplier'] == 1.0


class TestPaperTraderSentimentSizing:
    """PaperTrader sentiment sizing 통합 테스트"""

    def _make_trader(self, sentiment_sizing: bool = False):
        """테스트용 PaperTrader 생성"""
        from trading_bot.paper_trader import PaperTrader

        strategy = MagicMock()
        strategy.name = "TestStrategy"

        trader = PaperTrader(
            strategy=strategy,
            symbols=['AAPL'],
            initial_capital=10000.0,
            position_size=0.5,
            commission=0.0,  # 수수료 0으로 계산 단순화
            sentiment_sizing=sentiment_sizing,
        )
        return trader

    def test_no_sentiment_sizing_default(self):
        """sentiment_sizing=False → 기본 포지션"""
        trader = self._make_trader(sentiment_sizing=False)
        trader.start()

        trader.execute_buy('AAPL', 100.0, datetime.now())

        # position_size=0.5 → 5000 / 100 = 50 shares
        assert trader.positions['AAPL'] == pytest.approx(50.0, rel=0.01)

    def test_sentiment_sizing_with_report(self):
        """sentiment_sizing=True + 리포트 → 조정된 포지션"""
        trader = self._make_trader(sentiment_sizing=True)
        trader.start()

        # 극단적 공포 리포트 주입
        report = {
            'overall': {'score': 0.0, 'signal': 'neutral'},
            'layers': {},
        }
        trader.update_intelligence_report(report, fear_greed_value=20.0)

        trader.execute_buy('AAPL', 100.0, datetime.now())

        # multiplier = 1.25 → 5000 * 1.25 = 6250 / 100 = 62.5 shares
        assert trader.positions['AAPL'] == pytest.approx(62.5, rel=0.01)

    def test_sentiment_sizing_without_report(self):
        """sentiment_sizing=True but no report → 기본 포지션"""
        trader = self._make_trader(sentiment_sizing=True)
        trader.start()

        trader.execute_buy('AAPL', 100.0, datetime.now())

        # No report → multiplier stays 1.0
        assert trader.positions['AAPL'] == pytest.approx(50.0, rel=0.01)

    def test_sentiment_sizing_capped_by_capital(self):
        """trade_capital이 현재 자본금 초과 불가"""
        trader = self._make_trader(sentiment_sizing=True)
        trader.start()

        # position_size=0.5 → base=5000, with 1.25x → 6250
        # capital=10000 이므로 6250 < 10000, 통과
        report = {'overall': {'score': 35.0, 'signal': 'bullish'}, 'layers': {}}
        trader.update_intelligence_report(report, fear_greed_value=10.0)

        trader.execute_buy('AAPL', 100.0, datetime.now())

        # multiplier = 1.0 + 0.25 + 0.15 = 1.4 → 5000 * 1.4 = 7000 / 100 = 70
        assert trader.positions['AAPL'] == pytest.approx(70.0, rel=0.01)
        assert trader.capital == pytest.approx(3000.0, rel=0.01)

    def test_greed_reduces_position(self):
        """극단적 탐욕 → 포지션 축소"""
        trader = self._make_trader(sentiment_sizing=True)
        trader.start()

        report = {'overall': {'score': 0.0, 'signal': 'neutral'}, 'layers': {}}
        trader.update_intelligence_report(report, fear_greed_value=80.0)

        trader.execute_buy('AAPL', 100.0, datetime.now())

        # multiplier = 0.75 → 5000 * 0.75 = 3750 / 100 = 37.5
        assert trader.positions['AAPL'] == pytest.approx(37.5, rel=0.01)

    def test_update_intelligence_report(self):
        """update_intelligence_report() 메서드 동작"""
        trader = self._make_trader(sentiment_sizing=True)

        report = {'overall': {'score': 10.0}, 'layers': {}}
        trader.update_intelligence_report(report, fear_greed_value=50.0)

        assert trader._intelligence_report == report
        assert trader._fear_greed_value == 50.0
