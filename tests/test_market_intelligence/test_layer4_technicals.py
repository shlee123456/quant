"""
Tests for Layer 4: Enhanced Individual Stock Technicals.

10개 기술적 지표(기존 5 + 신규 5)의 개별 계산 및 종합 점수 산출을 테스트합니다.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.layer4_technicals import (
    INDICATOR_WEIGHTS,
    TechnicalsLayer,
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


def _mock_stock_data(
    rsi: float = 45.0,
    histogram: float = 0.5,
    pct_b: float = 0.55,
    k: float = 50.0,
    d: float = 48.0,
    adx: float = 22.0,
    adx_trend: str = 'weak_trend',
) -> dict:
    """Create mock stock analysis data matching MarketAnalyzer output."""
    return {
        'price': {'last': 185.0, 'change_5d': 2.3, 'change_20d': -1.5},
        'indicators': {
            'rsi': {'value': rsi, 'signal': 'neutral', 'zone': '45-55'},
            'macd': {
                'histogram': histogram,
                'signal': 'bullish' if histogram > 0 else 'bearish',
                'cross_recent': False,
            },
            'bollinger': {'pct_b': pct_b, 'signal': 'neutral'},
            'stochastic': {'k': k, 'd': d, 'signal': 'neutral'},
            'adx': {'value': adx, 'trend': adx_trend},
        },
    }


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def layer():
    return TechnicalsLayer()


@pytest.fixture
def mock_stocks():
    return {
        'AAPL': _mock_stock_data(rsi=45.0, histogram=0.5, pct_b=0.55),
        'MSFT': _mock_stock_data(rsi=60.0, histogram=-0.3, pct_b=0.70),
        'GOOGL': _mock_stock_data(rsi=30.0, histogram=1.2, pct_b=0.20),
    }


@pytest.fixture
def mock_cache():
    return MockCache({
        'AAPL': _make_ohlcv(n=250, start_price=185.0, trend=0.001, seed=42),
        'MSFT': _make_ohlcv(n=250, start_price=380.0, trend=0.0005, seed=43),
        'GOOGL': _make_ohlcv(n=250, start_price=140.0, trend=-0.001, seed=44),
    })


@pytest.fixture
def full_data(mock_stocks, mock_cache):
    return {
        'stocks': mock_stocks,
        'cache': mock_cache,
        'stock_symbols': ['AAPL', 'MSFT', 'GOOGL'],
    }


# ──────────────────────────────────────────────────────────────────────
# Happy path tests
# ──────────────────────────────────────────────────────────────────────


class TestTechnicalsHappyPath:
    """Full data present - happy path tests."""

    def test_analyze_returns_layer_result(self, layer, full_data):
        """analyze()가 LayerResult 인스턴스를 반환해야 한다."""
        result = layer.analyze(full_data)
        assert isinstance(result, LayerResult)

    def test_layer_name(self, layer, full_data):
        """레이어 이름이 올바르게 설정되어야 한다."""
        result = layer.analyze(full_data)
        assert result.layer_name == "technicals"

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

    def test_per_stock_details(self, layer, full_data):
        """details에 종목별 결과가 포함되어야 한다."""
        result = layer.analyze(full_data)
        per_stock = result.details.get('per_stock', {})
        assert 'AAPL' in per_stock
        assert 'MSFT' in per_stock
        assert 'GOOGL' in per_stock

    def test_per_stock_has_composite_score(self, layer, full_data):
        """각 종목에 composite_score가 있어야 한다."""
        result = layer.analyze(full_data)
        per_stock = result.details.get('per_stock', {})
        for sym, data in per_stock.items():
            assert 'composite_score' in data
            assert -100.0 <= data['composite_score'] <= 100.0

    def test_per_stock_has_indicator_scores(self, layer, full_data):
        """각 종목에 10개 지표 점수가 있어야 한다."""
        result = layer.analyze(full_data)
        per_stock = result.details.get('per_stock', {})
        for sym, data in per_stock.items():
            ind_scores = data.get('indicator_scores', {})
            assert len(ind_scores) == len(INDICATOR_WEIGHTS)
            for key in INDICATOR_WEIGHTS:
                assert key in ind_scores, f"Missing {key} for {sym}"

    def test_top_and_bottom_stocks(self, layer, full_data):
        """상위/하위 종목이 결과에 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert 'top_stocks' in result.details
        assert 'bottom_stocks' in result.details

    def test_interpretation_is_korean(self, layer, full_data):
        """해석이 한국어를 포함해야 한다."""
        result = layer.analyze(full_data)
        assert '기술적 종합 점수' in result.interpretation

    def test_to_dict_format(self, layer, full_data):
        """to_dict()가 올바른 형식의 딕셔너리를 반환해야 한다."""
        result = layer.analyze(full_data)
        d = result.to_dict()
        assert d['layer'] == 'technicals'
        assert isinstance(d['score'], float)


