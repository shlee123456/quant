"""
Phase 2 아키텍처 개선 테스트:
- 동적 가중치 (Regime-Dependent Dynamic Weights)
- Meta-Confidence (Layer Agreement)
- 데이터 신선도 체크 (Freshness Multiplier)
"""

import math

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence import (
    MarketIntelligence,
    LAYER_WEIGHTS,
)
from trading_bot.market_intelligence.base_layer import LayerResult
from trading_bot.market_intelligence.data_fetcher import MarketDataCache

from .conftest import MockCache, make_ohlcv


def _make_layer_result(
    name: str,
    score: float = 0.0,
    signal: str = "neutral",
    confidence: float = 0.5,
    metrics: dict = None,
    details: dict = None,
) -> LayerResult:
    """테스트용 LayerResult 생성 헬퍼."""
    return LayerResult(
        layer_name=name,
        score=score,
        signal=signal,
        confidence=confidence,
        metrics=metrics or {},
        interpretation="test",
        details=details or {},
    )


def _make_standard_layer_results(**overrides) -> dict:
    """5개 레이어 기본 결과 세트 생성.

    overrides로 특정 레이어의 LayerResult을 덮어쓸 수 있음.
    """
    defaults = {
        'macro_regime': _make_layer_result('macro_regime', score=10),
        'market_structure': _make_layer_result('market_structure', score=5),
        'sector_rotation': _make_layer_result('sector_rotation', score=0),
        'enhanced_technicals': _make_layer_result('enhanced_technicals', score=15),
        'sentiment': _make_layer_result('sentiment', score=8),
    }
    defaults.update(overrides)
    return defaults


# ─────────────────────────────────────────────
# Improvement 2-1: Dynamic Weights
# ─────────────────────────────────────────────

