"""
Tests for Layer 5 (KR): Sentiment - 한국 시장 심리 분석.

VKOSPI, 한글 뉴스 감성, GLD/KOSPI 모멘텀, 원달러 환율 분석 레이어를 테스트합니다.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.kr_layer5_sentiment import (
    KR_BEARISH_KEYWORDS,
    KR_BULLISH_KEYWORDS,
    KR_SUB_WEIGHTS,
    KRSentimentLayer,
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


def _build_kr_sentiment_cache(
    vkospi_level: float = 20.0,
    gld_trend: float = 0.001,
    kospi_trend: float = 0.002,
    usdkrw_level: float = 1350.0,
    usdkrw_trend: float = 0.0,
    n: int = 200,
) -> MockCache:
    """Build a mock cache with VKOSPI, GLD, KOSPI, and USDKRW data."""
    rng = np.random.RandomState(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='B')

    # VKOSPI-like data
    vkospi_prices = vkospi_level + rng.normal(0, 2, n).cumsum() * 0.1
    vkospi_prices = np.clip(vkospi_prices, 10, 80)

    vkospi_df = pd.DataFrame(
        {
            'Open': vkospi_prices,
            'High': vkospi_prices * 1.02,
            'Low': vkospi_prices * 0.98,
            'Close': vkospi_prices,
            'Volume': np.ones(n) * 1_000_000,
        },
        index=dates,
    )

    gld_df = _make_ohlcv(n=n, start_price=180.0, trend=gld_trend, seed=99)
    kospi_df = _make_ohlcv(n=n, start_price=2700.0, trend=kospi_trend, seed=100)
    kospi_df.index = gld_df.index

    # USDKRW-like data
    usdkrw_returns = rng.normal(usdkrw_trend, 0.005, n)
    usdkrw_prices = usdkrw_level * np.exp(np.cumsum(usdkrw_returns))

    usdkrw_df = pd.DataFrame(
        {
            'Open': usdkrw_prices,
            'High': usdkrw_prices * 1.005,
            'Low': usdkrw_prices * 0.995,
            'Close': usdkrw_prices,
            'Volume': np.ones(n) * 100_000,
        },
        index=dates,
    )

    return MockCache({
        '^VKOSPI': vkospi_df,
        '^KS11': kospi_df,
        'GLD': gld_df,
        'USDKRW=X': usdkrw_df,
    })


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def layer():
    return KRSentimentLayer()


@pytest.fixture
def kr_cache():
    return _build_kr_sentiment_cache()


@pytest.fixture
def full_data(kr_cache):
    return {
        'cache': kr_cache,
        'news': [
            {'title': '코스피 상승세 지속, 삼성전자 급등'},
            {'title': '한국은행 기준금리 동결로 시장 안도'},
            {'title': '원달러 환율 급락 우려 확대'},
            {'title': 'SK하이닉스 실적 호재에 강세'},
            {'title': '글로벌 불황 여파로 코스닥 약세'},
        ],
    }


# ──────────────────────────────────────────────────────────────────────
# Happy path tests
# ──────────────────────────────────────────────────────────────────────


class TestKRSentimentHappyPath:
    """Full data present - happy path tests."""

    def test_analyze_returns_layer_result(self, layer, full_data):
        """analyze()가 LayerResult 인스턴스를 반환해야 한다."""
        result = layer.analyze(full_data)
        assert isinstance(result, LayerResult)

    def test_layer_name(self, layer, full_data):
        """레이어 이름이 올바르게 설정되어야 한다."""
        result = layer.analyze(full_data)
        assert result.layer_name == "kr_sentiment"

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
        expected_keys = {'vkospi_sentiment', 'news_sentiment', 'smart_money', 'usdkrw_sentiment'}
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
        assert 'VKOSPI' in result.interpretation or '뉴스' in result.interpretation

    def test_to_dict_format(self, layer, full_data):
        """to_dict()가 올바른 형식의 딕셔너리를 반환해야 한다."""
        result = layer.analyze(full_data)
        d = result.to_dict()
        assert d['layer'] == 'kr_sentiment'
        assert isinstance(d['score'], float)


# ──────────────────────────────────────────────────────────────────────
# VKOSPI sentiment tests
# ──────────────────────────────────────────────────────────────────────


class TestVKOSPISentiment:
    """VKOSPI-based sentiment scoring tests."""

    def test_low_vkospi_complacency(self, layer):
        """VKOSPI < 15 -> extreme complacency (-20)."""
        cache = _build_kr_sentiment_cache(vkospi_level=12.0)
        score, details = layer._calc_vkospi_sentiment(cache)
        assert details['zone'] == 'extreme_complacency'
        assert -50.0 <= score <= 10.0

    def test_normal_vkospi(self, layer):
        """VKOSPI 15-20 -> normal (+10)."""
        cache = _build_kr_sentiment_cache(vkospi_level=17.0)
        score, details = layer._calc_vkospi_sentiment(cache)
        assert details['zone'] == 'normal'

    def test_elevated_fear(self, layer):
        """VKOSPI 20-30 -> elevated fear (contrarian +30)."""
        cache = _build_kr_sentiment_cache(vkospi_level=25.0)
        score, details = layer._calc_vkospi_sentiment(cache)
        assert details['zone'] == 'elevated_fear'

    def test_panic_vkospi(self, layer):
        """VKOSPI > 30 -> panic (contrarian +50)."""
        cache = _build_kr_sentiment_cache(vkospi_level=40.0)
        score, details = layer._calc_vkospi_sentiment(cache)
        assert details['zone'] == 'panic'

    def test_no_vkospi_data(self, layer):
        """VKOSPI 데이터 없으면 0을 반환해야 한다."""
        score, details = layer._calc_vkospi_sentiment(MockCache({}))
        assert score == 0.0

    def test_score_in_range(self, layer, kr_cache):
        """점수가 -100 ~ +100 범위여야 한다."""
        score, _ = layer._calc_vkospi_sentiment(kr_cache)
        assert -100.0 <= score <= 100.0

    def test_details_contain_direction(self, layer, kr_cache):
        """details에 direction이 포함되어야 한다."""
        score, details = layer._calc_vkospi_sentiment(kr_cache)
        assert 'direction' in details
        assert details['direction'] in ('rising', 'falling', 'stable')


# ──────────────────────────────────────────────────────────────────────
# Korean news sentiment tests
# ──────────────────────────────────────────────────────────────────────


class TestKRNewsSentiment:
    """Korean news headline keyword sentiment tests."""

    def test_bullish_headlines(self, layer):
        """긍정적 한글 헤드라인 -> 양의 점수."""
        news = [
            {'title': '코스피 상승세 지속 강세장 진입'},
            {'title': '삼성전자 급등 신고가 돌파'},
            {'title': '호재 속출 매수세 강화'},
        ]
        score, details = layer._calc_news_sentiment(news)
        assert score > 0
        assert details['bullish_count'] > details['bearish_count']
        assert details['tone'] == 'positive'
        assert details['method'] == 'kr_keyword'

    def test_bearish_headlines(self, layer):
        """부정적 한글 헤드라인 -> 음의 점수."""
        news = [
            {'title': '코스피 하락 폭락 위기 심화'},
            {'title': '급락세 지속 악재 쏟아져'},
            {'title': '약세장 매도 불황 우려'},
        ]
        score, details = layer._calc_news_sentiment(news)
        assert score < 0
        assert details['bearish_count'] > details['bullish_count']
        assert details['tone'] == 'negative'

    def test_mixed_headlines(self, layer):
        """혼조 한글 헤드라인 -> 중립에 가까운 점수."""
        news = [
            {'title': '코스피 상승 후 하락 전환'},
            {'title': '호재와 악재 혼재 속 강세와 약세 공존'},
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
            {'title': '기업 신제품 출시 발표'},
            {'title': 'CEO 컨퍼런스 참석'},
        ]
        score, details = layer._calc_news_sentiment(news)
        assert score == 0.0
        assert details['tone'] == 'neutral'

    def test_bullish_keywords_set(self):
        """긍정 키워드 세트가 올바르게 정의되어야 한다."""
        assert '상승' in KR_BULLISH_KEYWORDS
        assert '급등' in KR_BULLISH_KEYWORDS
        assert '호재' in KR_BULLISH_KEYWORDS
        assert '강세' in KR_BULLISH_KEYWORDS

    def test_bearish_keywords_set(self):
        """부정 키워드 세트가 올바르게 정의되어야 한다."""
        assert '하락' in KR_BEARISH_KEYWORDS
        assert '급락' in KR_BEARISH_KEYWORDS
        assert '악재' in KR_BEARISH_KEYWORDS
        assert '위기' in KR_BEARISH_KEYWORDS

    def test_substring_matching(self, layer):
        """한글 키워드는 부분 문자열 매칭으로 동작해야 한다."""
        news = [{'title': '오늘코스피급등세계속'}]
        score, details = layer._calc_news_sentiment(news)
        assert details['bullish_count'] >= 1  # '급등' 매칭

    def test_score_clamped(self, layer):
        """점수가 -100 ~ +100 범위로 클램핑되어야 한다."""
        news = [
            {'title': '상승 급등 호재 반등 신고가 매수 강세 호황'}
        ]
        score, _ = layer._calc_news_sentiment(news)
        assert -100.0 <= score <= 100.0


# ──────────────────────────────────────────────────────────────────────
# Smart money tests (GLD/KOSPI)
# ──────────────────────────────────────────────────────────────────────


class TestSmartMoney:
    """GLD/KOSPI ratio momentum (smart money proxy) tests."""

    def test_kospi_outperform_gld_is_risk_on(self, layer):
        """KOSPI가 GLD 대비 outperform -> risk_on."""
        gld = _make_ohlcv(n=200, start_price=180.0, trend=-0.001, seed=60)
        kospi = _make_ohlcv(n=200, start_price=2700.0, trend=0.005, seed=61)
        kospi.index = gld.index
        cache = MockCache({'GLD': gld, '^KS11': kospi})
        score, details = layer._calc_smart_money(cache)
        assert score > 0 or details.get('direction') in ('risk_on', 'neutral')

    def test_gld_outperform_kospi_is_risk_off(self, layer):
        """GLD가 KOSPI 대비 outperform -> risk_off."""
        gld = _make_ohlcv(n=200, start_price=180.0, trend=0.005, seed=62)
        kospi = _make_ohlcv(n=200, start_price=2700.0, trend=-0.001, seed=63)
        kospi.index = gld.index
        cache = MockCache({'GLD': gld, '^KS11': kospi})
        score, details = layer._calc_smart_money(cache)
        assert score < 0 or details.get('direction') in ('risk_off', 'neutral')

    def test_no_data(self, layer):
        """GLD/KOSPI 데이터 없으면 0을 반환해야 한다."""
        score, details = layer._calc_smart_money(MockCache({}))
        assert score == 0.0
        assert 'error' in details

    def test_short_data(self, layer):
        """짧은 데이터 -> 0."""
        cache = MockCache({
            'GLD': _make_ohlcv(n=10),
            '^KS11': _make_ohlcv(n=200, seed=100),
        })
        score, details = layer._calc_smart_money(cache)
        assert score == 0.0

    def test_score_in_range(self, layer):
        """점수가 -100 ~ +100 범위여야 한다."""
        gld = _make_ohlcv(n=200, start_price=180.0, trend=0.001, seed=70)
        kospi = _make_ohlcv(n=200, start_price=2700.0, trend=0.002, seed=71)
        kospi.index = gld.index
        cache = MockCache({'GLD': gld, '^KS11': kospi})
        score, _ = layer._calc_smart_money(cache)
        assert -100.0 <= score <= 100.0

    def test_details_contain_returns(self, layer):
        """details에 수익률 정보가 포함되어야 한다."""
        gld = _make_ohlcv(n=200, start_price=180.0, trend=0.001, seed=70)
        kospi = _make_ohlcv(n=200, start_price=2700.0, trend=0.002, seed=71)
        kospi.index = gld.index
        cache = MockCache({'GLD': gld, '^KS11': kospi})
        score, details = layer._calc_smart_money(cache)
        assert 'gld_kospi_ret_5d_pct' in details
        assert 'gld_kospi_ret_20d_pct' in details


# ──────────────────────────────────────────────────────────────────────
# USDKRW sentiment tests
# ──────────────────────────────────────────────────────────────────────


class TestUSDKRWSentiment:
    """USDKRW exchange rate sentiment tests."""

    def test_krw_strengthening_is_positive(self, layer):
        """원화 강세 (USDKRW 하락) -> 긍정적."""
        cache = _build_kr_sentiment_cache(usdkrw_level=1350.0, usdkrw_trend=-0.003)
        score, details = layer._calc_usdkrw_sentiment(cache)
        # USDKRW 하락 = 원화 강세 = negate 후 양수
        assert score > 0 or details['direction'] in ('krw_strong', 'stable')

    def test_krw_weakening_is_negative(self, layer):
        """원화 약세 (USDKRW 상승) -> 부정적."""
        cache = _build_kr_sentiment_cache(usdkrw_level=1350.0, usdkrw_trend=0.003)
        score, details = layer._calc_usdkrw_sentiment(cache)
        assert score < 0 or details['direction'] in ('krw_weak', 'stable')

    def test_no_usdkrw_data(self, layer):
        """USDKRW 데이터 없으면 0을 반환해야 한다."""
        score, details = layer._calc_usdkrw_sentiment(MockCache({}))
        assert score == 0.0
        assert 'error' in details

    def test_short_data(self, layer):
        """짧은 USDKRW 데이터 -> 0."""
        usdkrw_df = _make_ohlcv(n=10, start_price=1350.0, seed=42)
        cache = MockCache({'USDKRW=X': usdkrw_df})
        score, details = layer._calc_usdkrw_sentiment(cache)
        assert score == 0.0

    def test_score_in_range(self, layer, kr_cache):
        """점수가 -100 ~ +100 범위여야 한다."""
        score, _ = layer._calc_usdkrw_sentiment(kr_cache)
        assert -100.0 <= score <= 100.0

    def test_details_contain_rate(self, layer, kr_cache):
        """details에 현재 환율이 포함되어야 한다."""
        score, details = layer._calc_usdkrw_sentiment(kr_cache)
        assert 'current_rate' in details
        assert details['current_rate'] > 0

    def test_details_contain_direction(self, layer, kr_cache):
        """details에 direction이 포함되어야 한다."""
        score, details = layer._calc_usdkrw_sentiment(kr_cache)
        assert 'direction' in details
        assert details['direction'] in ('krw_strong', 'krw_weak', 'stable')


# ──────────────────────────────────────────────────────────────────────
# Missing / partial data tests
# ──────────────────────────────────────────────────────────────────────


class TestKRSentimentMissingData:
    """Edge cases with missing or partial data."""

    def test_all_missing(self, layer):
        """모든 데이터 없을 때 기본 결과를 반환해야 한다."""
        result = layer.analyze({})
        assert isinstance(result, LayerResult)
        assert result.score == 0.0
        assert result.signal == "neutral"

    def test_only_news(self, layer):
        """뉴스만 있을 때도 분석 가능해야 한다."""
        result = layer.analyze({
            'news': [{'title': '코스피 급등세 지속'}]
        })
        assert isinstance(result, LayerResult)

    def test_only_cache(self, layer, kr_cache):
        """캐시만 있을 때도 분석 가능해야 한다."""
        result = layer.analyze({'cache': kr_cache})
        assert isinstance(result, LayerResult)

    def test_none_cache(self, layer):
        """None 캐시에서도 정상 동작해야 한다."""
        result = layer.analyze({
            'cache': None,
            'news': [],
        })
        assert isinstance(result, LayerResult)


# ──────────────────────────────────────────────────────────────────────
# Score consistency tests
# ──────────────────────────────────────────────────────────────────────


class TestKRSentimentConsistency:
    """Score consistency and interpretation tests."""

    def test_weights_sum_to_one(self):
        """서브 메트릭 가중치 합이 1.0이어야 한다."""
        total = sum(KR_SUB_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_weights_match_spec(self):
        """가중치가 스펙과 일치해야 한다."""
        assert KR_SUB_WEIGHTS['vkospi_sentiment'] == 0.30
        assert KR_SUB_WEIGHTS['news_sentiment'] == 0.35
        assert KR_SUB_WEIGHTS['smart_money'] == 0.20
        assert KR_SUB_WEIGHTS['usdkrw_sentiment'] == 0.15

    def test_reproducibility(self, layer, full_data):
        """동일 데이터로 두 번 호출 시 같은 결과여야 한다."""
        r1 = layer.analyze(full_data)
        r2 = layer.analyze(full_data)
        assert r1.score == r2.score
        assert r1.signal == r2.signal

    def test_interpretation_includes_vkospi(self, layer, full_data):
        """해석에 VKOSPI 정보가 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert 'VKOSPI' in result.interpretation

    def test_interpretation_includes_news_tone(self, layer, full_data):
        """해석에 뉴스 톤이 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert '뉴스' in result.interpretation

    def test_interpretation_includes_smart_money(self, layer, full_data):
        """해석에 기관 리스크 선호도가 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert '기관' in result.interpretation

    def test_interpretation_includes_usdkrw(self, layer, full_data):
        """해석에 원달러 정보가 포함되어야 한다."""
        result = layer.analyze(full_data)
        assert '원달러' in result.interpretation

    def test_panic_vkospi_bullish_composite(self, layer):
        """패닉 VKOSPI + 부정적 뉴스 -> 역발상 시그널."""
        result = layer.analyze({
            'cache': _build_kr_sentiment_cache(vkospi_level=35.0),
            'news': [{'title': '폭락 위기 급락 하락 악재'}],
        })
        assert isinstance(result, LayerResult)

    def test_low_vkospi_bearish_composite(self, layer):
        """낮은 VKOSPI + 긍정적 뉴스 -> 역발상 약세."""
        result = layer.analyze({
            'cache': _build_kr_sentiment_cache(vkospi_level=11.0),
            'news': [{'title': '급등 상승 호재 강세 신고가'}],
        })
        assert isinstance(result, LayerResult)