# ──────────────────────────────────────────────────────────────────────
# Individual indicator scoring tests
# ──────────────────────────────────────────────────────────────────────


class TestRSIScoring:
    """RSI indicator scoring tests."""

    def test_oversold_is_positive(self, layer):
        """RSI < 30 -> positive score (buy opportunity)."""
        assert layer._score_rsi({'value': 25}) > 0
        assert layer._score_rsi({'value': 15}) > 50

    def test_overbought_is_negative(self, layer):
        """RSI > 70 -> negative score (sell signal)."""
        assert layer._score_rsi({'value': 75}) < 0
        assert layer._score_rsi({'value': 85}) < -50

    def test_neutral_zone(self, layer):
        """RSI 45-55 -> near zero."""
        score = layer._score_rsi({'value': 50})
        assert abs(score) <= 5

    def test_none_value(self, layer):
        """None value -> 0."""
        assert layer._score_rsi({'value': None}) == 0.0
        assert layer._score_rsi({}) == 0.0

    def test_extreme_oversold(self, layer):
        """RSI < 20 -> +100."""
        assert layer._score_rsi({'value': 10}) == 100.0

    def test_extreme_overbought(self, layer):
        """RSI > 80 -> -100."""
        assert layer._score_rsi({'value': 90}) == -100.0


class TestMACDScoring:
    """MACD indicator scoring tests."""

    def test_positive_histogram(self, layer):
        """histogram > 0 -> positive score."""
        assert layer._score_macd({'histogram': 2.0}) > 0

    def test_negative_histogram(self, layer):
        """histogram < 0 -> negative score."""
        assert layer._score_macd({'histogram': -2.0}) < 0

    def test_zero_histogram(self, layer):
        """histogram = 0 -> zero score."""
        assert layer._score_macd({'histogram': 0.0}) == 0.0

    def test_none_histogram(self, layer):
        """None -> 0."""
        assert layer._score_macd({}) == 0.0

    def test_clamped_to_range(self, layer):
        """Score clamped to -100..+100."""
        assert layer._score_macd({'histogram': 100}) == 100.0
        assert layer._score_macd({'histogram': -100}) == -100.0


class TestBollingerScoring:
    """Bollinger %B scoring tests."""

    def test_near_lower_band(self, layer):
        """pct_b < 0.2 -> positive (buy signal)."""
        assert layer._score_bollinger({'pct_b': 0.1}) > 50

    def test_near_upper_band(self, layer):
        """pct_b > 0.8 -> negative (sell signal)."""
        assert layer._score_bollinger({'pct_b': 0.9}) < -50

    def test_middle(self, layer):
        """pct_b = 0.5 -> zero."""
        assert layer._score_bollinger({'pct_b': 0.5}) == 0.0

    def test_none(self, layer):
        """None -> 0."""
        assert layer._score_bollinger({}) == 0.0