class TestDynamicWeights:
    """동적 가중치 테스트."""

    def _make_mi(self) -> MarketIntelligence:
        """MarketIntelligence 인스턴스 생성 (yfinance fetch 불필요)."""
        mi = MarketIntelligence.__new__(MarketIntelligence)
        mi.weights = LAYER_WEIGHTS.copy()
        mi.cache = MockCache({})
        mi.layers = {}
        return mi

    def test_contraction_boosts_macro(self):
        """수축기에 macro 가중치 증가"""
        mi = self._make_mi()
        layer_results = _make_standard_layer_results(
            macro_regime=_make_layer_result(
                'macro_regime', score=-20,
                details={'cycle_phase': 'contraction'},
            ),
        )
        weights = mi._compute_dynamic_weights(layer_results)

        assert weights['macro_regime'] == 0.30
        assert weights['sentiment'] == 0.25
        assert weights['enhanced_technicals'] == 0.15
        assert weights['market_structure'] == 0.15
        assert weights['sector_rotation'] == 0.15

    def test_expansion_boosts_technicals(self):
        """확장기에 technicals 가중치 증가"""
        mi = self._make_mi()
        layer_results = _make_standard_layer_results(
            macro_regime=_make_layer_result(
                'macro_regime', score=30,
                details={'cycle_phase': 'expansion'},
            ),
            market_structure=_make_layer_result(
                'market_structure', score=25,
                metrics={'vix_level': 25},
            ),
        )
        weights = mi._compute_dynamic_weights(layer_results)

        assert weights['enhanced_technicals'] == 0.30
        assert weights['sector_rotation'] == 0.20
        assert weights['macro_regime'] == 0.15
        assert weights['market_structure'] == 0.20
        assert weights['sentiment'] == 0.15

    def test_default_weights_when_unknown(self):
        """레짐 불명일 때 기본 가중치"""
        mi = self._make_mi()
        layer_results = _make_standard_layer_results()
        weights = mi._compute_dynamic_weights(layer_results)

        assert weights == LAYER_WEIGHTS

    def test_weights_sum_to_one(self):
        """모든 경우에서 가중치 합 = 1.0"""
        mi = self._make_mi()

        # Case 1: 기본
        w1 = mi._compute_dynamic_weights(_make_standard_layer_results())
        assert abs(sum(w1.values()) - 1.0) < 1e-9

        # Case 2: contraction
        w2 = mi._compute_dynamic_weights(_make_standard_layer_results(
            macro_regime=_make_layer_result(
                'macro_regime', score=-10,
                details={'cycle_phase': 'contraction'},
            ),
        ))
        assert abs(sum(w2.values()) - 1.0) < 1e-9

        # Case 3: expansion + high vix_score
        w3 = mi._compute_dynamic_weights(_make_standard_layer_results(
            macro_regime=_make_layer_result(
                'macro_regime', score=20,
                details={'cycle_phase': 'expansion'},
            ),
            market_structure=_make_layer_result(
                'market_structure', score=30,
                metrics={'vix_level': 30},
            ),
        ))
        assert abs(sum(w3.values()) - 1.0) < 1e-9

    def test_high_vix_triggers_contraction_weights(self):
        """VIX 점수가 -30 미만이면 cycle과 무관하게 위기 가중치 적용"""
        mi = self._make_mi()
        layer_results = _make_standard_layer_results(
            macro_regime=_make_layer_result(
                'macro_regime', score=10,
                details={'cycle_phase': 'expansion'},
            ),
            market_structure=_make_layer_result(
                'market_structure', score=-40,
                metrics={'vix_level': -35},
            ),
        )
        weights = mi._compute_dynamic_weights(layer_results)

        # vix_score < -30 이므로 contraction 가중치 적용
        assert weights['macro_regime'] == 0.30
        assert weights['sentiment'] == 0.25

    def test_nan_score_uses_default_weights(self):
        """NaN 스코어 레이어는 무시하고 기본 가중치"""
        mi = self._make_mi()
        layer_results = _make_standard_layer_results(
            macro_regime=_make_layer_result(
                'macro_regime', score=float('nan'),
                details={'cycle_phase': 'contraction'},
            ),
        )
        weights = mi._compute_dynamic_weights(layer_results)

        # NaN이므로 cycle_phase 무시 → 기본 가중치
        assert weights == LAYER_WEIGHTS


# ─────────────────────────────────────────────
# Improvement 2-2: Meta-Confidence
# ─────────────────────────────────────────────

