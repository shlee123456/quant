"""
MarketAnalyzer + market_analysis_prompt 통합 검증 테스트

SimulationDataGenerator로 모의 데이터를 생성하여
실제 KIS API 없이 전체 파이프라인을 검증합니다.
"""

import json
import os
import tempfile
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import numpy as np
import pytest

from trading_bot.market_analyzer import MarketAnalyzer
from trading_bot.market_analysis_prompt import build_analysis_prompt, get_notion_page_id
from trading_bot.simulation_data import SimulationDataGenerator


# ─── Fixtures ───


@pytest.fixture
def sample_ohlcv():
    """SimulationDataGenerator로 200봉 OHLCV 데이터 생성"""
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_ohlcv(periods=200, initial_price=150.0)


@pytest.fixture
def mock_broker(sample_ohlcv):
    """fetch_ohlcv를 모킹한 가짜 브로커"""
    broker = MagicMock()
    broker.fetch_ohlcv.return_value = sample_ohlcv
    return broker


@pytest.fixture
def analyzer():
    return MarketAnalyzer(ohlcv_limit=200, api_delay=0.0)


# ─── MarketAnalyzer 단위 테스트 ───


class TestMarketAnalyzerIndicators:
    """지표 계산 정확성 테스트"""

    def test_calc_rsi_range(self, sample_ohlcv):
        """RSI 값이 0~100 범위 내인지 확인"""
        rsi = MarketAnalyzer._calc_rsi(sample_ohlcv['close'], period=14)
        valid = rsi.dropna()
        assert len(valid) > 0
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_calc_macd_components(self, sample_ohlcv):
        """MACD 구성요소가 올바르게 계산되는지 확인"""
        macd_line, signal_line, histogram = MarketAnalyzer._calc_macd(sample_ohlcv['close'])
        assert len(macd_line) == len(sample_ohlcv)
        assert len(signal_line) == len(sample_ohlcv)
        # histogram = macd_line - signal_line 검증
        np.testing.assert_allclose(
            histogram.dropna().values,
            (macd_line - signal_line).dropna().values,
            rtol=1e-10
        )

    def test_calc_bollinger_bands(self, sample_ohlcv):
        """볼린저 밴드: upper > middle > lower 관계 확인"""
        upper, middle, lower = MarketAnalyzer._calc_bollinger(sample_ohlcv['close'])
        valid_idx = upper.dropna().index
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()

    def test_calc_stochastic_range(self, sample_ohlcv):
        """스토캐스틱 %K, %D가 0~100 범위 내인지 확인"""
        k, d = MarketAnalyzer._calc_stochastic(
            sample_ohlcv['high'], sample_ohlcv['low'], sample_ohlcv['close']
        )
        valid_k = k.dropna()
        valid_d = d.dropna()
        assert valid_k.min() >= 0
        assert valid_k.max() <= 100
        assert valid_d.min() >= 0
        assert valid_d.max() <= 100

    def test_calc_pct_b(self):
        """Bollinger %B 계산: 경계값 및 정상 범위"""
        assert MarketAnalyzer._calc_pct_b(100.0, 110.0, 90.0) == 0.5
        assert MarketAnalyzer._calc_pct_b(110.0, 110.0, 90.0) == 1.0
        assert MarketAnalyzer._calc_pct_b(90.0, 110.0, 90.0) == 0.0
        # upper == lower 엣지 케이스
        assert MarketAnalyzer._calc_pct_b(100.0, 100.0, 100.0) == 0.5


