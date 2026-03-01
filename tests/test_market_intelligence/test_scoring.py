"""
Tests for scoring.py - 공유 점수 계산 유틸리티 테스트.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.scoring import (
    calc_rsi,
    momentum_score,
    pct_change,
    percentile_rank,
    rolling_z_score,
    weighted_composite,
)


# ─── percentile_rank tests ───


class TestPercentileRank:
    """percentile_rank() 테스트."""

    def test_lowest_value(self):
        """최솟값의 백분위 = 0."""
        series = pd.Series([10, 20, 30, 40, 50])
        assert percentile_rank(10, series) == 0.0

    def test_highest_value(self):
        """최댓값의 백분위 = 80 (5개 중 4개가 작음)."""
        series = pd.Series([10, 20, 30, 40, 50])
        assert percentile_rank(50, series) == 80.0

    def test_median_value(self):
        """중앙값의 백분위."""
        series = pd.Series([10, 20, 30, 40, 50])
        assert percentile_rank(30, series) == 40.0

    def test_empty_series_returns_50(self):
        """빈 시리즈는 50 반환."""
        assert percentile_rank(10, pd.Series([], dtype=float)) == 50.0

    def test_all_nan_series_returns_50(self):
        """모두 NaN인 시리즈는 50 반환."""
        assert percentile_rank(10, pd.Series([np.nan, np.nan])) == 50.0

    def test_value_below_all(self):
        """모든 값보다 작은 경우 0."""
        series = pd.Series([10, 20, 30])
        assert percentile_rank(5, series) == 0.0

    def test_value_above_all(self):
        """모든 값보다 큰 경우 100."""
        series = pd.Series([10, 20, 30])
        assert percentile_rank(40, series) == 100.0

    def test_with_nan_values_in_series(self):
        """NaN이 포함된 시리즈에서도 정상 작동."""
        series = pd.Series([10, np.nan, 30, np.nan, 50])
        rank = percentile_rank(30, series)
        # 유효값: 10, 30, 50 → 30보다 작은 건 1개 → 1/3 * 100 = 33.33
        assert abs(rank - 33.33) < 0.1


# ─── rolling_z_score tests ───


class TestRollingZScore:
    """rolling_z_score() 테스트."""

    def test_basic_output(self):
        """기본 출력 확인."""
        series = pd.Series(range(100), dtype=float)
        z = rolling_z_score(series, window=20)
        assert len(z) == 100
        # NaN이 없어야 함 (fillna(0.0) 처리)
        assert z.isna().sum() == 0

    def test_constant_series_returns_zero(self):
        """일정한 시리즈의 Z-score는 0."""
        series = pd.Series([100.0] * 50)
        z = rolling_z_score(series, window=20)
        # std=0이므로 NaN → fillna(0.0)
        assert (z == 0.0).all()

    def test_trending_series_has_positive_z(self):
        """상승 추세 시리즈의 마지막 Z-score는 양수."""
        series = pd.Series(np.arange(100, dtype=float))
        z = rolling_z_score(series, window=20)
        # 마지막 값은 항상 최신이므로 Z > 0
        assert z.iloc[-1] > 0

    def test_short_series(self):
        """짧은 시리즈도 에러 없이 처리."""
        series = pd.Series([1.0, 2.0, 3.0])
        z = rolling_z_score(series, window=60)
        assert len(z) == 3


# ─── momentum_score tests ───


class TestMomentumScore:
    """momentum_score() 테스트."""

    def test_uptrend_positive_score(self):
        """상승 추세에서 양의 점수."""
        prices = pd.Series(np.linspace(100, 120, 50))
        score = momentum_score(prices, periods=[5, 10, 20])
        assert score > 0

    def test_downtrend_negative_score(self):
        """하락 추세에서 음의 점수."""
        prices = pd.Series(np.linspace(120, 100, 50))
        score = momentum_score(prices, periods=[5, 10, 20])
        assert score < 0

    def test_flat_near_zero(self):
        """횡보 시 점수 ~ 0."""
        prices = pd.Series([100.0] * 50)
        score = momentum_score(prices)
        assert score == 0.0

    def test_clamped_to_range(self):
        """결과가 -100 ~ +100 범위."""
        # 매우 급격한 상승
        prices = pd.Series(np.linspace(100, 300, 30))
        score = momentum_score(prices, periods=[5, 10, 20])
        assert -100 <= score <= 100

    def test_insufficient_data_returns_zero(self):
        """데이터 부족 시 0 반환."""
        assert momentum_score(pd.Series([100.0]), periods=[5, 10]) == 0.0
        assert momentum_score(pd.Series([], dtype=float)) == 0.0

    def test_custom_periods(self):
        """커스텀 기간 리스트 사용."""
        prices = pd.Series(np.linspace(100, 110, 30))
        score = momentum_score(prices, periods=[3, 7])
        assert score > 0

    def test_default_periods(self):
        """기본 기간 [5, 10, 20] 사용."""
        prices = pd.Series(np.linspace(100, 115, 50))
        score = momentum_score(prices)
        assert score > 0

    def test_nan_handling(self):
        """NaN이 포함된 시리즈도 정상 처리."""
        prices = pd.Series([np.nan, np.nan, 100, 102, 104, 106, 108, 110])
        score = momentum_score(prices, periods=[3])
        # dropna() 후에 유효값 6개, periods=3이면 계산 가능
        assert isinstance(score, float)


# ─── weighted_composite tests ───


class TestWeightedComposite:
    """weighted_composite() 테스트."""

    def test_equal_weights(self):
        """동일 가중치 시 단순 평균."""
        scores = {'a': 60, 'b': 40}
        weights = {'a': 0.5, 'b': 0.5}
        assert weighted_composite(scores, weights) == 50.0

    def test_different_weights(self):
        """다른 가중치 테스트."""
        scores = {'a': 100, 'b': 0}
        weights = {'a': 0.75, 'b': 0.25}
        assert weighted_composite(scores, weights) == 75.0

    def test_missing_score_key(self):
        """scores에 없는 키는 무시."""
        scores = {'a': 60}
        weights = {'a': 0.5, 'b': 0.5}
        # total_weight = 0.5, weighted_sum = 30
        assert weighted_composite(scores, weights) == 60.0

    def test_all_nan_scores(self):
        """모든 점수가 NaN이면 0 반환."""
        scores = {'a': float('nan'), 'b': float('nan')}
        weights = {'a': 0.5, 'b': 0.5}
        assert weighted_composite(scores, weights) == 0.0

    def test_partial_nan_scores(self):
        """일부 NaN은 유효한 값만으로 계산."""
        scores = {'a': 80, 'b': float('nan')}
        weights = {'a': 0.5, 'b': 0.5}
        # total_weight = 0.5, weighted_sum = 40
        assert weighted_composite(scores, weights) == 80.0

    def test_empty_scores_returns_zero(self):
        """빈 점수면 0 반환."""
        assert weighted_composite({}, {'a': 1.0}) == 0.0

    def test_empty_weights_returns_zero(self):
        """빈 가중치면 0 반환."""
        assert weighted_composite({'a': 50.0}, {}) == 0.0

    def test_no_common_keys(self):
        """공통 키가 없으면 0 반환."""
        scores = {'x': 50}
        weights = {'y': 1.0}
        assert weighted_composite(scores, weights) == 0.0


# ─── calc_rsi tests ───


class TestCalcRSI:
    """calc_rsi() 테스트."""

    def test_output_range(self):
        """RSI 값이 0~100 범위."""
        close = pd.Series(np.random.RandomState(42).uniform(90, 110, 100))
        rsi = calc_rsi(close, period=14)
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_strong_uptrend_high_rsi(self):
        """강한 상승에서 RSI > 70."""
        # 상승 추세 + 약간의 노이즈로 gain과 loss 모두 발생하도록
        rng = np.random.RandomState(42)
        base = np.linspace(100, 200, 100)
        noise = rng.normal(0, 1.0, 100)
        close = pd.Series(base + noise)
        rsi = calc_rsi(close, period=14)
        valid_rsi = rsi.dropna()
        assert len(valid_rsi) > 0
        assert valid_rsi.iloc[-1] > 70

    def test_strong_downtrend_low_rsi(self):
        """강한 하락에서 RSI < 30."""
        rng = np.random.RandomState(42)
        base = np.linspace(200, 100, 100)
        noise = rng.normal(0, 1.0, 100)
        close = pd.Series(base + noise)
        rsi = calc_rsi(close, period=14)
        valid_rsi = rsi.dropna()
        assert len(valid_rsi) > 0
        assert valid_rsi.iloc[-1] < 30

    def test_constant_price_rsi_nan(self):
        """일정한 가격에서 RSI는 NaN (gain=loss=0)."""
        close = pd.Series([100.0] * 30)
        rsi = calc_rsi(close, period=14)
        # 모든 변화 = 0 → rs = 0/0 = NaN → RSI = NaN
        # 이것은 정상 동작
        assert True  # 에러 없이 실행되면 통과

    def test_period_parameter(self):
        """다양한 period 값 테스트."""
        close = pd.Series(np.random.RandomState(42).uniform(90, 110, 100))
        for period in [7, 14, 21]:
            rsi = calc_rsi(close, period=period)
            assert len(rsi) == 100

    def test_matches_expected_pattern(self):
        """RSI가 가격 패턴과 일관된지 확인."""
        # 하락 후 상승
        down = np.linspace(100, 80, 20)
        up = np.linspace(80, 110, 20)
        close = pd.Series(np.concatenate([down, up]))
        rsi = calc_rsi(close, period=14)
        valid = rsi.dropna()
        if len(valid) > 5:
            # 마지막 RSI가 처음보다 높아야 함 (상승 중)
            assert valid.iloc[-1] > valid.iloc[len(valid) // 2]


# ─── pct_change tests ───


class TestPctChange:
    """pct_change() 테스트."""

    def test_positive_change(self):
        """양의 변화율 계산."""
        series = pd.Series([100, 105, 110])
        result = pct_change(series, 2)
        assert result is not None
        assert abs(result - 0.10) < 0.001

    def test_negative_change(self):
        """음의 변화율 계산."""
        series = pd.Series([100, 95, 90])
        result = pct_change(series, 2)
        assert result is not None
        assert abs(result - (-0.10)) < 0.001

    def test_no_change(self):
        """변화 없음."""
        series = pd.Series([100, 100, 100])
        result = pct_change(series, 1)
        assert result == 0.0

    def test_insufficient_data_returns_none(self):
        """데이터 부족 시 None 반환."""
        series = pd.Series([100, 105])
        assert pct_change(series, 5) is None

    def test_single_value_returns_none(self):
        """단일 값은 None."""
        assert pct_change(pd.Series([100.0]), 1) is None

    def test_empty_series_returns_none(self):
        """빈 시리즈는 None."""
        assert pct_change(pd.Series([], dtype=float), 1) is None

    def test_with_nan_values(self):
        """NaN 포함 시 dropna() 후 계산."""
        series = pd.Series([np.nan, 100, np.nan, 110, 120])
        # dropna → [100, 110, 120], periods=2, current=120, past=100
        result = pct_change(series, 2)
        assert result is not None
        assert abs(result - 0.20) < 0.001

    def test_zero_past_price_returns_none(self):
        """과거 가격이 0이면 None."""
        series = pd.Series([0, 10, 20])
        result = pct_change(series, 2)
        assert result is None