class TestMetaConfidence:
    """Meta-Confidence (레이어 합의도) 테스트."""

    def _make_mi(self) -> MarketIntelligence:
        mi = MarketIntelligence.__new__(MarketIntelligence)
        mi.weights = LAYER_WEIGHTS.copy()
        mi.cache = MockCache({})
        mi.layers = {}
        return mi

    def test_high_agreement(self):
        """모든 레이어 점수 비슷 -> 높은 confidence"""
        mi = self._make_mi()
        layer_results = {
            'a': _make_layer_result('a', score=20, confidence=0.8),
            'b': _make_layer_result('b', score=22, confidence=0.85),
            'c': _make_layer_result('c', score=18, confidence=0.9),
            'd': _make_layer_result('d', score=21, confidence=0.75),
            'e': _make_layer_result('e', score=19, confidence=0.8),
        }
        mc = mi._compute_meta_confidence(layer_results)

        # 점수가 거의 동일 → std 작음 → agreement 높음
        assert mc >= 0.7

    def test_low_agreement(self):
        """레이어 점수 큰 차이 -> 낮은 confidence"""
        mi = self._make_mi()
        layer_results = {
            'a': _make_layer_result('a', score=80, confidence=0.9),
            'b': _make_layer_result('b', score=-80, confidence=0.9),
            'c': _make_layer_result('c', score=50, confidence=0.9),
            'd': _make_layer_result('d', score=-50, confidence=0.9),
            'e': _make_layer_result('e', score=0, confidence=0.9),
        }
        mc = mi._compute_meta_confidence(layer_results)

        # 점수 편차 큼 → agreement 낮음
        assert mc < 0.5

    def test_with_nan_layers(self):
        """NaN 레이어는 제외하고 계산"""
        mi = self._make_mi()
        layer_results = {
            'a': _make_layer_result('a', score=20, confidence=0.8),
            'b': _make_layer_result('b', score=22, confidence=0.85),
            'c': _make_layer_result('c', score=float('nan'), confidence=0.0),
        }
        mc = mi._compute_meta_confidence(layer_results)

        # NaN 제외 → 2개 레이어만 사용 → 점수 비슷
        assert mc >= 0.5

    def test_range_0_to_1(self):
        """결과값이 0~1 범위"""
        mi = self._make_mi()

        # 극단 케이스들
        test_cases = [
            # 모든 점수 동일
            {'a': _make_layer_result('a', score=50, confidence=1.0),
             'b': _make_layer_result('b', score=50, confidence=1.0)},
            # 최대 분산
            {'a': _make_layer_result('a', score=100, confidence=1.0),
             'b': _make_layer_result('b', score=-100, confidence=1.0)},
            # 낮은 confidence
            {'a': _make_layer_result('a', score=10, confidence=0.1),
             'b': _make_layer_result('b', score=10, confidence=0.1)},
        ]

        for layer_results in test_cases:
            mc = mi._compute_meta_confidence(layer_results)
            assert 0.0 <= mc <= 1.0, f"meta_confidence {mc} out of range for {layer_results}"

    def test_single_layer_returns_default(self):
        """레이어가 1개 이하이면 0.5 반환"""
        mi = self._make_mi()
        layer_results = {
            'a': _make_layer_result('a', score=50, confidence=0.9),
        }
        mc = mi._compute_meta_confidence(layer_results)
        assert mc == 0.5

    def test_all_nan_returns_default(self):
        """모든 레이어가 NaN이면 0.5 반환"""
        mi = self._make_mi()
        layer_results = {
            'a': _make_layer_result('a', score=float('nan'), confidence=0.0),
            'b': _make_layer_result('b', score=float('nan'), confidence=0.0),
        }
        mc = mi._compute_meta_confidence(layer_results)
        assert mc == 0.5


# ─────────────────────────────────────────────
# Improvement 2-3: Freshness Multiplier
# ─────────────────────────────────────────────

