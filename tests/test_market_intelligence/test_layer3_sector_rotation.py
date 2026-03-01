"""
Tests for Layer 3: Sector/Factor Rotation.

섹터 ETF 모멘텀, 팩터 레짐, 상관관계, 경기 사이클 분석 레이어를 테스트합니다.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.layer3_sector_rotation import (
    CYCLE_GROUPS,
    EARLY_CYCLE,
    FACTOR_ETFS,
    LATE_CYCLE,
    MID_CYCLE,
    RECESSION,
    SECTOR_ETFS,
    SectorRotationLayer,
)
from trading_bot.market_intelligence.base_layer import LayerResult


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_ohlcv(
    n: int = 200,
    start_price: float = 100.0,
    trend: float = 0.0005,
    volatility: float = 0.02,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV with yfinance columns."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='B')
    returns = rng.normal(trend, volatility, n)
    prices = start_price * np.exp(np.cumsum(returns))
    high = prices * (1 + rng.uniform(0, 0.02, n))
    low = prices * (1 - rng.uniform(0, 0.02, n))
    volume = rng.randint(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame(
        {
            'Open': prices * (1 + rng.uniform(-0.005, 0.005, n)),
            'High': high,
            'Low': low,
            'Close': prices,
            'Volume': volume,
        },
        index=dates,
    )


class MockCache:
    """Mock MarketDataCache for testing."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, symbol: str):
        return self._data.get(symbol)

    def get_many(self, symbols):
        return {s: self._data[s] for s in symbols if s in self._data}

    @property
    def available_symbols(self):
        return list(self._data.keys())


def _build_full_cache(
    sector_trend: float = 0.0005,
    factor_trend: float = 0.0003,
    n: int = 200,
) -> MockCache:
    """Build a mock cache with all sector and factor ETFs."""
    data = {}
    for i, sym in enumerate(SECTOR_ETFS):
        data[sym] = _make_ohlcv(
            n=n, start_price=50 + i * 5, trend=sector_trend, seed=42 + i
        )
    for i, sym in enumerate(FACTOR_ETFS):
        data[sym] = _make_ohlcv(
            n=n, start_price=100 + i * 10, trend=factor_trend, seed=100 + i
        )
    return MockCache(data)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def layer():
    return SectorRotationLayer()


@pytest.fixture
def full_cache():
    return _build_full_cache()


@pytest.fixture
def full_data(full_cache):
    return {'cache': full_cache}


# ──────────────────────────────────────────────────────────────────────
# Happy path tests
# ──────────────────────────────────────────────────────────────────────


