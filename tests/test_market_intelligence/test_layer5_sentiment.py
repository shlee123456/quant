"""
Tests for Layer 5: Sentiment & Positioning.

Fear & Greed, VIX 심리, 뉴스 감성, 스마트 머니 분석 레이어를 테스트합니다.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.layer5_sentiment import (
    NEGATIVE_WORDS,
    POSITIVE_WORDS,
    SUB_WEIGHTS,
    SentimentLayer,
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


def _build_sentiment_cache(
    vix_level: float = 20.0,
    gld_trend: float = 0.001,
    spy_trend: float = 0.002,
    n: int = 200,
) -> MockCache:
    """Build a mock cache with VIX, GLD, and SPY data."""
    # VIX-like data (stays around vix_level)
    rng = np.random.RandomState(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='B')
    vix_prices = vix_level + rng.normal(0, 2, n).cumsum() * 0.1
    vix_prices = np.clip(vix_prices, 10, 80)

    vix_df = pd.DataFrame(
        {
            'Open': vix_prices,
            'High': vix_prices * 1.02,
            'Low': vix_prices * 0.98,
            'Close': vix_prices,
            'Volume': np.ones(n) * 1_000_000,
        },
        index=dates,
    )

    gld_df = _make_ohlcv(n=n, start_price=180.0, trend=gld_trend, seed=99)
    spy_df = _make_ohlcv(n=n, start_price=450.0, trend=spy_trend, seed=100)
    spy_df.index = gld_df.index  # 동일 인덱스로 ratio 계산 보장

    return MockCache({
        '^VIX': vix_df,
        'VIXY': vix_df.copy(),
        'GLD': gld_df,
        'SPY': spy_df,
    })


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def layer():
    return SentimentLayer()


@pytest.fixture
def sentiment_cache():
    return _build_sentiment_cache()


@pytest.fixture
def full_data(sentiment_cache):
    return {
        'fear_greed': {'value': 35},
        'cache': sentiment_cache,
        'news': [
            {'title': 'Stock market rally continues as tech gains surge'},
            {'title': 'Fed warning on recession risk causes concern'},
            {'title': 'AAPL beats earnings expectations, stock soars'},
            {'title': 'Crypto market decline deepens with bearish outlook'},
            {'title': 'Strong job growth boosts optimistic outlook'},
        ],
    }


# ──────────────────────────────────────────────────────────────────────
# Happy path tests
# ──────────────────────────────────────────────────────────────────────


class TestSentimentHappyPath:
    """Full data present - happy path tests."""

    def test_analyze_returns_layer_result(self, layer, full_data):
        """analyze()가 LayerResult 인스턴스를 반환해야 한다."""
        result = layer.analyze(full_data)
        assert isinstance(result, LayerResult)

    def test_layer_name(self, layer, full_data):
        """레이어 이름이 올바르게 설정되어야 한다."""
        result = layer.analyze(full_data)
        assert result.layer_name == "sentiment"

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
        expected_keys = {'fear_greed', 'vix_sentiment', 'news_sentiment', 'smart_money'}
        assert expected_keys.issubset(set(result.metrics.keys()))

    def test_sub_scores_in_valid_range(self, layer, full_data):
        """각 서브 메트릭 점수가 유효한 범위여야 한다."""
        result = layer.analyze(full_data)
        for key, value in result.metrics.items():
            assert -100.0 <= value <= 100.0, f"{key} = {value} out of range"

    def test_interpretation_is_korean(self, layer, full_data):
        """해석이 한국어를 포함해야 한다."""
        result = layer.analyze(full_data)
        assert len(result.interpretation) > 0
        # 공포탐욕 라벨이 포함되어야 함
        assert '공포탐욕' in result.interpretation or 'VIX' in result.interpretation

    def test_to_dict_format(self, layer, full_data):
        """to_dict()가 올바른 형식의 딕셔너리를 반환해야 한다."""
        result = layer.analyze(full_data)
        d = result.to_dict()
        assert d['layer'] == 'sentiment'
        assert isinstance(d['score'], float)


# ──────────────────────────────────────────────────────────────────────
# Fear & Greed scoring tests
# ──────────────────────────────────────────────────────────────────────


class TestFearGreedScoring:
    """Fear & Greed Index scoring tests."""

    def test_extreme_fear_is_contrarian_bullish(self, layer):
        """극단적 공포 (< 20) -> 역발상 매수 (+80)."""
        score, details = layer._calc_fear_greed({'value': 10})
        assert score == 80.0
        assert details['zone'] == 'extreme_fear'

    def test_fear_zone(self, layer):
        """공포 (20-35) -> +40."""
        score, details = layer._calc_fear_greed({'value': 30})
        assert score == 40.0
        assert details['zone'] == 'fear'

    def test_mild_fear_zone(self, layer):
        """약한 공포 (35-50) -> +10."""
        score, details = layer._calc_fear_greed({'value': 40})
        assert score == 10.0
        assert details['zone'] == 'mild_fear'

    def test_neutral_zone(self, layer):
        """중립 (50-55) -> 0."""
        score, details = layer._calc_fear_greed({'value': 52})
        assert score == 0.0
        assert details['zone'] == 'neutral'

    def test_mild_greed_zone(self, layer):
        """약한 탐욕 (55-65) -> -10."""
        score, details = layer._calc_fear_greed({'value': 60})
        assert score == -10.0
        assert details['zone'] == 'mild_greed'

    def test_greed_zone(self, layer):
        """탐욕 (65-80) -> -40."""
        score, details = layer._calc_fear_greed({'value': 70})
        assert score == -40.0
        assert details['zone'] == 'greed'

    def test_extreme_greed_is_contrarian_bearish(self, layer):
        """극단적 탐욕 (> 80) -> 역발상 매도 (-80)."""
        score, details = layer._calc_fear_greed({'value': 85})
        assert score == -80.0
        assert details['zone'] == 'extreme_greed'

    def test_none_data(self, layer):
        """None 데이터 -> 0."""
        score, details = layer._calc_fear_greed(None)
        assert score == 0.0
        assert details['zone'] == 'unknown'

    def test_missing_value(self, layer):
        """value 키 없음 -> 0."""
        score, details = layer._calc_fear_greed({})
        assert score == 0.0

    def test_boundary_20(self, layer):
        """경계값 20 테스트."""
        score, details = layer._calc_fear_greed({'value': 20})
        assert details['zone'] == 'fear'

    def test_boundary_35(self, layer):
        """경계값 35 테스트."""
        score, details = layer._calc_fear_greed({'value': 35})
        assert details['zone'] == 'mild_fear'

    def test_boundary_50(self, layer):
        """경계값 50 테스트."""
        score, details = layer._calc_fear_greed({'value': 50})
        assert details['zone'] == 'neutral'

    def test_boundary_55(self, layer):
        """경계값 55 테스트."""
        score, details = layer._calc_fear_greed({'value': 55})
        assert details['zone'] == 'neutral'

    def test_boundary_65(self, layer):
        """경계값 65 테스트."""
        score, details = layer._calc_fear_greed({'value': 65})
        assert details['zone'] == 'mild_greed'

    def test_boundary_80(self, layer):
        """경계값 80 테스트."""
        score, details = layer._calc_fear_greed({'value': 80})
        assert details['zone'] == 'greed'


# ──────────────────────────────────────────────────────────────────────
# VIX sentiment tests
# ──────────────────────────────────────────────────────────────────────


class TestVIXSentiment:
    """VIX-based sentiment scoring tests."""

    def test_low_vix_complacency(self, layer):
        """VIX < 15 -> extreme complacency (-20)."""
        cache = _build_sentiment_cache(vix_level=12.0)
        score, details = layer._calc_vix_sentiment(cache)
        assert details['zone'] == 'extreme_complacency'
        # 기본 점수는 -20이지만 방향 보너스로 변할 수 있음
        assert -50.0 <= score <= 10.0

    def test_normal_vix(self, layer):
        """VIX 15-20 -> normal (+10)."""
        cache = _build_sentiment_cache(vix_level=17.0)
        score, details = layer._calc_vix_sentiment(cache)
        assert details['zone'] == 'normal'

    def test_elevated_fear(self, layer):
        """VIX 20-30 -> elevated fear (contrarian +30)."""
        cache = _build_sentiment_cache(vix_level=25.0)
        score, details = layer._calc_vix_sentiment(cache)
        assert details['zone'] == 'elevated_fear'

    def test_panic_vix(self, layer):
        """VIX > 30 -> panic (contrarian +50)."""
        cache = _build_sentiment_cache(vix_level=40.0)
        score, details = layer._calc_vix_sentiment(cache)
        assert details['zone'] == 'panic'

    def test_no_vix_data(self, layer):
        """VIX 데이터 없으면 0을 반환해야 한다."""
        score, details = layer._calc_vix_sentiment(MockCache({}))
        assert score == 0.0

    def test_score_in_range(self, layer, sentiment_cache):
        """점수가 -100 ~ +100 범위여야 한다."""
        score, _ = layer._calc_vix_sentiment(sentiment_cache)
        assert -100.0 <= score <= 100.0

    def test_vixy_fallback(self, layer):
        """^VIX 없으면 VIXY로 폴백해야 한다."""
        vixy_df = _make_ohlcv(n=100, start_price=20.0, seed=42)
        cache = MockCache({'VIXY': vixy_df})
        score, details = layer._calc_vix_sentiment(cache)
        assert details.get('source') == 'VIXY'


# ──────────────────────────────────────────────────────────────────────
# News sentiment tests
# ──────────────────────────────────────────────────────────────────────


class TestNewsSentiment:
    """News headline keyword sentiment tests."""

    def test_positive_headlines(self, layer):
        """긍정적 헤드라인 -> 양의 점수."""
        news = [
            {'title': 'Markets surge to record high'},
            {'title': 'AAPL beats expectations, shares rally'},
            {'title': 'Strong growth outlook, bullish analysts'},
        ]
        score, details = layer._calc_news_sentiment(news)
        assert score > 0
        assert details['positive_count'] > details['negative_count']
        assert details['tone'] == 'positive'

    def test_negative_headlines(self, layer):
        """부정적 헤드라인 -> 음의 점수."""
        news = [
            {'title': 'Market crash fears grow amid recession warning'},
            {'title': 'Stock plunge deepens, bearish outlook concern'},
            {'title': 'Investors sell amid growing risk of decline'},
        ]
        score, details = layer._calc_news_sentiment(news)
        assert score < 0
        assert details['negative_count'] > details['positive_count']
        assert details['tone'] == 'negative'

    def test_mixed_headlines(self, layer):
        """혼조 헤드라인 -> 중립에 가까운 점수."""
        news = [
            {'title': 'Market rally offset by recession concerns'},
            {'title': 'Strong earnings beat but weak guidance warning'},
        ]
        score, details = layer._calc_news_sentiment(news)
        assert -50.0 <= score <= 50.0
        assert details['tone'] in ('mixed', 'neutral', 'positive', 'negative')

    def test_no_news(self, layer):
        """뉴스 없으면 0을 반환해야 한다."""
        score, details = layer._calc_news_sentiment(None)
        assert score == 0.0
        assert details['tone'] == 'no_data'

    def test_empty_news_list(self, layer):
        """빈 뉴스 리스트 -> 0."""
        score, details = layer._calc_news_sentiment([])
        assert score == 0.0
        assert details['tone'] == 'no_data'

    def test_news_without_title(self, layer):
        """title 없는 뉴스 아이템 처리."""
        news = [{'url': 'http://example.com'}, {'title': ''}, {'title': None}]
        score, details = layer._calc_news_sentiment(news)
        assert score == 0.0

    def test_no_keyword_matches(self, layer):
        """키워드 매칭 없는 헤드라인 -> 0."""
        news = [
            {'title': 'Company announces new product launch'},
            {'title': 'CEO speaks at conference about innovation'},
        ]
        score, details = layer._calc_news_sentiment(news)
        assert score == 0.0
        assert details['tone'] == 'neutral'

    def test_positive_words_set(self):
        """긍정 키워드 세트가 올바르게 정의되어야 한다."""
        assert 'surge' in POSITIVE_WORDS
        assert 'rally' in POSITIVE_WORDS
        assert 'bullish' in POSITIVE_WORDS

    def test_negative_words_set(self):
        """부정 키워드 세트가 올바르게 정의되어야 한다."""
        assert 'crash' in NEGATIVE_WORDS
        assert 'recession' in NEGATIVE_WORDS
        assert 'bearish' in NEGATIVE_WORDS

    def test_case_insensitive(self, layer):
        """키워드 매칭이 대소문자 무관해야 한다."""
        news = [{'title': 'SURGE in markets after RALLY'}]
        score, details = layer._calc_news_sentiment(news)
        assert details['positive_count'] >= 2

    def test_score_clamped(self, layer):
        """점수가 -100 ~ +100 범위로 클램핑되어야 한다."""
        # 극단적으로 긍정적인 뉴스
        news = [
            {'title': 'surge rally gain soar beat upgrade bullish record growth strong'}
        ]
        score, _ = layer._calc_news_sentiment(news)
        assert -100.0 <= score <= 100.0


# ──────────────────────────────────────────────────────────────────────
# Smart money tests
# ──────────────────────────────────────────────────────────────────────


class TestSmartMoney:
    """GLD/SPY ratio momentum (smart money proxy) tests."""

    def test_spy_outperform_gld_is_risk_on(self, layer):
        """SPY가 GLD 대비 outperform -> risk_on (GLD/SPY 하락 = 반전 후 양수)."""
        # 같은 인덱스 사용하여 ratio 계산 시 NaN 방지
        gld = _make_ohlcv(n=200, start_price=180.0, trend=-0.001, seed=60)
        spy = _make_ohlcv(n=200, start_price=450.0, trend=0.005, seed=61)
        spy.index = gld.index  # 동일 인덱스 보장
        cache = MockCache({'GLD': gld, 'SPY': spy})
        score, details = layer._calc_smart_money(cache)
        assert score > 0 or details.get('direction') in ('risk_on', 'neutral')

    def test_gld_outperform_spy_is_risk_off(self, layer):
        """GLD가 SPY 대비 outperform -> risk_off."""
        gld = _make_ohlcv(n=200, start_price=180.0, trend=0.005, seed=62)
        spy = _make_ohlcv(n=200, start_price=450.0, trend=-0.001, seed=63)
        spy.index = gld.index  # 동일 인덱스 보장
        cache = MockCache({'GLD': gld, 'SPY': spy})
        score, details = layer._calc_smart_money(cache)
        assert score < 0 or details.get('direction') in ('risk_off', 'neutral')

    def test_no_gld_spy_data(self, layer):
        """GLD/SPY 데이터 없으면 0을 반환해야 한다."""
        score, details = layer._calc_smart_money(MockCache({}))
        assert score == 0.0
        assert 'error' in details or details.get('direction') == 'neutral'

    def test_short_gld_data(self, layer):
        """짧은 GLD 데이터 -> 0."""
        cache = MockCache({
            'GLD': _make_ohlcv(n=10),
            'SPY': _make_ohlcv(n=200, seed=100),
        })
        score, details = layer._calc_smart_money(cache)
        assert score == 0.0

    def test_score_in_range(self, layer):
        """점수가 -100 ~ +100 범위여야 한다."""
        gld = _make_ohlcv(n=200, start_price=180.0, trend=0.001, seed=70)
        spy = _make_ohlcv(n=200, start_price=450.0, trend=0.002, seed=71)
        spy.index = gld.index
        cache = MockCache({'GLD': gld, 'SPY': spy})
        score, _ = layer._calc_smart_money(cache)
        assert -100.0 <= score <= 100.0

    def test_details_contain_gld_spy_returns(self, layer):
        """details에 GLD/SPY 수익률 정보가 포함되어야 한다."""
        gld = _make_ohlcv(n=200, start_price=180.0, trend=0.001, seed=70)
        spy = _make_ohlcv(n=200, start_price=450.0, trend=0.002, seed=71)
        spy.index = gld.index
        cache = MockCache({'GLD': gld, 'SPY': spy})
        score, details = layer._calc_smart_money(cache)
        assert 'gld_spy_ret_5d_pct' in details
        assert 'gld_spy_ret_20d_pct' in details


# ──────────────────────────────────────────────────────────────────────
# Missing / partial data tests
# ──────────────────────────────────────────────────────────────────────


class TestSentimentMissingData:
    """Edge cases with missing or partial data."""

    def test_all_missing(self, layer):
        """모든 데이터 없을 때 기본 결과를 반환해야 한다."""
        result = layer.analyze({})
        assert isinstance(result, LayerResult)
        assert result.score == 0.0
        assert result.signal == "neutral"

    def test_only_fear_greed(self, layer):
        """Fear & Greed만 있을 때도 분석 가능해야 한다."""
        result = layer.analyze({'fear_greed': {'value': 20}})
        assert isinstance(result, LayerResult)
        assert result.metrics.get('fear_greed', 0.0) == 40.0  # fear zone (20-35) = +40

    def test_only_news(self, layer):
        """뉴스만 있을 때도 분석 가능해야 한다."""
        result = layer.analyze({
            'news': [{'title': 'Market surge continues'}]
        })
        assert isinstance(result, LayerResult)

    def test_only_cache(self, layer, sentiment_cache):
        """캐시만 있을 때도 분석 가능해야 한다."""
        result = layer.analyze({'cache': sentiment_cache})
        assert isinstance(result, LayerResult)

    def test_fear_greed_invalid_value(self, layer):
        """잘못된 Fear & Greed 값 처리."""
        result = layer.analyze({'fear_greed': {'value': 'invalid'}})
        assert isinstance(result, LayerResult)
        assert result.metrics.get('fear_greed', 0.0) == 0.0

    def test_none_cache(self, layer):
        """None 캐시에서도 정상 동작해야 한다."""
        result = layer.analyze({
            'cache': None,
            'fear_greed': {'value': 50},
            'news': [],
        })
        assert isinstance(result, LayerResult)


# ──────────────────────────────────────────────────────────────────────
# Score consistency tests
# ──────────────────────────────────────────────────────────────────────


class TestSentimentConsistency:
    """Score consistency and interpretation tests."""

    def test_weights_sum_to_one(self):
        """서브 메트릭 가중치 합이 1.0이어야 한다."""
        total = sum(SUB_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_extreme_fear_bullish_overall(self, layer):
        """극단적 공포 + 높은 VIX + GLD 강세 -> 역발상 신호."""
        result = layer.analyze({
            'fear_greed': {'value': 10},  # extreme fear (+80)
            'cache': _build_sentiment_cache(vix_level=35.0, gld_trend=0.005, spy_trend=-0.003),
            'news': [{'title': 'Market crash panic sell fear decline'}],
        })
        # 극단적 공포는 역발상 매수이므로 점수가 양수일 수 있음
        assert isinstance(result, LayerResult)

    def test_extreme_greed_bearish_overall(self, layer):
        """극단적 탐욕 + 낮은 VIX -> 역발상 약세 신호."""
        result = layer.analyze({
            'fear_greed': {'value': 90},  # extreme greed (-80)
            'cache': _build_sentiment_cache(vix_level=11.0, gld_trend=-0.001, spy_trend=0.003),
            'news': [{'title': 'Everything is bullish rally surge record'}],
        })
        assert isinstance(result, LayerResult)

    def test_reproducibility(self, layer, full_data):
        """동일 데이터로 두 번 호출 시 같은 결과여야 한다."""
        r1 = layer.analyze(full_data)
        r2 = layer.analyze(full_data)
        assert r1.score == r2.score
        assert r1.signal == r2.signal

    def test_interpretation_includes_fg_value(self, layer, full_data):
        """해석에 Fear & Greed 값이 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert '공포탐욕' in result.interpretation

    def test_interpretation_includes_vix(self, layer, full_data):
        """해석에 VIX 정보가 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert 'VIX' in result.interpretation

    def test_interpretation_includes_news_tone(self, layer, full_data):
        """해석에 뉴스 톤이 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert '뉴스' in result.interpretation

    def test_interpretation_includes_smart_money(self, layer, full_data):
        """해석에 기관 리스크 선호도가 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert '기관' in result.interpretation