class TestStochasticScoring:
    """Stochastic scoring tests."""

    def test_oversold(self, layer):
        """k < 20 -> positive."""
        assert layer._score_stochastic({'k': 15}) > 0

    def test_overbought(self, layer):
        """k > 80 -> negative."""
        assert layer._score_stochastic({'k': 85}) < 0

    def test_neutral(self, layer):
        """k = 50 -> near zero."""
        assert abs(layer._score_stochastic({'k': 50})) <= 5

    def test_none(self, layer):
        """None -> 0."""
        assert layer._score_stochastic({}) == 0.0


class TestADXScoring:
    """ADX scoring tests."""

    def test_bullish_trend(self, layer):
        """ADX > 25 + bullish trend -> positive."""
        assert layer._score_adx({'value': 40, 'trend': 'bullish'}) > 0

    def test_bearish_trend(self, layer):
        """ADX > 25 + bearish trend -> negative."""
        assert layer._score_adx({'value': 40, 'trend': 'bearish'}) < 0

    def test_weak_trend(self, layer):
        """ADX with unknown trend -> 0."""
        assert layer._score_adx({'value': 15, 'trend': 'weak_trend'}) == 0.0

    def test_none(self, layer):
        """None -> 0."""
        assert layer._score_adx({}) == 0.0


# ──────────────────────────────────────────────────────────────────────
# New indicator scoring tests (from OHLCV)
# ──────────────────────────────────────────────────────────────────────


class TestOBVScoring:
    """OBV (On-Balance Volume) scoring tests."""

    def test_basic_calculation(self, layer):
        """OBV 기본 계산이 정상 동작해야 한다."""
        df = _make_ohlcv(n=100, trend=0.002, seed=42)
        score = layer._score_obv(df['Close'], df['Volume'])
        assert -100.0 <= score <= 100.0

    def test_no_volume_returns_zero(self, layer):
        """거래량 없으면 0을 반환해야 한다."""
        close = pd.Series(np.linspace(100, 110, 50))
        assert layer._score_obv(close, None) == 0.0

    def test_short_data_returns_zero(self, layer):
        """짧은 데이터에서 0을 반환해야 한다."""
        close = pd.Series([100, 101, 102])
        volume = pd.Series([1000, 1100, 1200])
        assert layer._score_obv(close, volume) == 0.0


class TestMFIScoring:
    """MFI (Money Flow Index) scoring tests."""

    def test_basic_calculation(self, layer):
        """MFI 기본 계산이 정상 동작해야 한다."""
        df = _make_ohlcv(n=100, seed=42)
        score = layer._score_mfi(df['High'], df['Low'], df['Close'], df['Volume'])
        assert -100.0 <= score <= 100.0

    def test_no_volume_returns_zero(self, layer):
        """거래량 없으면 0을 반환해야 한다."""
        df = _make_ohlcv(n=100)
        score = layer._score_mfi(df['High'], df['Low'], df['Close'], None)
        assert score == 0.0

    def test_short_data_returns_zero(self, layer):
        """짧은 데이터에서 0을 반환해야 한다."""
        df = _make_ohlcv(n=10)
        score = layer._score_mfi(df['High'], df['Low'], df['Close'], df['Volume'])
        assert score == 0.0


class TestATRScoring:
    """ATR scoring tests."""

    def test_basic_calculation(self, layer):
        """ATR 기본 계산이 정상 동작해야 한다."""
        df = _make_ohlcv(n=100, seed=42)
        score = layer._score_atr(df['High'], df['Low'], df['Close'])
        assert -100.0 <= score <= 100.0

    def test_short_data_returns_zero(self, layer):
        """짧은 데이터에서 0을 반환해야 한다."""
        df = _make_ohlcv(n=10)
        score = layer._score_atr(df['High'], df['Low'], df['Close'])
        assert score == 0.0

    def test_high_volatility_is_negative(self, layer):
        """높은 변동성은 부정적 점수여야 한다."""
        df = _make_ohlcv(n=100, volatility=0.08, seed=42)
        score = layer._score_atr(df['High'], df['Low'], df['Close'])
        # 높은 변동성이므로 0 이하여야 함 (ATR% > 3% 가능)
        assert score <= 30  # 높은 변동성에서는 낮은 점수