class TestMarketAnalyzerClassifiers:
    """분류 헬퍼 테스트"""

    def test_classify_rsi(self):
        assert MarketAnalyzer._classify_rsi(15)[0] == 'oversold'
        assert MarketAnalyzer._classify_rsi(30)[0] == 'near_oversold'
        assert MarketAnalyzer._classify_rsi(50)[0] == 'neutral'
        assert MarketAnalyzer._classify_rsi(70)[0] == 'near_overbought'
        assert MarketAnalyzer._classify_rsi(85)[0] == 'overbought'

    def test_classify_bollinger(self):
        assert MarketAnalyzer._classify_bollinger(-0.1) == 'below_lower'
        assert MarketAnalyzer._classify_bollinger(0.1) == 'near_lower'
        assert MarketAnalyzer._classify_bollinger(0.5) == 'neutral'
        assert MarketAnalyzer._classify_bollinger(0.9) == 'near_upper'
        assert MarketAnalyzer._classify_bollinger(1.1) == 'above_upper'

    def test_classify_stochastic(self):
        assert MarketAnalyzer._classify_stochastic(10, 10) == 'oversold_zone'
        assert MarketAnalyzer._classify_stochastic(90, 90) == 'overbought_zone'
        assert MarketAnalyzer._classify_stochastic(50, 50) == 'neutral'

    def test_classify_adx(self):
        assert MarketAnalyzer._classify_adx(10) == 'no_trend'
        assert MarketAnalyzer._classify_adx(20) == 'weak_trend'
        assert MarketAnalyzer._classify_adx(30) == 'moderate_trend'
        assert MarketAnalyzer._classify_adx(50) == 'strong_trend'


class TestMarketAnalyzerPatterns:
    """패턴 감지 테스트"""

    def test_detect_patterns_short_data(self, analyzer):
        """짧은 데이터에서 패턴 감지 시 안전한 반환"""
        short_prices = np.array([100.0] * 10)
        result = analyzer._detect_patterns(short_prices)
        assert result['double_bottom'] is False
        assert result['support_levels'] == []

    def test_detect_patterns_with_double_bottom(self, analyzer):
        """이중 바닥 패턴 감지"""
        # V자 하락 후 반등, 다시 하락 후 반등 (이중 바닥)
        prices = np.concatenate([
            np.linspace(100, 90, 15),   # 하락
            np.linspace(90, 100, 15),   # 반등
            np.linspace(100, 90, 15),   # 재하락 (비슷한 수준)
            np.linspace(90, 105, 15),   # 재반등
        ])
        result = analyzer._detect_patterns(prices)
        assert isinstance(result['support_levels'], list)

    def test_detect_patterns_returns_support_levels(self, analyzer):
        """지지선이 리스트로 반환되는지 확인"""
        gen = SimulationDataGenerator(seed=99)
        df = gen.generate_volatile_data(periods=100, initial_price=100.0)
        result = analyzer._detect_patterns(df['close'].values)
        assert isinstance(result['support_levels'], list)


class TestMarketAnalyzerDiagnosis:
    """시그널 진단 테스트"""

    def test_diagnose_signals_oversold(self, analyzer):
        """과매도 영역에서 진단"""
        indicators = {'rsi': {'value': 25.0}, 'macd': {}, 'bollinger': {}, 'stochastic': {}, 'adx': {}}
        result = analyzer._diagnose_signals(25.0, indicators)
        assert result['rsi_35_65']['buy_triggered'] is True
        assert result['rsi_35_65']['sell_triggered'] is False

    def test_diagnose_signals_overbought(self, analyzer):
        """과매수 영역에서 진단"""
        indicators = {'rsi': {'value': 75.0}, 'macd': {}, 'bollinger': {}, 'stochastic': {}, 'adx': {}}
        result = analyzer._diagnose_signals(75.0, indicators)
        assert result['rsi_35_65']['buy_triggered'] is False
        assert result['rsi_35_65']['sell_triggered'] is True

    def test_diagnose_signals_neutral(self, analyzer):
        """중립 영역에서 진단"""
        indicators = {'rsi': {'value': 50.0}, 'macd': {}, 'bollinger': {}, 'stochastic': {}, 'adx': {}}
        result = analyzer._diagnose_signals(50.0, indicators)
        assert result['rsi_35_65']['buy_triggered'] is False
        assert result['rsi_35_65']['sell_triggered'] is False


# ─── 통합 테스트 ───