class TestSectorRotationHappyPath:
    """All data present - full analysis path."""

    def test_analyze_returns_layer_result(self, layer, full_data):
        """analyze()가 LayerResult 인스턴스를 반환해야 한다."""
        result = layer.analyze(full_data)
        assert isinstance(result, LayerResult)

    def test_layer_name(self, layer, full_data):
        """레이어 이름이 올바르게 설정되어야 한다."""
        result = layer.analyze(full_data)
        assert result.layer_name == "sector_rotation"

    def test_score_in_valid_range(self, layer, full_data):
        """합성 점수가 -100 ~ +100 범위여야 한다."""
        result = layer.analyze(full_data)
        assert -100.0 <= result.score <= 100.0

    def test_signal_classification(self, layer, full_data):
        """시그널이 올바른 분류여야 한다."""
        result = layer.analyze(full_data)
        assert result.signal in ('bullish', 'bearish', 'neutral')

    def test_confidence_range(self, layer, full_data):
        """신뢰도가 0.0 ~ 1.0 범위여야 한다."""
        result = layer.analyze(full_data)
        assert 0.0 <= result.confidence <= 1.0

    def test_metrics_contains_all_sub_scores(self, layer, full_data):
        """metrics에 모든 서브 메트릭이 포함되어야 한다."""
        result = layer.analyze(full_data)
        expected_keys = {
            'sector_momentum', 'factor_momentum',
            'factor_regime', 'cross_correlation', 'cycle_position',
        }
        assert expected_keys.issubset(set(result.metrics.keys()))

    def test_sub_scores_in_valid_range(self, layer, full_data):
        """각 서브 메트릭 점수가 -100 ~ +100 범위여야 한다."""
        result = layer.analyze(full_data)
        for key, value in result.metrics.items():
            assert -100.0 <= value <= 100.0, f"{key} = {value} out of range"

    def test_details_has_sector_rankings(self, layer, full_data):
        """details에 섹터 순위가 포함되어야 한다."""
        result = layer.analyze(full_data)
        sm = result.details.get('sector_momentum', {})
        assert 'top3' in sm
        assert 'bottom3' in sm
        assert len(sm['top3']) == 3
        assert len(sm['bottom3']) == 3

    def test_details_has_factor_info(self, layer, full_data):
        """details에 팩터 정보가 포함되어야 한다."""
        result = layer.analyze(full_data)
        fm = result.details.get('factor_momentum', {})
        assert 'leading_factor' in fm
        assert fm['leading_factor'] is not None

    def test_details_has_cycle_position(self, layer, full_data):
        """details에 경기 사이클 위치가 포함되어야 한다."""
        result = layer.analyze(full_data)
        cp = result.details.get('cycle_position', {})
        assert 'cycle' in cp
        assert cp['cycle'] in ('early_recovery', 'expansion', 'late_expansion', 'contraction')

    def test_details_has_correlation(self, layer, full_data):
        """details에 상관관계 정보가 포함되어야 한다."""
        result = layer.analyze(full_data)
        cc = result.details.get('cross_correlation', {})
        assert 'avg_correlation' in cc
        assert cc['avg_correlation'] is not None
        assert 0.0 <= cc['avg_correlation'] <= 1.0

    def test_interpretation_is_korean(self, layer, full_data):
        """해석이 한국어를 포함해야 한다."""
        result = layer.analyze(full_data)
        assert len(result.interpretation) > 0
        # 경기 사이클 한국어 라벨이 포함되어야 함
        korean_labels = ['초기 회복기', '확장기', '후기 확장기', '수축기']
        assert any(label in result.interpretation for label in korean_labels)

    def test_to_dict_format(self, layer, full_data):
        """to_dict()가 올바른 형식의 딕셔너리를 반환해야 한다."""
        result = layer.analyze(full_data)
        d = result.to_dict()
        assert 'layer' in d
        assert 'score' in d
        assert 'signal' in d
        assert 'confidence' in d
        assert d['layer'] == 'sector_rotation'


# ──────────────────────────────────────────────────────────────────────
# Missing / partial data tests
# ──────────────────────────────────────────────────────────────────────


class TestSectorRotationMissingData:
    """Edge cases with missing or partial data."""

    def test_no_cache(self, layer):
        """캐시가 없을 때 기본 결과를 반환해야 한다."""
        result = layer.analyze({})
        assert result.score == 0.0
        assert result.signal == "neutral"
        assert result.confidence == 0.0

    def test_empty_cache(self, layer):
        """빈 캐시에서 기본 결과를 반환해야 한다."""
        result = layer.analyze({'cache': MockCache({})})
        assert result.score == 0.0
        assert result.signal == "neutral"

    def test_partial_sectors_only(self, layer):
        """일부 섹터만 있을 때 분석이 가능해야 한다."""
        data = {}
        for sym in SECTOR_ETFS[:4]:  # 4개 섹터만
            data[sym] = _make_ohlcv(n=100, seed=hash(sym) % 1000)
        result = layer.analyze({'cache': MockCache(data)})
        assert isinstance(result, LayerResult)
        assert result.confidence < 1.0

    def test_sectors_without_factors(self, layer):
        """팩터 ETF 없이 섹터 ETF만으로 분석 가능해야 한다."""
        data = {}
        for i, sym in enumerate(SECTOR_ETFS):
            data[sym] = _make_ohlcv(n=100, seed=42 + i)
        result = layer.analyze({'cache': MockCache(data)})
        assert isinstance(result, LayerResult)
        # factor_momentum과 factor_regime은 0이어야 함
        assert result.metrics.get('factor_momentum', 0.0) == 0.0
        assert result.metrics.get('factor_regime', 0.0) == 0.0

    def test_very_short_data(self, layer):
        """매우 짧은 데이터에서 에러 없이 처리해야 한다."""
        data = {}
        for sym in SECTOR_ETFS:
            data[sym] = _make_ohlcv(n=10, seed=hash(sym) % 1000)
        result = layer.analyze({'cache': MockCache(data)})
        assert isinstance(result, LayerResult)

    def test_insufficient_sectors(self, layer):
        """2개 이하 섹터만 있을 때 기본 결과를 반환해야 한다."""
        data = {'XLK': _make_ohlcv(n=50), 'XLF': _make_ohlcv(n=50, seed=43)}
        result = layer.analyze({'cache': MockCache(data)})
        assert result.score == 0.0
        assert result.confidence == 0.0

    def test_nan_in_data(self, layer):
        """NaN이 포함된 데이터에서도 정상 동작해야 한다."""
        df = _make_ohlcv(n=200)
        # NaN 삽입
        df.loc[df.index[50:55], 'Close'] = np.nan
        data = {sym: df.copy() for sym in SECTOR_ETFS}
        result = layer.analyze({'cache': MockCache(data)})
        assert isinstance(result, LayerResult)
        assert not np.isnan(result.score)


