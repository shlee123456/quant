"""Tests for StockRanker — 5-factor weighted ranking system."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from trading_bot.stock_ranker import StockRanker


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def ranker() -> StockRanker:
    return StockRanker()


@pytest.fixture
def sample_stocks() -> Dict[str, Any]:
    return {
        'AAPL': {
            'price': {'last': 255.0, 'change_1d': -1.9, 'change_5d': -1.7, 'change_20d': -7.2},
            'indicators': {
                'rsi': {'value': 31.8, 'signal': 'near_oversold'},
                'macd': {'histogram': -1.0, 'signal': 'bearish', 'cross_recent': False},
                'bollinger': {'pct_b': 0.13, 'signal': 'near_lower'},
                'stochastic': {'k': 9.3, 'd': 24.3},
                'adx': {'value': 16.6, 'trend': 'weak_trend'},
            },
            'regime': {'state': 'VOLATILE', 'confidence': 0.7},
            'patterns': {'double_bottom': True, 'support_levels': [246.7, 255.78]},
        },
        'MSFT': {
            'price': {'last': 401.0, 'change_1d': -0.8, 'change_5d': -1.2, 'change_20d': -3.5},
            'indicators': {
                'rsi': {'value': 45.2, 'signal': 'neutral'},
                'macd': {'histogram': 0.5, 'signal': 'bullish', 'cross_recent': True},
                'bollinger': {'pct_b': 0.45, 'signal': 'middle'},
                'stochastic': {'k': 42.0, 'd': 38.5},
                'adx': {'value': 22.0, 'trend': 'moderate_trend'},
            },
            'regime': {'state': 'SIDEWAYS', 'confidence': 0.6},
            'patterns': {'double_bottom': False, 'support_levels': [390.0]},
        },
        'TSLA': {
            'price': {'last': 220.0, 'change_1d': -3.1, 'change_5d': -5.0, 'change_20d': -15.0},
            'indicators': {
                'rsi': {'value': 25.0, 'signal': 'oversold'},
                'macd': {'histogram': -2.5, 'signal': 'bearish', 'cross_recent': False},
                'bollinger': {'pct_b': 0.05, 'signal': 'below_lower'},
                'stochastic': {'k': 5.0, 'd': 12.0},
                'adx': {'value': 35.0, 'trend': 'strong_trend'},
            },
            'regime': {'state': 'BEARISH', 'confidence': 0.9},
            'patterns': {'double_bottom': False, 'support_levels': [210.0, 215.0]},
        },
    }


@pytest.fixture
def five_stocks(sample_stocks: Dict[str, Any]) -> Dict[str, Any]:
    """sample_stocks 3개 + 추가 2개로 5종목 생성."""
    extra = {
        'NVDA': {
            'price': {'last': 120.0, 'change_1d': -2.0, 'change_5d': -3.5, 'change_20d': -10.0},
            'indicators': {
                'rsi': {'value': 38.0, 'signal': 'weak'},
                'macd': {'histogram': -0.8, 'signal': 'bearish', 'cross_recent': False},
                'bollinger': {'pct_b': 0.25, 'signal': 'lower_half'},
                'stochastic': {'k': 20.0, 'd': 28.0},
                'adx': {'value': 28.0, 'trend': 'moderate_trend'},
            },
            'regime': {'state': 'BEARISH', 'confidence': 0.75},
            'patterns': {},
        },
        'AMZN': {
            'price': {'last': 190.0, 'change_1d': 0.5, 'change_5d': 1.0, 'change_20d': 2.0},
            'indicators': {
                'rsi': {'value': 55.0, 'signal': 'neutral'},
                'macd': {'histogram': 1.2, 'signal': 'bullish', 'cross_recent': True},
                'bollinger': {'pct_b': 0.60, 'signal': 'upper_half'},
                'stochastic': {'k': 60.0, 'd': 55.0},
                'adx': {'value': 18.0, 'trend': 'weak_trend'},
            },
            'regime': {'state': 'SIDEWAYS', 'confidence': 0.5},
            'patterns': {},
        },
    }
    return {**sample_stocks, **extra}


@pytest.fixture
def sample_intelligence() -> Dict[str, Any]:
    """Intelligence Layer 4 데이터 구조."""
    return {
        'layers': {
            'enhanced_technicals': {
                'details': {
                    'per_stock': {
                        'AAPL': {'composite_score': 14.2, 'signal': 'neutral'},
                        'MSFT': {'composite_score': 2.3, 'signal': 'neutral'},
                        'TSLA': {'composite_score': -22.5, 'signal': 'bearish'},
                        'NVDA': {'composite_score': 1.5, 'signal': 'neutral'},
                        'AMZN': {'composite_score': 4.1, 'signal': 'neutral'},
                    }
                }
            }
        }
    }


@pytest.fixture
def sample_daily_changes() -> Dict[str, Any]:
    """전일 대비 변화 데이터."""
    return {
        'has_previous': True,
        'previous_date': '2026-03-12',
        'stocks': {
            'AAPL': {'price_change_pct': -1.9, 'rsi_change': -4.2},
            'MSFT': {'price_change_pct': -0.7, 'rsi_change': 2.1},
            'TSLA': {'price_change_pct': -3.1, 'rsi_change': -8.5},
            'NVDA': {'price_change_pct': -2.0, 'rsi_change': -3.0},
            'AMZN': {'price_change_pct': 0.5, 'rsi_change': 1.5},
        },
    }


# ─────────────────────────────────────────────────────────────
# 1. Basic ranking
# ─────────────────────────────────────────────────────────────

class TestBasicRanking:
    def test_basic_ranking(
        self, ranker: StockRanker, five_stocks, sample_intelligence, sample_daily_changes
    ):
        results = ranker.rank(five_stocks, sample_intelligence, sample_daily_changes)

        assert len(results) == 5
        # 각 항목에 필수 키가 존재
        for item in results:
            assert 'symbol' in item
            assert 'total_score' in item
            assert 'factor_scores' in item
            assert 'reasons' in item
            assert 'rank' in item
            assert isinstance(item['factor_scores'], dict)
            assert isinstance(item['reasons'], list)

        # rank 필드가 위치와 일치
        for i, item in enumerate(results):
            assert item['rank'] == i + 1

        # 내림차순 정렬 확인
        scores = [r['total_score'] for r in results]
        assert scores == sorted(scores, reverse=True)


# ─────────────────────────────────────────────────────────────
# 2. Deterministic
# ─────────────────────────────────────────────────────────────

class TestDeterministic:
    def test_deterministic(
        self, ranker: StockRanker, five_stocks, sample_intelligence, sample_daily_changes
    ):
        result1 = ranker.rank(five_stocks, sample_intelligence, sample_daily_changes)
        result2 = ranker.rank(five_stocks, sample_intelligence, sample_daily_changes)

        assert result1 == result2


# ─────────────────────────────────────────────────────────────
# 3. Intelligence fallback
# ─────────────────────────────────────────────────────────────

class TestIntelligenceFallback:
    def test_intelligence_fallback(
        self, ranker: StockRanker, sample_stocks, sample_daily_changes, caplog
    ):
        """intelligence_data=None이면 fallback 점수 사용."""
        results = ranker.rank(sample_stocks, None, sample_daily_changes)

        assert len(results) == 3
        for item in results:
            assert item['total_score'] > 0
            # intelligence_composite가 fallback으로 계산되어 있어야 함
            assert 'intelligence_composite' in item['factor_scores']


# ─────────────────────────────────────────────────────────────
# 4. daily_changes=None
# ─────────────────────────────────────────────────────────────

class TestDailyChangesNone:
    def test_daily_changes_none(
        self, ranker: StockRanker, sample_stocks, sample_intelligence
    ):
        results = ranker.rank(sample_stocks, sample_intelligence, None)

        assert len(results) == 3
        for item in results:
            assert item['total_score'] > 0
            # daily_delta 팩터는 None이므로 factor_scores에 없어야 함
            assert 'daily_delta' not in item['factor_scores']


# ─────────────────────────────────────────────────────────────
# 5. All data missing
# ─────────────────────────────────────────────────────────────

class TestAllDataMissing:
    def test_all_data_missing(self, ranker: StockRanker, sample_stocks):
        """intelligence=None, daily_changes=None — momentum/extremity/regime만 사용."""
        results = ranker.rank(sample_stocks, None, None)

        assert len(results) == 3
        for item in results:
            assert item['total_score'] > 0
            # 최소 momentum, extremity, regime은 있어야 함
            fs = item['factor_scores']
            assert 'momentum_multi' in fs
            assert 'technical_extremity' in fs
            assert 'regime_clarity' in fs
            # daily_delta는 없어야 함
            assert 'daily_delta' not in fs


# ─────────────────────────────────────────────────────────────
# 6. Empty stocks
# ─────────────────────────────────────────────────────────────

class TestEmptyStocks:
    def test_empty_stocks(self, ranker: StockRanker):
        results = ranker.rank({}, None, None)
        assert results == []


# ─────────────────────────────────────────────────────────────
# 7. Single stock
# ─────────────────────────────────────────────────────────────

class TestSingleStock:
    def test_single_stock(self, ranker: StockRanker, sample_stocks):
        single = {'AAPL': sample_stocks['AAPL']}
        results = ranker.rank(single, None, None)

        assert len(results) == 1
        assert results[0]['symbol'] == 'AAPL'
        assert results[0]['rank'] == 1
        assert results[0]['total_score'] > 0


# ─────────────────────────────────────────────────────────────
# 8. Duplicate penalty — single stock
# ─────────────────────────────────────────────────────────────

class TestDuplicatePenalty:
    def test_duplicate_penalty(
        self, ranker: StockRanker, sample_stocks, sample_intelligence, sample_daily_changes
    ):
        # 첫 번째 호출: 감점 없이
        results_orig = ranker.rank(sample_stocks, sample_intelligence, sample_daily_changes)
        top_symbol = results_orig[0]['symbol']
        top_score_orig = results_orig[0]['total_score']

        # 두 번째 호출: 1위 종목을 previous_top3에 포함
        results_penalized = ranker.rank(
            sample_stocks, sample_intelligence, sample_daily_changes,
            previous_top3=[top_symbol],
        )

        # 감점된 종목 찾기
        penalized_item = next(r for r in results_penalized if r['symbol'] == top_symbol)

        # 약 30% 감점 확인 (반올림 오차 허용)
        expected_penalized = round(top_score_orig * 0.70, 1)
        assert abs(penalized_item['total_score'] - expected_penalized) <= 0.2

        # 감점 이유 메시지 포함 확인
        penalty_reasons = [r for r in penalized_item['reasons'] if '중복 감점' in r]
        assert len(penalty_reasons) == 1

    def test_duplicate_penalty_all_previous(
        self, ranker: StockRanker, sample_stocks, sample_intelligence, sample_daily_changes
    ):
        """이전 TOP 3 전부 감점하면 순위가 바뀔 수 있음."""
        results_orig = ranker.rank(sample_stocks, sample_intelligence, sample_daily_changes)
        top3_symbols = [r['symbol'] for r in results_orig[:3]]
        original_scores = {r['symbol']: r['total_score'] for r in results_orig}

        results_penalized = ranker.rank(
            sample_stocks, sample_intelligence, sample_daily_changes,
            previous_top3=top3_symbols,
        )

        # 모든 이전 TOP 3 종목이 감점되었는지 확인
        for item in results_penalized:
            if item['symbol'] in top3_symbols:
                orig_score = original_scores[item['symbol']]
                expected = round(orig_score * 0.70, 1)
                assert abs(item['total_score'] - expected) <= 0.2
                assert any('중복 감점' in r for r in item['reasons'])


# ─────────────────────────────────────────────────────────────
# 10. Extreme RSI scores higher
# ─────────────────────────────────────────────────────────────

class TestTechnicalExtremity:
    def test_extreme_rsi_scores_higher(self, ranker: StockRanker):
        """극단적 RSI 종목이 중립 RSI 종목보다 extremity 점수가 높아야 함."""
        def _make_stock(rsi: float) -> Dict[str, Any]:
            return {
                'price': {'last': 100.0, 'change_1d': 0, 'change_5d': 0, 'change_20d': 0},
                'indicators': {
                    'rsi': {'value': rsi, 'signal': 'test'},
                    'macd': {'histogram': 0, 'signal': 'neutral', 'cross_recent': False},
                    'bollinger': {'pct_b': 0.5, 'signal': 'middle'},
                    'stochastic': {'k': 50.0, 'd': 50.0},
                    'adx': {'value': 20.0, 'trend': 'moderate'},
                },
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.5},
            }

        stocks = {
            'A_OVERSOLD': _make_stock(15),   # 극단적 과매도
            'B_NEUTRAL': _make_stock(50),     # 중립
            'C_OVERBOUGHT': _make_stock(85),  # 극단적 과매수
        }

        results = ranker.rank(stocks, None, None)
        scores_by_sym = {r['symbol']: r['factor_scores'] for r in results}

        # A, C의 extremity가 B보다 높아야 함
        assert scores_by_sym['A_OVERSOLD']['technical_extremity'] > scores_by_sym['B_NEUTRAL']['technical_extremity']
        assert scores_by_sym['C_OVERBOUGHT']['technical_extremity'] > scores_by_sym['B_NEUTRAL']['technical_extremity']


# ─────────────────────────────────────────────────────────────
# 11. High volatility scores higher
# ─────────────────────────────────────────────────────────────

class TestMomentum:
    def test_high_volatility_scores_higher(self, ranker: StockRanker):
        """큰 1일 변동률 종목이 momentum_multi에서 더 높은 점수."""
        def _make_stock(change_1d: float) -> Dict[str, Any]:
            return {
                'price': {'last': 100.0, 'change_1d': change_1d, 'change_5d': 0, 'change_20d': 0},
                'indicators': {
                    'rsi': {'value': 50, 'signal': 'neutral'},
                    'macd': {'histogram': 0, 'signal': 'neutral', 'cross_recent': False},
                    'bollinger': {'pct_b': 0.5, 'signal': 'middle'},
                    'stochastic': {'k': 50, 'd': 50},
                    'adx': {'value': 20, 'trend': 'moderate'},
                },
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.5},
            }

        stocks = {
            'HIGH_VOL': _make_stock(-5.0),   # 큰 변동
            'LOW_VOL': _make_stock(-0.5),     # 작은 변동
        }

        results = ranker.rank(stocks, None, None)
        scores_by_sym = {r['symbol']: r['factor_scores'] for r in results}

        assert scores_by_sym['HIGH_VOL']['momentum_multi'] > scores_by_sym['LOW_VOL']['momentum_multi']


# ─────────────────────────────────────────────────────────────
# 12. Regime clarity scoring
# ─────────────────────────────────────────────────────────────

class TestRegimeClarity:
    def test_regime_clarity_scoring(self, ranker: StockRanker):
        """명확한 레짐(BULLISH, 높은 confidence, 높은 ADX)이 더 높은 점수."""
        stocks = {
            'CLEAR': {
                'price': {'last': 100.0, 'change_1d': 0, 'change_5d': 0, 'change_20d': 0},
                'indicators': {
                    'rsi': {'value': 50, 'signal': 'neutral'},
                    'macd': {'histogram': 0, 'signal': 'neutral', 'cross_recent': False},
                    'bollinger': {'pct_b': 0.5, 'signal': 'middle'},
                    'stochastic': {'k': 50, 'd': 50},
                    'adx': {'value': 35.0, 'trend': 'strong_trend'},
                },
                'regime': {'state': 'BULLISH', 'confidence': 0.9},
            },
            'UNCLEAR': {
                'price': {'last': 100.0, 'change_1d': 0, 'change_5d': 0, 'change_20d': 0},
                'indicators': {
                    'rsi': {'value': 50, 'signal': 'neutral'},
                    'macd': {'histogram': 0, 'signal': 'neutral', 'cross_recent': False},
                    'bollinger': {'pct_b': 0.5, 'signal': 'middle'},
                    'stochastic': {'k': 50, 'd': 50},
                    'adx': {'value': 15.0, 'trend': 'no_trend'},
                },
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.5},
            },
        }

        results = ranker.rank(stocks, None, None)
        scores_by_sym = {r['symbol']: r['factor_scores'] for r in results}

        # CLEAR가 UNCLEAR보다 regime_clarity에서 크게 높아야 함
        clear_score = scores_by_sym['CLEAR']['regime_clarity']
        unclear_score = scores_by_sym['UNCLEAR']['regime_clarity']
        assert clear_score > unclear_score
        # "크게" 차이 나는지 확인 (최소 2배)
        assert clear_score > unclear_score * 2


# ─────────────────────────────────────────────────────────────
# 13. Real data test
# ─────────────────────────────────────────────────────────────

class TestWithRealData:
    DATA_PATH = Path(__file__).resolve().parent.parent / 'data' / 'market_analysis' / '2026-03-13.json'

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / 'data' / 'market_analysis' / '2026-03-13.json').exists(),
        reason='실제 데이터 파일이 없음',
    )
    def test_with_real_data(self, ranker: StockRanker):
        with open(self.DATA_PATH, 'r') as f:
            data = json.load(f)

        stocks = data['stocks']
        intelligence = data.get('intelligence')

        results = ranker.rank(stocks, intelligence, daily_changes=None)

        # 16개 종목이 모두 랭킹되어야 함
        assert len(results) == 16

        for item in results:
            assert item['total_score'] > 0
            assert item['rank'] >= 1

        # rank는 1부터 연속
        ranks = [r['rank'] for r in results]
        assert ranks == list(range(1, 17))

        # 시각 확인용 출력
        print("\n=== Real Data Top 5 ===")
        for item in results[:5]:
            print(
                f"  #{item['rank']} {item['symbol']:>5s}  "
                f"score={item['total_score']:.1f}  "
                f"reasons={item['reasons']}"
            )


# ─────────────────────────────────────────────────────────────
# 14. Weight redistribution
# ─────────────────────────────────────────────────────────────

class TestWeightRedistribution:
    def test_weights_sum_to_one_without_intelligence(self, ranker: StockRanker):
        """intelligence=None일 때도 유효 가중치 합이 1.0."""
        # intelligence_composite는 fallback이 있으므로 항상 점수가 있음.
        # daily_delta만 None이 되는 케이스 확인.
        factor_results = {
            'intelligence_composite': 50.0,
            'momentum_multi': 30.0,
            'technical_extremity': 40.0,
            'regime_clarity': 20.0,
            'daily_delta': None,  # 데이터 없음
        }
        effective = ranker._get_effective_weights(factor_results)
        assert abs(sum(effective.values()) - 1.0) < 1e-9
        assert 'daily_delta' not in effective

    def test_weights_sum_to_one_without_daily(self, ranker: StockRanker):
        """daily_changes=None일 때 remaining weights 합이 1.0."""
        factor_results = {
            'intelligence_composite': 50.0,
            'momentum_multi': 30.0,
            'technical_extremity': 40.0,
            'regime_clarity': 20.0,
            'daily_delta': None,
        }
        effective = ranker._get_effective_weights(factor_results)
        assert abs(sum(effective.values()) - 1.0) < 1e-9

    def test_weights_sum_to_one_all_available(self, ranker: StockRanker):
        """모든 팩터 사용 가능할 때도 합이 1.0."""
        factor_results = {
            'intelligence_composite': 50.0,
            'momentum_multi': 30.0,
            'technical_extremity': 40.0,
            'regime_clarity': 20.0,
            'daily_delta': 60.0,
        }
        effective = ranker._get_effective_weights(factor_results)
        assert abs(sum(effective.values()) - 1.0) < 1e-9
        assert len(effective) == 5

    def test_weights_redistribution_proportional(self, ranker: StockRanker):
        """재분배는 기존 비율을 유지해야 함."""
        factor_results = {
            'intelligence_composite': 50.0,
            'momentum_multi': 30.0,
            'technical_extremity': 40.0,
            'regime_clarity': 20.0,
            'daily_delta': None,
        }
        effective = ranker._get_effective_weights(factor_results)

        # intelligence_composite / momentum_multi 비율이 원래 0.40/0.20 = 2.0
        ratio = effective['intelligence_composite'] / effective['momentum_multi']
        assert abs(ratio - 2.0) < 1e-9


# ─────────────────────────────────────────────────────────────
# Edge cases / factor-level unit tests
# ─────────────────────────────────────────────────────────────

class TestFactorScoring:
    """개별 팩터 점수 계산 단위 테스트."""

    def test_score_momentum_zero_changes(self):
        price_data = {'change_1d': 0, 'change_5d': 0, 'change_20d': 0}
        score = StockRanker._score_momentum(price_data)
        assert score == 0.0

    def test_score_momentum_cap_at_100(self):
        """극단적 변동에도 100 이하."""
        price_data = {'change_1d': 50, 'change_5d': 30, 'change_20d': 20}
        score = StockRanker._score_momentum(price_data)
        assert score <= 100.0

    def test_score_extremity_neutral(self):
        """모든 지표가 중심에 있으면 0점."""
        indicators = {
            'rsi': {'value': 50},
            'stochastic': {'k': 50},
            'bollinger': {'pct_b': 0.5},
        }
        score = StockRanker._score_extremity(indicators)
        assert score == 0.0

    def test_score_regime_sideways(self):
        """SIDEWAYS + 낮은 ADX = 낮은 점수."""
        score = StockRanker._score_regime(
            {'state': 'SIDEWAYS', 'confidence': 0.5},
            {'value': 10},
        )
        # state_score=0, conf_score=15, adx_score=5
        expected = 0 + 15 + 5
        assert score == expected

    def test_score_daily_delta_no_data(self):
        """daily_changes가 None이면 None 반환."""
        assert StockRanker._score_daily_delta('AAPL', None) is None

    def test_score_daily_delta_no_has_previous(self):
        """has_previous=False이면 None 반환."""
        assert StockRanker._score_daily_delta('AAPL', {'has_previous': False}) is None

    def test_score_daily_delta_missing_symbol(self):
        """해당 심볼이 없으면 None."""
        daily = {'has_previous': True, 'stocks': {'MSFT': {'price_change_pct': 1.0}}}
        assert StockRanker._score_daily_delta('AAPL', daily) is None

    def test_score_daily_delta_valid(self):
        """정상 데이터 시 0~100 범위 점수."""
        daily = {
            'has_previous': True,
            'stocks': {'AAPL': {'price_change_pct': 2.0, 'rsi_change': 5.0}},
        }
        score = StockRanker._score_daily_delta('AAPL', daily)
        assert score is not None
        assert 0 <= score <= 100

    def test_score_intelligence_with_composite(self):
        """per_stock composite_score가 있으면 절대값 사용."""
        ranker = StockRanker()
        intel = {
            'layers': {
                'enhanced_technicals': {
                    'details': {
                        'per_stock': {
                            'AAPL': {'composite_score': -25.0},
                        }
                    }
                }
            }
        }
        indicators = {'rsi': {'value': 50}, 'macd': {'histogram': 0}, 'bollinger': {'pct_b': 0.5}}
        score = ranker._score_intelligence('AAPL', intel, indicators)
        assert score == 25.0  # abs(-25.0)

    def test_score_intelligence_fallback(self):
        """composite_score가 없으면 fallback 계산."""
        ranker = StockRanker()
        indicators = {
            'rsi': {'value': 30},       # dist=40
            'macd': {'histogram': 2.0},  # mag=40
            'bollinger': {'pct_b': 0.1}, # dist=80
        }
        score = ranker._score_intelligence('AAPL', None, indicators)
        # (40 + 40 + 80) / 3 = 53.33...
        assert abs(score - 53.33) < 0.1


# ─────────────────────────────────────────────────────────────
# Reason generation
# ─────────────────────────────────────────────────────────────

class TestReasonGeneration:
    def test_rsi_oversold_reason(self, ranker: StockRanker, sample_stocks):
        """RSI < 32인 종목에 과매도 이유 생성."""
        results = ranker.rank({'AAPL': sample_stocks['AAPL']}, None, None)
        reasons = results[0]['reasons']
        assert any('과매도' in r for r in reasons)

    def test_large_1d_change_reason(self, ranker: StockRanker, sample_stocks):
        """1일 |변동률| >= 3인 종목에 급변 이유 생성."""
        results = ranker.rank({'TSLA': sample_stocks['TSLA']}, None, None)
        reasons = results[0]['reasons']
        assert any('급변' in r for r in reasons)

    def test_regime_reason(self, ranker: StockRanker, sample_stocks):
        """SIDEWAYS가 아닌 레짐에 이유 생성."""
        results = ranker.rank({'TSLA': sample_stocks['TSLA']}, None, None)
        reasons = results[0]['reasons']
        assert any('레짐' in r for r in reasons)

    def test_macd_cross_reason(self, ranker: StockRanker, sample_stocks):
        """MACD cross_recent=True인 종목에 교차 이유."""
        results = ranker.rank({'MSFT': sample_stocks['MSFT']}, None, None)
        reasons = results[0]['reasons']
        assert any('MACD 교차' in r for r in reasons)


# ─────────────────────────────────────────────────────────────
# Custom weights
# ─────────────────────────────────────────────────────────────

class TestCustomWeights:
    def test_custom_weights(self, sample_stocks):
        """사용자 정의 가중치 적용."""
        custom = {
            'intelligence_composite': 0.10,
            'momentum_multi': 0.50,
            'technical_extremity': 0.20,
            'regime_clarity': 0.10,
            'daily_delta': 0.10,
        }
        ranker = StockRanker(weights=custom)
        results = ranker.rank(sample_stocks, None, None)

        assert len(results) == 3
        # momentum 가중치가 높으므로 TSLA(큰 변동)가 1위일 가능성 높음
        # 최소한 유효한 결과가 나와야 함
        for item in results:
            assert item['total_score'] > 0