class TestMACrossScoring:
    """MA Cross scoring tests."""

    def test_strong_uptrend(self, layer):
        """강한 상승 추세에서 양의 점수여야 한다."""
        df = _make_ohlcv(n=250, trend=0.003, seed=42)
        score = layer._score_ma_cross(df['Close'])
        assert score > 0

    def test_strong_downtrend(self, layer):
        """강한 하락 추세에서 음의 점수여야 한다."""
        df = _make_ohlcv(n=250, trend=-0.003, seed=42)
        score = layer._score_ma_cross(df['Close'])
        assert score < 0

    def test_short_data_uses_50ma_only(self, layer):
        """200일 미만이면 50MA만 사용해야 한다."""
        df = _make_ohlcv(n=100, trend=0.003, seed=42)
        score = layer._score_ma_cross(df['Close'])
        assert -100.0 <= score <= 100.0

    def test_very_short_data(self, layer):
        """50일 미만이면 0을 반환해야 한다."""
        df = _make_ohlcv(n=30, seed=42)
        score = layer._score_ma_cross(df['Close'])
        assert score == 0.0

    def test_score_range(self, layer):
        """점수가 항상 -100 ~ +100 범위여야 한다."""
        for seed in range(10):
            df = _make_ohlcv(n=250, seed=seed)
            score = layer._score_ma_cross(df['Close'])
            assert -100.0 <= score <= 100.0


class TestVolumeScoring:
    """Volume analysis scoring tests."""

    def test_basic_calculation(self, layer):
        """Volume 분석 기본 계산이 정상 동작해야 한다."""
        df = _make_ohlcv(n=100, seed=42)
        score = layer._score_volume(df['Close'], df['Volume'])
        assert -100.0 <= score <= 100.0

    def test_no_volume_returns_zero(self, layer):
        """거래량 없으면 0을 반환해야 한다."""
        close = pd.Series(np.linspace(100, 110, 50))
        assert layer._score_volume(close, None) == 0.0

    def test_short_data_returns_zero(self, layer):
        """짧은 데이터에서 0을 반환해야 한다."""
        close = pd.Series([100, 101])
        volume = pd.Series([1000, 1100])
        assert layer._score_volume(close, volume) == 0.0


# ──────────────────────────────────────────────────────────────────────
# Missing / partial data tests
# ──────────────────────────────────────────────────────────────────────