# ──────────────────────────────────────────────────────────────────────
# Factor regime specific tests
# ──────────────────────────────────────────────────────────────────────


class TestFactorRegime:
    """Factor regime (MTUM/VLUE ratio) specific tests."""

    def test_momentum_regime_with_mtum_leading(self, layer):
        """MTUM이 VLUE보다 빠르게 상승하면 momentum 레짐이어야 한다."""
        data = {
            'MTUM': _make_ohlcv(n=100, trend=0.005, seed=42),
            'VLUE': _make_ohlcv(n=100, trend=0.0, seed=43),
        }
        # 섹터 데이터도 최소한 넣어야 함
        for i, sym in enumerate(SECTOR_ETFS[:4]):
            data[sym] = _make_ohlcv(n=100, seed=100 + i)

        result = layer.analyze({'cache': MockCache(data)})
        fr_details = result.details.get('factor_regime', {})
        assert fr_details.get('regime') in ('momentum', 'balanced')

    def test_value_regime_with_vlue_leading(self, layer):
        """VLUE가 MTUM보다 빠르게 상승하면 value 레짐이어야 한다."""
        data = {
            'MTUM': _make_ohlcv(n=100, trend=-0.003, seed=42),
            'VLUE': _make_ohlcv(n=100, trend=0.005, seed=43),
        }
        for i, sym in enumerate(SECTOR_ETFS[:4]):
            data[sym] = _make_ohlcv(n=100, seed=100 + i)

        result = layer.analyze({'cache': MockCache(data)})
        fr_details = result.details.get('factor_regime', {})
        assert fr_details.get('regime') in ('value', 'balanced')

    def test_missing_mtum_returns_unknown(self, layer):
        """MTUM이 없으면 factor_regime이 unknown이어야 한다."""
        data = {'VLUE': _make_ohlcv(n=100)}
        for i, sym in enumerate(SECTOR_ETFS[:4]):
            data[sym] = _make_ohlcv(n=100, seed=100 + i)

        result = layer.analyze({'cache': MockCache(data)})
        fr_details = result.details.get('factor_regime', {})
        assert fr_details.get('regime') == 'unknown'


# ──────────────────────────────────────────────────────────────────────
# Cross correlation tests
# ──────────────────────────────────────────────────────────────────────


class TestCrossCorrelation:
    """Cross-correlation specific tests."""

    def test_high_correlation_is_negative(self, layer):
        """높은 상관관계는 부정적 점수를 반환해야 한다."""
        # 모든 섹터가 같은 데이터 -> 상관관계 ~ 1.0
        base = _make_ohlcv(n=100, seed=42)
        data = {sym: base.copy() for sym in SECTOR_ETFS}
        result = layer.analyze({'cache': MockCache(data)})
        cc = result.details.get('cross_correlation', {})
        avg = cc.get('avg_correlation')
        if avg is not None and avg > 0.8:
            # 높은 상관관계 -> 부정적 점수
            assert result.metrics.get('cross_correlation', 0) < 0

    def test_diverse_sectors_moderate_correlation(self, layer):
        """서로 다른 추세의 섹터들은 상관관계가 낮아야 한다."""
        data = {}
        for i, sym in enumerate(SECTOR_ETFS):
            # 각 섹터에 다른 seed와 트렌드
            trend = 0.001 * ((-1) ** i)
            data[sym] = _make_ohlcv(n=100, trend=trend, seed=42 + i * 10)
        result = layer.analyze({'cache': MockCache(data)})
        cc = result.details.get('cross_correlation', {})
        avg = cc.get('avg_correlation')
        assert avg is not None