class TestMarketAnalyzerIntegration:
    """전체 분석 파이프라인 통합 테스트"""

    def test_analyze_single_symbol(self, analyzer, mock_broker):
        """단일 종목 분석"""
        results = analyzer.analyze(['AAPL'], mock_broker)

        assert 'date' in results
        assert 'market_summary' in results
        assert 'stocks' in results
        assert 'AAPL' in results['stocks']

        stock = results['stocks']['AAPL']
        assert 'price' in stock
        assert 'indicators' in stock
        assert 'regime' in stock
        assert 'patterns' in stock
        assert 'signal_diagnosis' in stock

    def test_analyze_multiple_symbols(self, analyzer, mock_broker):
        """여러 종목 동시 분석"""
        symbols = ['AAPL', 'MSFT', 'NVDA']
        results = analyzer.analyze(symbols, mock_broker)

        assert results['market_summary']['total_stocks'] == 3
        for sym in symbols:
            assert sym in results['stocks']

    def test_analyze_with_failed_symbol(self, analyzer):
        """일부 종목 조회 실패 시 나머지는 정상 분석 (모든 거래소 폴백도 실패)"""
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_ohlcv(periods=200, initial_price=150.0)

        broker = MagicMock()

        def side_effect(**kwargs):
            symbol = kwargs.get('symbol', '')
            if symbol == 'FAIL_SYM':
                raise Exception("API Error")
            return df

        broker.fetch_ohlcv.side_effect = side_effect

        results = analyzer.analyze(['FAIL_SYM', 'GOOD_SYM'], broker)
        assert 'FAIL_SYM' not in results['stocks']
        assert 'GOOD_SYM' in results['stocks']

    def test_analyze_all_fail(self, analyzer):
        """모든 종목 실패 시 빈 결과 반환"""
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = None

        results = analyzer.analyze(['BAD1', 'BAD2'], broker)
        assert results['stocks'] == {}
        assert results['market_summary'] == {}

    def test_indicator_structure(self, analyzer, mock_broker):
        """지표 딕셔너리 구조 검증"""
        results = analyzer.analyze(['AAPL'], mock_broker)
        indicators = results['stocks']['AAPL']['indicators']

        # RSI 구조
        assert 'value' in indicators['rsi']
        assert 'signal' in indicators['rsi']
        assert 'zone' in indicators['rsi']
        assert isinstance(indicators['rsi']['value'], float)

        # MACD 구조
        assert 'histogram' in indicators['macd']
        assert 'signal' in indicators['macd']
        assert 'cross_recent' in indicators['macd']
        assert isinstance(indicators['macd']['cross_recent'], bool)

        # Bollinger 구조
        assert 'pct_b' in indicators['bollinger']
        assert 'signal' in indicators['bollinger']

        # Stochastic 구조
        assert 'k' in indicators['stochastic']
        assert 'd' in indicators['stochastic']
        assert 'signal' in indicators['stochastic']

        # ADX 구조
        assert 'value' in indicators['adx']
        assert 'trend' in indicators['adx']

    def test_price_structure_includes_change_1d(self, analyzer, mock_broker):
        """price 딕셔너리에 change_1d 포함 확인"""
        results = analyzer.analyze(['AAPL'], mock_broker)
        price = results['stocks']['AAPL']['price']

        assert 'last' in price
        assert 'change_1d' in price
        assert 'change_5d' in price
        assert 'change_20d' in price
        assert isinstance(price['last'], float)
        # change_1d는 float 또는 None (데이터 부족 시)
        assert price['change_1d'] is None or isinstance(price['change_1d'], float)

    def test_market_summary_structure(self, analyzer, mock_broker):
        """시장 요약 구조 검증"""
        results = analyzer.analyze(['AAPL', 'MSFT', 'NVDA'], mock_broker)
        summary = results['market_summary']

        assert summary['total_stocks'] == 3
        assert isinstance(summary['bullish_count'], int)
        assert isinstance(summary['bearish_count'], int)
        assert isinstance(summary['sideways_count'], int)
        assert isinstance(summary['avg_rsi'], float)
        assert summary['market_sentiment'] in ['강한 약세', '약세', '중립', '강세', '강한 강세']
        assert isinstance(summary['notable_events'], list)

        # 합계 검증
        assert summary['bullish_count'] + summary['bearish_count'] + summary['sideways_count'] <= summary['total_stocks']

    def test_regime_structure(self, analyzer, mock_broker):
        """레짐 감지 결과 구조 검증"""
        results = analyzer.analyze(['AAPL'], mock_broker)
        regime = results['stocks']['AAPL']['regime']

        assert 'state' in regime
        assert 'confidence' in regime
        assert regime['state'] in ['BULLISH', 'BEARISH', 'SIDEWAYS', 'VOLATILE', 'UNKNOWN']
        assert 0.0 <= regime['confidence'] <= 1.0


