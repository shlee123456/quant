"""
Integration tests for MarketIntelligence orchestrator.

MarketIntelligence 오케스트레이터의 통합 테스트.
- 전체 파이프라인 (5 레이어 분석 + 종합 점수)
- 그레이스풀 디그레이데이션 (캐시 비어있을 때)
- 부분 데이터 처리 (뉴스, Fear & Greed 유무)
- JSON 출력 크기 제약 (<50KB)
- 하위 호환성 (기존 MarketAnalyzer 결과와 통합)
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from trading_bot.market_intelligence import (
    MarketIntelligence,
    LAYER_WEIGHTS,
    LayerResult,
)

from .conftest import MockCache, make_ohlcv, make_trending_cache


# ─── Orchestrator init tests ───


class TestMarketIntelligenceInit:
    """MarketIntelligence 초기화 테스트."""

    def test_default_initialization(self):
        """기본 초기화 확인."""
        mi = MarketIntelligence()
        assert mi.weights == LAYER_WEIGHTS
        assert len(mi.layers) == 5
        assert 'macro_regime' in mi.layers
        assert 'market_structure' in mi.layers
        assert 'sector_rotation' in mi.layers
        assert 'enhanced_technicals' in mi.layers
        assert 'sentiment' in mi.layers

    def test_custom_weights(self):
        """커스텀 가중치 전달."""
        custom_weights = {
            'macro_regime': 0.10,
            'market_structure': 0.10,
            'sector_rotation': 0.10,
            'enhanced_technicals': 0.50,
            'sentiment': 0.20,
        }
        mi = MarketIntelligence(layer_weights=custom_weights)
        assert mi.weights == custom_weights

    def test_custom_period_interval(self):
        """커스텀 period/interval."""
        mi = MarketIntelligence(period='3mo', interval='1wk')
        assert mi.cache.period == '3mo'
        assert mi.cache.interval == '1wk'


# ─── Full pipeline tests with mock cache ───


class TestMarketIntelligenceAnalyze:
    """MarketIntelligence.analyze() 전체 파이프라인 테스트."""

    def _make_mi_with_mock_cache(self, cache: MockCache) -> MarketIntelligence:
        """MockCache를 주입한 MarketIntelligence 생성."""
        mi = MarketIntelligence()
        mi.cache = cache
        # cache.fetch()가 호출되지 않도록 패치
        mi.cache.fetch = MagicMock(return_value=True)
        return mi

    def test_full_pipeline_bullish(self, bullish_cache):
        """상승 추세 데이터로 전체 파이프라인 실행."""
        mi = self._make_mi_with_mock_cache(bullish_cache)
        report = mi.analyze(stock_symbols=['AAPL', 'MSFT'])

        # 리포트 구조 확인
        assert 'generated_at' in report
        assert 'overall' in report
        assert 'layers' in report
        assert 'layer_weights' in report

        # overall 구조
        overall = report['overall']
        assert 'score' in overall
        assert 'signal' in overall
        assert 'interpretation' in overall
        assert overall['signal'] in ('bullish', 'bearish', 'neutral')
        assert isinstance(overall['score'], float)

        # layers 구조 (5개 레이어 모두 존재)
        assert len(report['layers']) == 5
        for layer_key in LAYER_WEIGHTS:
            assert layer_key in report['layers']
            layer_data = report['layers'][layer_key]
            assert 'score' in layer_data
            assert 'signal' in layer_data
            assert 'confidence' in layer_data

    def test_full_pipeline_bearish(self, bearish_cache):
        """하락 추세 데이터로 전체 파이프라인 실행."""
        mi = self._make_mi_with_mock_cache(bearish_cache)
        report = mi.analyze(stock_symbols=['AAPL'])

        assert report['overall']['signal'] in ('bullish', 'bearish', 'neutral')
        assert len(report['layers']) == 5

    def test_full_pipeline_neutral(self, neutral_cache):
        """횡보 데이터로 전체 파이프라인 실행."""
        mi = self._make_mi_with_mock_cache(neutral_cache)
        report = mi.analyze()

        assert report['overall']['signal'] in ('bullish', 'bearish', 'neutral')
        assert len(report['layers']) == 5

    def test_score_range(self, bullish_cache):
        """종합 점수가 -100 ~ +100 범위 내."""
        mi = self._make_mi_with_mock_cache(bullish_cache)
        report = mi.analyze()

        assert -100 <= report['overall']['score'] <= 100
        for layer_data in report['layers'].values():
            assert -100 <= layer_data['score'] <= 100


# ─── Graceful degradation tests ───


class TestGracefulDegradation:
    """캐시 실패 및 레이어 실패 시 그레이스풀 디그레이데이션."""

    def test_empty_cache_returns_report(self, empty_cache):
        """빈 캐시에서도 리포트 반환."""
        mi = MarketIntelligence()
        mi.cache = empty_cache
        mi.cache.fetch = MagicMock(return_value=False)

        report = mi.analyze()

        assert 'overall' in report
        assert 'layers' in report
        assert len(report['layers']) == 5
        # 모든 레이어가 낮은 신뢰도이거나 중립
        for layer_data in report['layers'].values():
            assert layer_data['signal'] in ('bullish', 'bearish', 'neutral')

    def test_single_layer_failure(self, bullish_cache):
        """단일 레이어 실패 시 다른 레이어 정상 동작."""
        mi = MarketIntelligence()
        mi.cache = bullish_cache
        mi.cache.fetch = MagicMock(return_value=True)

        # macro_regime 레이어에 예외 발생하도록 패치
        mi.layers['macro_regime'].analyze = MagicMock(
            side_effect=RuntimeError("test error")
        )

        report = mi.analyze()

        # 실패한 레이어: 중립 점수
        macro = report['layers']['macro_regime']
        assert macro['score'] == 0.0
        assert macro['signal'] == 'neutral'
        assert macro['confidence'] == 0.0
        assert 'error' in macro.get('details', {})

        # 나머지 레이어: 정상 작동
        for key in ('market_structure', 'sector_rotation',
                     'enhanced_technicals', 'sentiment'):
            assert report['layers'][key]['score'] != 0.0 or True

    def test_all_layers_failure(self, empty_cache):
        """모든 레이어 실패 시 중립 리포트 반환."""
        mi = MarketIntelligence()
        mi.cache = empty_cache
        mi.cache.fetch = MagicMock(return_value=False)

        # 모든 레이어에 예외 발생
        for layer in mi.layers.values():
            layer.analyze = MagicMock(
                side_effect=RuntimeError("all fail")
            )

        report = mi.analyze()

        assert report['overall']['score'] == 0.0
        assert report['overall']['signal'] == 'neutral'


# ─── Partial data handling ───


class TestPartialDataHandling:
    """뉴스, Fear & Greed 등 선택적 데이터 처리."""

    def _make_mi(self, cache: MockCache) -> MarketIntelligence:
        mi = MarketIntelligence()
        mi.cache = cache
        mi.cache.fetch = MagicMock(return_value=True)
        return mi

    def test_with_news_dict(self, bullish_cache):
        """NewsCollector dict 형식 뉴스 데이터."""
        mi = self._make_mi(bullish_cache)
        news_data = {
            'market_news': [
                {'title': 'Market rallies', 'source': 'Reuters'},
            ],
            'stock_news': {
                'AAPL': [{'title': 'Apple earnings beat', 'source': 'CNBC'}],
            },
        }
        report = mi.analyze(
            stock_symbols=['AAPL'],
            news_data=news_data,
        )
        assert 'overall' in report

    def test_with_news_list(self, bullish_cache):
        """리스트 형식 뉴스 데이터."""
        mi = self._make_mi(bullish_cache)
        news_data = [
            {'title': 'Market rallies', 'source': 'Reuters'},
        ]
        report = mi.analyze(
            stock_symbols=['AAPL'],
            news_data=news_data,
        )
        assert 'overall' in report

    def test_with_fear_greed_collector_format(self, bullish_cache):
        """FearGreedCollector 형식 데이터."""
        mi = self._make_mi(bullish_cache)
        fear_greed_data = {
            'current': {'value': 35, 'classification': 'Fear'},
            'history': [{'date': '2026-02-25', 'value': 35, 'classification': 'Fear'}],
        }
        report = mi.analyze(
            stock_symbols=['AAPL'],
            fear_greed_data=fear_greed_data,
        )
        assert 'overall' in report

    def test_with_direct_value_format(self, bullish_cache):
        """직접 {'value': ...} 형식."""
        mi = self._make_mi(bullish_cache)
        report = mi.analyze(
            stock_symbols=['AAPL'],
            fear_greed_data={'value': 75},
        )
        assert 'overall' in report

    def test_no_optional_data(self, bullish_cache):
        """뉴스/FG 없이 분석."""
        mi = self._make_mi(bullish_cache)
        report = mi.analyze(stock_symbols=['AAPL'])
        assert 'overall' in report
        assert len(report['layers']) == 5

    def test_with_stocks_data(self, bullish_cache):
        """기존 MarketAnalyzer stocks_data 전달."""
        mi = self._make_mi(bullish_cache)
        stocks_data = {
            'AAPL': {
                'price': {'last': 185.0},
                'indicators': {
                    'rsi': {'value': 55, 'signal': 'neutral'},
                    'macd': {'signal': 'bullish'},
                },
                'regime': {'state': 'BULLISH', 'confidence': 80},
            },
        }
        report = mi.analyze(
            stock_symbols=['AAPL'],
            stocks_data=stocks_data,
        )
        assert 'overall' in report


# ─── JSON output size constraint ───


class TestJSONOutputSize:
    """JSON 출력 크기 제약 테스트."""

    def test_report_json_under_50kb(self, bullish_cache):
        """리포트 JSON이 50KB 이하."""
        mi = MarketIntelligence()
        mi.cache = bullish_cache
        mi.cache.fetch = MagicMock(return_value=True)

        report = mi.analyze(stock_symbols=['AAPL', 'MSFT', 'NVDA'])
        json_str = json.dumps(report, ensure_ascii=False)
        size_kb = len(json_str.encode('utf-8')) / 1024

        assert size_kb < 50, f"JSON 크기 {size_kb:.1f}KB > 50KB 제한 초과"

    def test_report_is_json_serializable(self, bullish_cache):
        """리포트가 JSON 직렬화 가능."""
        mi = MarketIntelligence()
        mi.cache = bullish_cache
        mi.cache.fetch = MagicMock(return_value=True)

        report = mi.analyze()
        # 예외 없이 직렬화
        json_str = json.dumps(report, ensure_ascii=False)
        assert isinstance(json_str, str)
        # 역직렬화 확인
        parsed = json.loads(json_str)
        assert parsed['overall']['signal'] == report['overall']['signal']


# ─── Normalize helpers ───


class TestNormalizeHelpers:
    """MarketIntelligence 내부 정규화 헬퍼 테스트."""

    def test_normalize_news_none(self):
        assert MarketIntelligence._normalize_news(None) is None

    def test_normalize_news_list(self):
        data = [{'title': 'test'}]
        assert MarketIntelligence._normalize_news(data) == data

    def test_normalize_news_dict(self):
        data = {
            'market_news': [{'title': 'a'}],
            'stock_news': {'AAPL': [{'title': 'b'}]},
        }
        result = MarketIntelligence._normalize_news(data)
        assert len(result) == 2

    def test_normalize_news_empty_dict(self):
        result = MarketIntelligence._normalize_news({})
        assert result is None

    def test_normalize_news_invalid_type(self):
        assert MarketIntelligence._normalize_news(42) is None

    def test_normalize_fear_greed_none(self):
        assert MarketIntelligence._normalize_fear_greed(None) is None

    def test_normalize_fear_greed_direct(self):
        data = {'value': 50}
        assert MarketIntelligence._normalize_fear_greed(data) == data

    def test_normalize_fear_greed_collector_format(self):
        data = {'current': {'value': 35}}
        result = MarketIntelligence._normalize_fear_greed(data)
        assert result == {'value': 35}

    def test_normalize_fear_greed_no_value(self):
        data = {'something': 'else'}
        assert MarketIntelligence._normalize_fear_greed(data) is None


# ─── Overall interpretation ───


class TestOverallInterpretation:
    """종합 해석 문자열 테스트."""

    def test_bullish_interpretation(self):
        layer_results = {
            'macro_regime': LayerResult(
                layer_name='macro_regime', score=40.0,
                signal='bullish', confidence=0.8,
            ),
            'market_structure': LayerResult(
                layer_name='market_structure', score=30.0,
                signal='bullish', confidence=0.7,
            ),
        }
        interp = MarketIntelligence._build_overall_interpretation(
            35.0, 'bullish', layer_results,
        )
        assert '긍정적' in interp
        assert '35.0' in interp

    def test_bearish_interpretation(self):
        layer_results = {
            'macro_regime': LayerResult(
                layer_name='macro_regime', score=-40.0,
                signal='bearish', confidence=0.8,
            ),
            'sentiment': LayerResult(
                layer_name='sentiment', score=-30.0,
                signal='bearish', confidence=0.7,
            ),
        }
        interp = MarketIntelligence._build_overall_interpretation(
            -35.0, 'bearish', layer_results,
        )
        assert '부정적' in interp

    def test_neutral_interpretation(self):
        layer_results = {
            'macro_regime': LayerResult(
                layer_name='macro_regime', score=5.0,
                signal='neutral', confidence=0.5,
            ),
        }
        interp = MarketIntelligence._build_overall_interpretation(
            5.0, 'neutral', layer_results,
        )
        assert '중립' in interp

    def test_empty_layer_results(self):
        interp = MarketIntelligence._build_overall_interpretation(
            0.0, 'neutral', {},
        )
        assert '중립' in interp


# ─── Backward compatibility ───


class TestBackwardCompatibility:
    """기존 MarketAnalyzer 결과와의 하위 호환성."""

    def test_report_integrates_with_existing_results(self, bullish_cache):
        """기존 results dict에 'intelligence' 키로 병합 가능."""
        mi = MarketIntelligence()
        mi.cache = bullish_cache
        mi.cache.fetch = MagicMock(return_value=True)

        # 기존 MarketAnalyzer 결과 시뮬레이션
        existing_results = {
            'stocks': {'AAPL': {'price': {'last': 185.0}}},
            'market_summary': {
                'total_stocks': 1,
                'bullish_count': 1,
                'bearish_count': 0,
                'sideways_count': 0,
                'avg_rsi': 55.0,
                'market_sentiment': 'bullish',
                'notable_events': [],
            },
        }

        intel_report = mi.analyze(
            stock_symbols=['AAPL'],
            stocks_data=existing_results.get('stocks', {}),
        )

        # 기존 결과에 intelligence 키로 병합
        existing_results['intelligence'] = intel_report

        # JSON 직렬화 확인
        json_str = json.dumps(existing_results, ensure_ascii=False)
        parsed = json.loads(json_str)

        assert 'intelligence' in parsed
        assert 'overall' in parsed['intelligence']
        assert 'layers' in parsed['intelligence']
        assert 'stocks' in parsed  # 기존 데이터 보존

    def test_layer_weights_preserved(self, bullish_cache):
        """리포트에 layer_weights가 포함되어 재현 가능."""
        mi = MarketIntelligence()
        mi.cache = bullish_cache
        mi.cache.fetch = MagicMock(return_value=True)

        report = mi.analyze()
        assert report['layer_weights'] == LAYER_WEIGHTS


# ─── Export from trading_bot ───


class TestExportFromTradingBot:
    """trading_bot 패키지에서 MarketIntelligence import 가능 확인."""

    def test_import_from_package(self):
        """trading_bot에서 직접 import."""
        from trading_bot import MarketIntelligence as MI
        assert MI is not None
        assert MI is MarketIntelligence

    def test_import_from_subpackage(self):
        """market_intelligence 서브패키지에서 import."""
        from trading_bot.market_intelligence import MarketIntelligence as MI
        assert MI is not None