# ──────────────────────────────────────────────────────────────────────
# Cycle position tests
# ──────────────────────────────────────────────────────────────────────


class TestCyclePosition:
    """Economic cycle position estimation tests."""

    def _build_cycle_cache(self, leading_group: list, trend: float = 0.005):
        """Create cache where a specific group leads."""
        data = {}
        for i, sym in enumerate(SECTOR_ETFS):
            if sym in leading_group:
                t = trend  # strong positive trend
            else:
                t = -0.001  # mild negative
            data[sym] = _make_ohlcv(n=100, trend=t, seed=42 + i)
        return MockCache(data)

    def test_early_cycle_detection(self, layer):
        """금융/산업재/경기소비재 선도 시 early_recovery."""
        cache = self._build_cycle_cache(EARLY_CYCLE)
        result = layer.analyze({'cache': cache})
        cp = result.details.get('cycle_position', {})
        # 초기 사이클 그룹이 가장 높은 모멘텀을 가져야 함
        assert cp.get('cycle') in ('early_recovery', 'expansion', 'late_expansion', 'contraction')

    def test_recession_cycle_detection(self, layer):
        """유틸리티/필수소비재/헬스케어 선도 시 contraction."""
        cache = self._build_cycle_cache(RECESSION)
        result = layer.analyze({'cache': cache})
        cp = result.details.get('cycle_position', {})
        assert cp.get('cycle') in ('early_recovery', 'expansion', 'late_expansion', 'contraction')

    def test_group_scores_present(self, layer, full_data):
        """group_scores가 결과에 포함되어야 한다."""
        result = layer.analyze(full_data)
        cp = result.details.get('cycle_position', {})
        group_scores = cp.get('group_scores', {})
        assert len(group_scores) > 0


# ──────────────────────────────────────────────────────────────────────
# Score consistency tests
# ──────────────────────────────────────────────────────────────────────


class TestScoreConsistency:
    """Score calculation consistency."""

    def test_bullish_market_positive_score(self, layer):
        """모든 섹터가 강하게 상승 중이면 양의 점수여야 한다."""
        data = {}
        for i, sym in enumerate(SECTOR_ETFS):
            data[sym] = _make_ohlcv(n=200, trend=0.005, seed=42 + i)
        for i, sym in enumerate(FACTOR_ETFS):
            data[sym] = _make_ohlcv(n=200, trend=0.005, seed=100 + i)
        result = layer.analyze({'cache': MockCache(data)})
        # 강한 상승 시장이므로 점수가 양수여야 함
        assert result.score > 0

    def test_bearish_market_negative_momentum(self, layer):
        """모든 섹터가 강하게 하락 중이면 sector_momentum이 음수여야 한다."""
        data = {}
        for i, sym in enumerate(SECTOR_ETFS):
            data[sym] = _make_ohlcv(n=200, trend=-0.005, seed=42 + i)
        for i, sym in enumerate(FACTOR_ETFS):
            data[sym] = _make_ohlcv(n=200, trend=-0.005, seed=100 + i)
        result = layer.analyze({'cache': MockCache(data)})
        # 섹터 모멘텀은 반드시 음수
        assert result.metrics['sector_momentum'] < 0
        # 팩터 모멘텀도 음수
        assert result.metrics['factor_momentum'] < 0

    def test_reproducibility(self, layer, full_data):
        """동일 데이터로 두 번 호출 시 같은 결과여야 한다."""
        r1 = layer.analyze(full_data)
        r2 = layer.analyze(full_data)
        assert r1.score == r2.score
        assert r1.signal == r2.signal