class TestFreshnessMultiplier:
    """데이터 신선도 멀티플라이어 테스트."""

    def _make_cache_with_data(self, days_ago: int) -> MarketDataCache:
        """특정 일수 전 데이터를 가진 캐시 생성."""
        cache = MarketDataCache.__new__(MarketDataCache)
        cache.period = '6mo'
        cache.interval = '1d'
        cache._fetched = True

        # 데이터 생성 (마지막 날짜가 days_ago일 전)
        end_date = pd.Timestamp.now(tz='UTC').normalize() - pd.Timedelta(days=days_ago)
        dates = pd.date_range(end=end_date, periods=100, freq='B', tz='UTC')
        df = pd.DataFrame({
            'Open': np.random.uniform(90, 110, len(dates)),
            'High': np.random.uniform(100, 120, len(dates)),
            'Low': np.random.uniform(80, 100, len(dates)),
            'Close': np.random.uniform(90, 110, len(dates)),
            'Volume': np.random.randint(1000, 10000, len(dates)),
        }, index=dates)
        cache._data = {'SPY': df}
        return cache

    def test_fresh_data(self):
        """당일 데이터 -> 1.0"""
        cache = self._make_cache_with_data(days_ago=0)
        result = cache.freshness_multiplier('SPY')
        assert result == 1.0

    def test_stale_data_3_days(self):
        """3일 경과 -> 0.7 (normalize로 인해 실제 days_stale가 다를 수 있음)"""
        cache = self._make_cache_with_data(days_ago=3)
        result = cache.freshness_multiplier('SPY')
        # normalize() 사용으로 인해 3~4일로 계산될 수 있음
        assert 0.6 <= result <= 0.7

    def test_very_stale_data(self):
        """10일 경과 -> 0.3 (최소값)"""
        cache = self._make_cache_with_data(days_ago=10)
        result = cache.freshness_multiplier('SPY')
        assert result == 0.3

    def test_extremely_stale_data(self):
        """20일 경과 -> 여전히 0.3 (최소값)"""
        cache = self._make_cache_with_data(days_ago=20)
        result = cache.freshness_multiplier('SPY')
        assert result == 0.3

    def test_no_data(self):
        """데이터 없음 -> 0.0"""
        cache = MarketDataCache.__new__(MarketDataCache)
        cache._data = {}
        result = cache.freshness_multiplier('SPY')
        assert result == 0.0

    def test_empty_dataframe(self):
        """빈 DataFrame -> 0.0"""
        cache = MarketDataCache.__new__(MarketDataCache)
        cache._data = {'SPY': pd.DataFrame()}
        result = cache.freshness_multiplier('SPY')
        assert result == 0.0

    def test_timezone_naive_data(self):
        """타임존 없는 데이터도 정상 처리"""
        cache = MarketDataCache.__new__(MarketDataCache)
        cache.period = '6mo'
        cache.interval = '1d'
        cache._fetched = True

        # 타임존 없는 인덱스
        end_date = pd.Timestamp.now().normalize()
        dates = pd.date_range(end=end_date, periods=50, freq='B')
        df = pd.DataFrame({
            'Close': np.random.uniform(90, 110, len(dates)),
        }, index=dates)
        cache._data = {'AAPL': df}

        result = cache.freshness_multiplier('AAPL')
        assert 0.3 <= result <= 1.0


# ─────────────────────────────────────────────
# Integration: Meta-confidence in position sizing
# ─────────────────────────────────────────────

class TestPositionSizeWithMetaConfidence:
    """meta_confidence가 포지션 사이징에 미치는 영향 테스트."""

    def test_position_size_with_low_meta_confidence(self):
        """meta_confidence < 0.4 -> 포지션 축소"""
        report = {
            'overall': {
                'score': 0.0,
                'signal': 'neutral',
                'meta_confidence': 0.3,
            },
        }
        rec = MarketIntelligence.get_position_size_recommendation(report)

        # multiplier = 1.0 * 0.7 = 0.7, clamped to [0.5, 1.5]
        assert rec['multiplier'] == 0.7
        assert any('불일치' in adj for adj in rec['adjustments'])

    def test_position_size_with_high_meta_confidence(self):
        """meta_confidence >= 0.4 -> 조정 없음"""
        report = {
            'overall': {
                'score': 0.0,
                'signal': 'neutral',
                'meta_confidence': 0.8,
            },
        }
        rec = MarketIntelligence.get_position_size_recommendation(report)

        # 다른 조정 없음 → 기본 1.0
        assert rec['multiplier'] == 1.0

    def test_position_size_low_meta_with_bullish(self):
        """meta_confidence 낮으면서 강세 → 강세 보너스 + 불일치 감소"""
        report = {
            'overall': {
                'score': 40.0,
                'signal': 'bullish',
                'meta_confidence': 0.3,
            },
        }
        rec = MarketIntelligence.get_position_size_recommendation(report)

        # (1.0 + 0.15) * 0.7 = 0.805, round(0.805, 2) = 0.8 (banker's rounding)
        assert abs(rec['multiplier'] - 0.805) < 0.02

    def test_position_size_no_meta_confidence_key(self):
        """meta_confidence 키 없으면 기본값 1.0 사용 (감소 없음)"""
        report = {
            'overall': {
                'score': 0.0,
                'signal': 'neutral',
            },
        }
        rec = MarketIntelligence.get_position_size_recommendation(report)

        assert rec['multiplier'] == 1.0
        assert not any('불일치' in adj for adj in rec['adjustments'])