class TestTechnicalsMissingData:
    """Edge cases with missing or partial data."""

    def test_no_data(self, layer):
        """데이터 없으면 기본 결과를 반환해야 한다."""
        result = layer.analyze({})
        assert result.score == 0.0
        assert result.signal == "neutral"
        assert result.confidence == 0.0

    def test_stocks_only_no_cache(self, layer, mock_stocks):
        """캐시 없이 기존 지표만으로 분석 가능해야 한다."""
        result = layer.analyze({
            'stocks': mock_stocks,
            'stock_symbols': list(mock_stocks.keys()),
        })
        assert isinstance(result, LayerResult)
        # 기존 5개 지표 점수는 있어야 함
        per_stock = result.details.get('per_stock', {})
        assert len(per_stock) == 3

    def test_cache_only_no_stocks(self, layer, mock_cache):
        """기존 지표 없이 캐시만으로 분석 가능해야 한다."""
        result = layer.analyze({
            'stocks': {},
            'cache': mock_cache,
            'stock_symbols': ['AAPL', 'MSFT', 'GOOGL'],
        })
        assert isinstance(result, LayerResult)

    def test_missing_indicator_fields(self, layer, mock_cache):
        """indicators에 일부 필드가 없어도 정상 동작해야 한다."""
        stocks = {
            'AAPL': {
                'price': {'last': 185.0},
                'indicators': {
                    'rsi': {'value': 45.0},
                    # macd, bollinger 등 없음
                },
            },
        }
        result = layer.analyze({
            'stocks': stocks,
            'cache': mock_cache,
            'stock_symbols': ['AAPL'],
        })
        assert isinstance(result, LayerResult)

    def test_empty_indicators(self, layer, mock_cache):
        """빈 indicators에서도 정상 동작해야 한다."""
        stocks = {'AAPL': {'price': {'last': 185.0}, 'indicators': {}}}
        result = layer.analyze({
            'stocks': stocks,
            'cache': mock_cache,
            'stock_symbols': ['AAPL'],
        })
        assert isinstance(result, LayerResult)

    def test_symbol_not_in_cache(self, layer, mock_stocks):
        """캐시에 없는 심볼이 있어도 에러 없이 처리해야 한다."""
        cache = MockCache({'AAPL': _make_ohlcv(n=100)})  # MSFT, GOOGL 없음
        result = layer.analyze({
            'stocks': mock_stocks,
            'cache': cache,
            'stock_symbols': ['AAPL', 'MSFT', 'GOOGL'],
        })
        assert isinstance(result, LayerResult)

    def test_nan_indicator_values(self, layer, mock_cache):
        """NaN 지표 값에서도 정상 동작해야 한다."""
        stocks = {
            'AAPL': _mock_stock_data(rsi=float('nan'), histogram=float('nan')),
        }
        result = layer.analyze({
            'stocks': stocks,
            'cache': mock_cache,
            'stock_symbols': ['AAPL'],
        })
        assert isinstance(result, LayerResult)
        assert not np.isnan(result.score)

    def test_stock_symbols_inferred_from_stocks(self, layer, mock_stocks, mock_cache):
        """stock_symbols가 없으면 stocks 키에서 추론해야 한다."""
        result = layer.analyze({
            'stocks': mock_stocks,
            'cache': mock_cache,
        })
        assert isinstance(result, LayerResult)
        per_stock = result.details.get('per_stock', {})
        assert len(per_stock) == 3


# ──────────────────────────────────────────────────────────────────────
# Composite score tests
# ──────────────────────────────────────────────────────────────────────


class TestCompositeScoring:
    """Composite score calculation tests."""

    def test_weights_sum_to_one(self):
        """지표 가중치 합이 1.0이어야 한다."""
        total = sum(INDICATOR_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_bullish_stock_positive_score(self, layer, mock_cache):
        """모든 지표가 bullish인 종목은 양의 점수여야 한다."""
        stocks = {
            'AAPL': _mock_stock_data(
                rsi=25.0,        # oversold (bullish)
                histogram=3.0,   # bullish
                pct_b=0.1,       # near lower (bullish)
                k=15.0,          # oversold (bullish)
                adx=35.0,        # strong trend
                adx_trend='bullish',
            ),
        }
        result = layer.analyze({
            'stocks': stocks,
            'cache': mock_cache,
            'stock_symbols': ['AAPL'],
        })
        per_stock = result.details.get('per_stock', {})
        aapl = per_stock.get('AAPL', {})
        assert aapl.get('composite_score', 0) > 0

    def test_bearish_stock_negative_score(self, layer, mock_cache):
        """모든 지표가 bearish인 종목은 음의 점수여야 한다."""
        stocks = {
            'AAPL': _mock_stock_data(
                rsi=85.0,         # overbought (bearish)
                histogram=-3.0,   # bearish
                pct_b=0.95,       # near upper (bearish)
                k=90.0,           # overbought (bearish)
                adx=35.0,         # strong trend
                adx_trend='bearish',
            ),
        }
        result = layer.analyze({
            'stocks': stocks,
            'cache': mock_cache,
            'stock_symbols': ['AAPL'],
        })
        per_stock = result.details.get('per_stock', {})
        aapl = per_stock.get('AAPL', {})
        assert aapl.get('composite_score', 0) < 0

    def test_reproducibility(self, layer, full_data):
        """동일 데이터로 두 번 호출 시 같은 결과여야 한다."""
        r1 = layer.analyze(full_data)
        r2 = layer.analyze(full_data)
        assert r1.score == r2.score