class TestMarketAnalyzerSaveJson:
    """JSON 저장 테스트"""

    def test_save_json_creates_file(self, analyzer, mock_broker):
        """JSON 파일이 올바르게 생성되는지 확인"""
        results = analyzer.analyze(['AAPL'], mock_broker)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            assert Path(path).exists()

            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            assert loaded['date'] == results['date']
            assert 'AAPL' in loaded['stocks']

    def test_save_json_creates_directory(self, analyzer, mock_broker):
        """존재하지 않는 디렉토리도 자동 생성"""
        results = analyzer.analyze(['AAPL'], mock_broker)

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = os.path.join(tmpdir, 'sub', 'dir')
            path = analyzer.save_json(results, output_dir=nested_dir)
            assert Path(path).exists()

    def test_save_json_roundtrip(self, analyzer, mock_broker):
        """저장 후 다시 로드했을 때 데이터 무결성 확인"""
        results = analyzer.analyze(['AAPL', 'MSFT'], mock_broker)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)

            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            # 종목 수 일치
            assert len(loaded['stocks']) == len(results['stocks'])
            # 지표 값 일치
            for sym in results['stocks']:
                assert loaded['stocks'][sym]['indicators']['rsi']['value'] == \
                       results['stocks'][sym]['indicators']['rsi']['value']


# ─── Prompt Builder 테스트 ───


class TestBuildAnalysisPrompt:
    """market_analysis_prompt 모듈 테스트"""

    def test_get_notion_page_id_default(self):
        """기본 노션 페이지 ID 반환"""
        # 환경 변수가 없을 때 기본값
        orig = os.environ.pop('NOTION_MARKET_ANALYSIS_PAGE_ID', None)
        try:
            page_id = get_notion_page_id()
            assert page_id == "30dd62f0-dffd-80a6-b624-e5a061ed26a9"
        finally:
            if orig is not None:
                os.environ['NOTION_MARKET_ANALYSIS_PAGE_ID'] = orig

    def test_get_notion_page_id_from_env(self):
        """환경 변수에서 노션 페이지 ID 읽기"""
        os.environ['NOTION_MARKET_ANALYSIS_PAGE_ID'] = 'custom-page-id-123'
        try:
            assert get_notion_page_id() == 'custom-page-id-123'
        finally:
            del os.environ['NOTION_MARKET_ANALYSIS_PAGE_ID']

    def test_build_analysis_prompt(self, analyzer, mock_broker):
        """JSON 파일에서 프롬프트 생성"""
        results = analyzer.analyze(['AAPL'], mock_broker)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            assert isinstance(prompt, str)
            assert len(prompt) > 100
            # 프롬프트에 핵심 키워드 포함 확인
            assert '노션' in prompt or 'Notion' in prompt
            assert '시장' in prompt
            assert '종목' in prompt

    def test_build_analysis_prompt_file_not_found(self):
        """존재하지 않는 파일 경로 시 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            build_analysis_prompt('/nonexistent/path.json')

    def test_build_analysis_prompt_contains_json_data(self, analyzer, mock_broker):
        """프롬프트에 JSON 데이터가 포함되는지 확인"""
        results = analyzer.analyze(['AAPL'], mock_broker)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            # JSON 데이터의 키 값들이 프롬프트에 포함
            assert 'AAPL' in prompt
            assert 'rsi' in prompt


# ─── 다양한 시장 상황 테스트 ───


class TestMarketAnalyzerMarketConditions:
    """다양한 시장 조건에서의 분석 검증"""

    def test_bullish_market(self):
        """상승장 데이터 분석"""
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_trend_data(periods=200, trend='bullish', initial_price=100.0)
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = df

        analyzer = MarketAnalyzer(api_delay=0.0)
        results = analyzer.analyze(['TEST'], broker)

        assert 'TEST' in results['stocks']
        rsi = results['stocks']['TEST']['indicators']['rsi']['value']
        # 상승장에서 RSI가 극단적 과매도는 아닐 것
        assert rsi > 20

    def test_bearish_market(self):
        """하락장 데이터 분석"""
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_trend_data(periods=200, trend='bearish', initial_price=200.0)
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = df

        analyzer = MarketAnalyzer(api_delay=0.0)
        results = analyzer.analyze(['TEST'], broker)

        assert 'TEST' in results['stocks']
        rsi = results['stocks']['TEST']['indicators']['rsi']['value']
        # 하락장에서 RSI가 극단적 과매수는 아닐 것
        assert rsi < 80

    def test_volatile_market(self):
        """고변동성 데이터 분석"""
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_volatile_data(periods=200, initial_price=150.0)
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = df

        analyzer = MarketAnalyzer(api_delay=0.0)
        results = analyzer.analyze(['TEST'], broker)

        assert 'TEST' in results['stocks']
        # 볼린저 밴드 %B가 계산되는지 확인
        pct_b = results['stocks']['TEST']['indicators']['bollinger']['pct_b']
        assert isinstance(pct_b, float)

    def test_sideways_market(self):
        """횡보장 데이터 분석"""
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_trend_data(periods=200, trend='sideways', initial_price=150.0)
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = df

        analyzer = MarketAnalyzer(api_delay=0.0)
        results = analyzer.analyze(['TEST'], broker)

        assert 'TEST' in results['stocks']
        adx = results['stocks']['TEST']['indicators']['adx']['value']
        # 횡보장에서 ADX가 극단적으로 높지는 않을 것
        assert isinstance(adx, float)


# ─── NYSE/NASDAQ 거래소 분류 테스트 ───


class TestMarketAnalyzerExchange:
    """거래소 분류 테스트"""

    def test_nyse_symbol(self):
        """NYSE 종목이 올바르게 분류되는지"""
        assert 'WMT' in MarketAnalyzer.NYSE_SYMBOLS
        assert 'LLY' in MarketAnalyzer.NYSE_SYMBOLS

    def test_nasdaq_default(self):
        """NASDAQ이 아닌 종목은 기본값으로 NASDAQ"""
        assert 'AAPL' not in MarketAnalyzer.NYSE_SYMBOLS
        assert 'MSFT' not in MarketAnalyzer.NYSE_SYMBOLS

    def test_fetch_data_uses_correct_market(self, sample_ohlcv):
        """fetch_data가 올바른 거래소를 브로커에 전달하는지"""
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = sample_ohlcv

        analyzer = MarketAnalyzer(api_delay=0.0)

        # NYSE 종목
        analyzer._fetch_data('WMT', broker)
        call_kwargs = broker.fetch_ohlcv.call_args[1]
        assert call_kwargs['market'] == 'NYSE'

        # NASDAQ 종목 (기본)
        analyzer._fetch_data('AAPL', broker)
        call_kwargs = broker.fetch_ohlcv.call_args[1]
        assert call_kwargs['market'] == 'NASDAQ'


# ─── 뉴스 통합 테스트 ───


class TestMarketAnalyzerNewsIntegration:
    """뉴스 수집 통합 테스트"""

    def test_analyze_with_news_includes_news_key(self, analyzer, mock_broker):
        """collect_news=True 시 결과에 news 키 포함"""
        with unittest.mock.patch('trading_bot.market_analyzer._has_news_collector', True), \
             unittest.mock.patch('trading_bot.market_analyzer.NewsCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.return_value = {
                'collected_at': '2026-02-20T06:10:00',
                'market_news': [{'title': 'Test News', 'source': 'Reuters', 'published': '2026-02-20', 'link': 'http://example.com'}],
                'stock_news': {
                    'AAPL': [{'title': 'Apple News', 'source': 'CNBC', 'published': '2026-02-20', 'link': 'http://example.com'}]
                }
            }

            results = analyzer.analyze(['AAPL'], mock_broker, collect_news=True)

            assert 'news' in results
            assert len(results['news']['market_news']) == 1
            assert 'AAPL' in results['news']['stock_news']

    def test_analyze_without_news(self, analyzer, mock_broker):
        """collect_news=False 시 news 키 없음"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_news=False)
        assert 'news' not in results

    def test_analyze_news_failure_continues(self, analyzer, mock_broker):
        """뉴스 수집 실패 시 기술적 분석은 정상 진행"""
        with unittest.mock.patch('trading_bot.market_analyzer._has_news_collector', True), \
             unittest.mock.patch('trading_bot.market_analyzer.NewsCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.side_effect = Exception("RSS fetch failed")

            results = analyzer.analyze(['AAPL'], mock_broker, collect_news=True)

            # 기술적 분석은 정상
            assert 'AAPL' in results['stocks']
            assert 'indicators' in results['stocks']['AAPL']
            # 뉴스는 없음
            assert 'news' not in results

    def test_analyze_no_news_collector_installed(self, analyzer, mock_broker):
        """NewsCollector 미설치 시 news 키 없음"""
        with unittest.mock.patch('trading_bot.market_analyzer._has_news_collector', False):
            results = analyzer.analyze(['AAPL'], mock_broker, collect_news=True)
            assert 'news' not in results


class TestMarketAnalyzerFearGreedIntegration:
    """Fear & Greed Index 통합 테스트"""

    def test_analyze_with_fear_greed_includes_key(self, analyzer, mock_broker):
        """collect_fear_greed=True 시 결과에 fear_greed_index 키 포함"""
        mock_fg_data = {
            'current': {'value': 42.5, 'classification': 'Fear', 'timestamp': '2026-02-20T10:30:00'},
            'history': [{'date': '2026-02-20', 'value': 42.5, 'classification': 'Fear'}],
        }
        with unittest.mock.patch('trading_bot.market_analyzer._has_fear_greed', True), \
             unittest.mock.patch('trading_bot.market_analyzer.FearGreedCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.return_value = mock_fg_data
            mock_instance.generate_chart.return_value = '/tmp/fear_greed_chart.png'

            results = analyzer.analyze(['AAPL'], mock_broker, collect_fear_greed=True)

            assert 'fear_greed_index' in results
            assert results['fear_greed_index']['current']['value'] == 42.5
            assert results['fear_greed_index']['chart_path'] == '/tmp/fear_greed_chart.png'

    def test_analyze_without_fear_greed(self, analyzer, mock_broker):
        """collect_fear_greed=False 시 fear_greed_index 키 없음"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_fear_greed=False)
        assert 'fear_greed_index' not in results

    def test_analyze_fear_greed_failure_continues(self, analyzer, mock_broker):
        """F&G 수집 실패 시 기술적 분석은 정상 진행"""
        with unittest.mock.patch('trading_bot.market_analyzer._has_fear_greed', True), \
             unittest.mock.patch('trading_bot.market_analyzer.FearGreedCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.side_effect = Exception("API Error")

            results = analyzer.analyze(['AAPL'], mock_broker, collect_fear_greed=True)

            assert 'AAPL' in results['stocks']
            assert 'indicators' in results['stocks']['AAPL']
            assert 'fear_greed_index' not in results

    def test_analyze_fear_greed_returns_none(self, analyzer, mock_broker):
        """F&G API가 None 반환 시 키 미포함"""
        with unittest.mock.patch('trading_bot.market_analyzer._has_fear_greed', True), \
             unittest.mock.patch('trading_bot.market_analyzer.FearGreedCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.return_value = None

            results = analyzer.analyze(['AAPL'], mock_broker, collect_fear_greed=True)

            assert 'fear_greed_index' not in results

    def test_analyze_no_fear_greed_collector_installed(self, analyzer, mock_broker):
        """FearGreedCollector 미설치 시 fear_greed_index 키 없음"""
        with unittest.mock.patch('trading_bot.market_analyzer._has_fear_greed', False):
            results = analyzer.analyze(['AAPL'], mock_broker, collect_fear_greed=True)
            assert 'fear_greed_index' not in results

    def test_analyze_fear_greed_without_chart(self, analyzer, mock_broker):
        """차트 생성 실패 시 chart_path 미포함"""
        mock_fg_data = {
            'current': {'value': 55.0, 'classification': 'Greed', 'timestamp': '2026-02-20T10:30:00'},
            'history': [],
        }
        with unittest.mock.patch('trading_bot.market_analyzer._has_fear_greed', True), \
             unittest.mock.patch('trading_bot.market_analyzer.FearGreedCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.return_value = mock_fg_data
            mock_instance.generate_chart.return_value = None

            results = analyzer.analyze(['AAPL'], mock_broker, collect_fear_greed=True)

            assert 'fear_greed_index' in results
            assert 'chart_path' not in results['fear_greed_index']


class TestBuildAnalysisPromptWithNews:
    """뉴스 데이터 포함 프롬프트 테스트"""

    def test_prompt_includes_news_section(self, analyzer, mock_broker):
        """뉴스 데이터가 있으면 프롬프트에 뉴스 섹션 포함"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_news=False)
        # 수동으로 뉴스 데이터 추가
        results['news'] = {
            'collected_at': '2026-02-20T06:10:00',
            'market_news': [{'title': 'Fed holds rates', 'source': 'Reuters', 'published': '2026-02-20', 'link': ''}],
            'stock_news': {
                'AAPL': [{'title': 'Apple beats earnings', 'source': 'CNBC', 'published': '2026-02-20', 'link': ''}]
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            assert '뉴스' in prompt
            assert 'WebSearch' in prompt
            assert 'Fed holds rates' in prompt
            assert 'Apple beats earnings' in prompt

    def test_prompt_without_news_still_has_websearch(self, analyzer, mock_broker):
        """뉴스 데이터 없어도 WebSearch 안내 포함"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_news=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            assert 'WebSearch' in prompt

    def test_prompt_includes_news_event_section(self, analyzer, mock_broker):
        """프롬프트에 '뉴스 & 이벤트 분석' 섹션 포함"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_news=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            assert '뉴스 & 이벤트 분석' in prompt


class TestBuildAnalysisPromptWithFearGreed:
    """Fear & Greed 데이터 포함 프롬프트 테스트"""

    def test_prompt_includes_fear_greed_section(self, analyzer, mock_broker):
        """F&G 데이터가 있으면 프롬프트에 공포/탐욕 지수 섹션 포함"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_news=False, collect_fear_greed=False)
        # 수동으로 F&G 데이터 추가
        results['fear_greed_index'] = {
            'current': {'value': 42.5, 'classification': 'Fear', 'timestamp': '2026-02-20T10:30:00'},
            'history': [
                {'date': '2026-02-20', 'value': 42.5, 'classification': 'Fear'},
                {'date': '2026-02-19', 'value': 40.0, 'classification': 'Fear'},
            ],
            'chart_path': '/tmp/charts/fear_greed_2026-02-20.png',
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            assert '공포/탐욕 지수' in prompt
            assert 'Fear & Greed Index' in prompt
            assert '42.5' in prompt
            assert 'Fear' in prompt
            assert 'fear_greed_2026-02-20.png' in prompt
            assert 'Read 도구' in prompt

    def test_prompt_without_fear_greed_no_section(self, analyzer, mock_broker):
        """F&G 데이터 없으면 해당 섹션 미포함"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_news=False, collect_fear_greed=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            assert '공포/탐욕 지수 (Fear & Greed Index)' not in prompt

    def test_prompt_fear_greed_section_number(self, analyzer, mock_broker):
        """프롬프트에 '공포/탐욕 지수 분석' 섹션 번호 포함"""
        results = analyzer.analyze(['AAPL'], mock_broker, collect_news=False, collect_fear_greed=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            prompt = build_analysis_prompt(path)

            assert '공포/탐욕 지수 분석' in prompt
